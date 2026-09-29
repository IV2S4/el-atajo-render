"""
El Atajo - Render gratis de Shorts verticales (1080x1920) y videos largos horizontales (1920x1080)
Voz: Kokoro TTS (modelo abierto de Hugging Face). Respaldo: edge-tts.
Video: FFmpeg. Subtítulos palabra por palabra (ASS).

Uso:  python render.py payload.json salida.mp4
payload.json = {"escenas": [{"texto": "...", "tipo": "video"|"foto", "src": "https://...", "capitulo": "(opcional)"}],
                "voz": "em_alex", "orientacion": "vertical"|"horizontal"}
Si hay capítulos, además escribe <salida>.capitulos.json con el segundo en que empieza cada uno.
"""
import json, os, re, subprocess, sys, tempfile, shutil, wave
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import requests

W, H, FPS, SR = 1080, 1920, 30, 24000
ROOT = Path(__file__).resolve().parent
FONTS_DIR = ROOT / "fonts"
TEST_MODE = os.environ.get("TEST_TTS") == "silence"   # solo para pruebas sin modelo


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("FFmpeg falló:\n" + " ".join(cmd) + "\n" + r.stderr[-3000:])


def write_wav(path, audio):
    audio = np.clip(audio, -1, 1)
    pcm = (audio * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


# ---------------- VOZ ----------------
_pipeline = None
def tts_kokoro(text, voice):
    global _pipeline
    from kokoro import KPipeline
    if _pipeline is None:
        _pipeline = KPipeline(lang_code="e", repo_id="hexgrad/Kokoro-82M")  # "e" = español
    parts = [a for _, _, a in _pipeline(text, voice=voice, speed=1.08)]
    parts = [p.numpy() if hasattr(p, "numpy") else np.asarray(p) for p in parts]
    return np.concatenate(parts).astype(np.float32)


def tts_edge(text, out_wav):
    import asyncio, edge_tts
    mp3 = str(out_wav) + ".mp3"
    asyncio.run(edge_tts.Communicate(text, "es-MX-JorgeNeural", rate="+8%").save(mp3))
    run(["ffmpeg", "-y", "-i", mp3, "-ac", "1", "-ar", str(SR), str(out_wav)])


def voz(text, voice, out_wav):
    """Genera la voz de una escena. Devuelve duración en segundos."""
    if TEST_MODE:
        dur = max(1.5, len(text.split()) * 0.36)
        write_wav(out_wav, np.zeros(int(dur * SR), dtype=np.float32))
    else:
        try:
            audio = tts_kokoro(text, voice)
            audio = np.concatenate([audio, np.zeros(int(0.12 * SR), np.float32)])  # respiro corto
            write_wav(out_wav, audio)
        except Exception as e:
            print("Kokoro falló, uso respaldo edge-tts:", e, flush=True)
            tts_edge(text, out_wav)
    with wave.open(str(out_wav)) as w:
        return w.getnframes() / w.getframerate()


# ---------------- IMAGEN / VIDEO ----------------
def bajar(url, dest):
    r = requests.get(url, timeout=120, stream=True, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    return dest


def cover():
    return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p"
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-an"]


def clip_escena(i, esc, dur, tmp):
    out = tmp / f"seg{i:02d}.mp4"
    src = esc.get("src")
    try:
        if not src:
            raise ValueError("sin media")
        ext = ".mp4" if esc.get("tipo") != "foto" else ".jpg"
        f = bajar(src, tmp / f"media{i:02d}{ext}")
        if esc.get("tipo") == "foto":
            frames = int(dur * FPS) + 1
            zdir = ["min(zoom+0.0009,1.15)", "if(eq(on,1),1.15,max(zoom-0.0009,1.0))"][i % 2]
            vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
                  f"zoompan=z='{zdir}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
                  "setsar=1,format=yuv420p")
            run(["ffmpeg", "-y", "-loop", "1", "-i", str(f), "-t", f"{dur:.3f}", "-vf", vf, *ENC, str(out)])
        else:
            run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(f), "-t", f"{dur:.3f}", "-vf", cover(), *ENC, str(out)])
    except Exception as e:
        print(f"Escena {i+1}: sin imagen usable ({e}); uso fondo de color", flush=True)
        colores = ["0x1b0540", "0x062b3d", "0x3a0a5c", "0x0b1a3d"]
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={colores[i % 4]}:s={W}x{H}:r={FPS}",
             "-t", f"{dur:.3f}", "-vf", "format=yuv420p", *ENC, str(out)])
    return out


