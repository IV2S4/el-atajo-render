"""
El Atajo - Render gratis de Shorts verticales (1080x1920)
Voz: Kokoro TTS (modelo abierto de Hugging Face). Respaldo: edge-tts.
Video: FFmpeg. Subtítulos palabra por palabra (ASS).

Uso:  python render.py payload.json salida.mp4
payload.json = {"escenas": [{"texto": "...", "tipo": "video"|"foto", "src": "https://..."}], "voz": "em_alex"}
"""
import json, os, re, subprocess, sys, tempfile, shutil, wave
from pathlib import Path

import numpy as np
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


COVER = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p"
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
            run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(f), "-t", f"{dur:.3f}", "-vf", COVER, *ENC, str(out)])
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


def escribir_ass(escenas_tiempos, path):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,AtajoSubs,96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,9,4,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    AMARILLO = r"{\c&H00D4FF&\fscx110\fscy110}"   # BGR -> #FFD400
    BLANCO = r"{\c&HFFFFFF&\fscx100\fscy100}"
    for palabras in escenas_tiempos:
        grupos = [palabras[k:k + 3] for k in range(0, len(palabras), 3)]
        for g in grupos:
            for j, (_, s, e) in enumerate(g):
                txt = " ".join((AMARILLO if k == j else BLANCO) + w.upper() for k, (w, _, _) in enumerate(g))
                lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Sub,,0,0,0,,{{\\pos({W//2},{int(H*0.64)})}}{txt}")
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


# ---------------- PRINCIPAL ----------------
def main(payload_path, salida):
    data = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    escenas = [e for e in data["escenas"] if (e.get("texto") or "").strip()]
    voice = data.get("voz") or "em_alex"
    tmp = Path(tempfile.mkdtemp())
    wavs, segs, subs, t = [], [], [], 0.0
    for i, esc in enumerate(escenas):
        texto = esc["texto"].strip()
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
    escribir_ass(subs, tmp / "subs.ass")

    vf = f"ass={tmp/'subs.ass'}:fontsdir={FONTS_DIR}"
    run(["ffmpeg", "-y", "-i", str(tmp / "video.mp4"), "-i", str(tmp / "voz.wav"), "-vf", vf,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest", "-movflags", "+faststart", salida])
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"LISTO: {salida} ({t:.1f}s)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "video.mp4")