# ---------------- SUBTÍTULOS ----------------
def ass_time(t):
    t = max(0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def tiempos_palabras(texto, inicio, dur):
    palabras = texto.split()
    pesos = [len(re.sub(r"\W", "", p)) + 2 + (3 if re.search(r"[.,;:!?…]$", p) else 0) for p in palabras]
    total = sum(pesos) or 1
    util = dur - 0.15
    t, res = inicio, []
    for p, w in zip(palabras, pesos):
        d = util * w / total
        res.append((p, t, t + d)); t += d
    return res


def bgr(hexcolor, defecto="00D4FF"):
    """'#FFD400' -> '00D4FF' (formato de color de subtítulos ASS: azul-verde-rojo)."""
    h = (hexcolor or "").lstrip("#")
    if len(h) != 6:
        return defecto
    return (h[4:6] + h[2:4] + h[0:2]).upper()


def escribir_ass(escenas_tiempos, path, gancho="", color="", capitulos=None):
    c = bgr(color)
    horiz = W > H
    if horiz:   # video largo 16:9: subtítulos más chicos abajo, más palabras por línea
        sub_size, gan_size, gan_mv, marca_size, max_pal, max_chr, sub_y = 64, 78, 90, 34, 5, 34, int(H * 0.85)
    else:
        sub_size, gan_size, gan_mv, marca_size, max_pal, max_chr, sub_y = 96, 92, 330, 40, 3, 16, int(H * 0.64)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Montserrat ExtraBold,{sub_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,9,4,5,60,60,0,1
Style: Gancho,Montserrat ExtraBold,{gan_size},&H00101010,&H00101010,&H00{c},&H00{c},0,0,0,0,100,100,1,0,3,18,0,8,90,90,{gan_mv},1
Style: Cap,Montserrat ExtraBold,{int(gan_size*0.8)},&H00101010,&H00101010,&H00{c},&H00{c},0,0,0,0,100,100,1,0,3,14,0,7,70,70,70,1
Style: Marca,Montserrat ExtraBold,{marca_size},&H50FFFFFF,&H50FFFFFF,&H70D62BFF,&H00000000,0,0,0,0,100,100,3,0,1,3,0,9,50,50,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    total = max((p[-1][2] for p in escenas_tiempos if p), default=0) + 1
    # Marca "EL ATAJO" arriba a la derecha todo el video
    lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(total)},Marca,,0,0,0,,EL ATAJO")
    # Gancho grande los primeros segundos (texto negro sobre franja amarilla)
    if gancho:
        g = gancho.strip().upper()
        lines.append(f"Dialogue: 2,{ass_time(0)},{ass_time(2.8)},Gancho,,0,0,0,,"
                     r"{\q0\fad(120,250)\fscx80\fscy80\t(0,180,\fscx106\fscy106)\t(180,320,\fscx100\fscy100)}" + g)
    # Títulos de capítulo (videos largos): franja de color arriba a la izquierda unos segundos
    for ct, titulo in (capitulos or []):
        if ct > 0.5:
            lines.append(f"Dialogue: 2,{ass_time(ct)},{ass_time(ct + 3.5)},Cap,,0,0,0,,"
                         r"{\q0\fad(150,300)}" + titulo.strip().upper())
    AMARILLO = r"{\c&H" + c + r"&\fscx110\fscy110}"   # color del formato (por defecto #FFD400)
    BLANCO = r"{\c&HFFFFFF&\fscx100\fscy100}"
    for palabras in escenas_tiempos:
        # grupos de hasta 3 palabras, cortando antes si la línea queda muy larga (no se sale de la pantalla)
        grupos, g = [], []
        for pw in palabras:
            if g and (len(g) == max_pal or len(" ".join(x[0] for x in g + [pw])) > max_chr):
                grupos.append(g); g = []
            g.append(pw)
        if g:
            grupos.append(g)
        for g in grupos:
            for j, (_, s, e) in enumerate(g):
                txt = " ".join((AMARILLO if k == j else BLANCO) + w.upper() for k, (w, _, _) in enumerate(g))
                lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Sub,,0,0,0,,{{\\pos({W//2},{sub_y})}}{txt}")
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


# ---------------- PRINCIPAL ----------------
def main(payload_path, salida):
    global W, H
    data = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    if data.get("orientacion") == "horizontal":
        W, H = 1920, 1080
    escenas = [e for e in data["escenas"] if (e.get("texto") or "").strip()]
    voice = data.get("voz") or "em_alex"
    tmp = Path(tempfile.mkdtemp())
    wavs, segs, subs, caps, t = [], [], [], [], 0.0
    for i, esc in enumerate(escenas):
        texto = esc["texto"].strip()
        if (esc.get("capitulo") or "").strip():
            caps.append((t, esc["capitulo"].strip()))
        wav = tmp / f"voz{i:02d}.wav"
        dur = voz(texto, voice, wav)
        print(f"Escena {i+1}/{len(escenas)}: {dur:.1f}s", flush=True)
        wavs.append(wav)
        segs.append(clip_escena(i, esc, dur, tmp))
        subs.append(tiempos_palabras(texto, t, dur))
        t += dur

    (tmp / "v.txt").write_text("".join(f"file '{s}'\n" for s in segs))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "v.txt"), "-c", "copy", str(tmp / "video.mp4")])
    (tmp / "a.txt").write_text("".join(f"file '{w}'\n" for w in wavs))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "a.txt"), "-c", "pcm_s16le", str(tmp / "voz.wav")])
    escribir_ass(subs, tmp / "subs.ass", data.get("gancho") or "", (data.get("estilo") or {}).get("color", ""), caps)

    vf = f"ass={tmp/'subs.ass'}:fontsdir={FONTS_DIR}"
    entradas = ["-i", str(tmp / "video.mp4"), "-i", str(tmp / "voz.wav")]
    usar_musica = data.get("musica", True)
    if usar_musica:
        try:
            import musica
            musica.guardar(tmp / "musica.wav", musica.generar(t + 0.5))
            entradas += ["-i", str(tmp / "musica.wav")]
        except Exception as e:
            print("Sin música (falló el generador):", e, flush=True)
            usar_musica = False
    if usar_musica:
        # la música baja sola cuando habla la voz (ducking) y se desvanece al final
        fin = max(0.0, t - 2.0)
        af = ("[1:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[v1][v2];"
              f"[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.45,afade=t=in:d=0.8,afade=t=out:st={fin:.2f}:d=2[mus];"
              "[mus][v2]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=350[duck];"
              "[v1][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        mapa = ["-filter_complex", af, "-map", "0:v", "-map", "[a]"]
    else:
        mapa = ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
    run(["ffmpeg", "-y", *entradas, "-vf", vf, *mapa,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest", "-movflags", "+faststart", salida])
    if caps:   # para los capítulos de YouTube (0:00 Intro, 1:12 ..., etc.)
        Path(str(salida) + ".capitulos.json").write_text(json.dumps(
            [{"segundo": round(ct, 1), "titulo": ti} for ct, ti in caps], ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"LISTO: {salida} ({t:.1f}s)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "video.mp4")
