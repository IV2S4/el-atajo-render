# Convierte productos/<slug>.json en una guía PDF con diseño de El Atajo + portadas PNG
import json, sys, html, re, subprocess, pathlib
src = pathlib.Path(sys.argv[1]); data = json.loads(src.read_text(encoding="utf-8"))
out = pathlib.Path("salida"); out.mkdir(exist_ok=True)
e = html.escape
def hl(t): return re.sub(r"\[([^\]]+)\]", r'<span class="ph">[\1]</span>', e(t))
FONTS = '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet">'
tit, res = data["titulo"], data.get("titulo_resaltado", "")
titulo_html = e(tit).replace(e(res), f'<span class="am">{e(res)}</span>') if res and res in tit else e(tit)
secs, n = "", 0
for i, s in enumerate(data["secciones"]):
    cards = ""
    for it in s["items"]:
        n += 1
        cards += f'<div class="p"><div class="pn">{n:02d}</div><div><h4>{e(it["titulo"])}</h4><p>{hl(it["texto"])}</p></div></div>'
    secs += f'<section class="cat"><div class="cat-h"><span class="ci">{e(s.get("emoji",""))}</span><div><p class="cn">Sección {i+1}</p><h2>{e(s["nombre"])}</h2><p class="cs">{e(s.get("intro",""))}</p></div></div>{cards}</section>'
indice = "".join(f'<li><span>{e(s.get("emoji",""))}</span> {e(s["nombre"])} <em>{len(s["items"])}</em></li>' for s in data["secciones"])
chips = "".join(f'<span>{e(s.get("emoji",""))} {e(s["nombre"])}</span>' for s in data["secciones"])
consejos = "".join(f"<li>{e(c)}</li>" for c in data.get("consejos", []))
CSS = """
@page{size:A4;margin:13mm 15mm}@page:first{margin:0}*{box-sizing:border-box}
body{font-family:Inter,Arial,sans-serif;color:#15181e;font-size:10pt;line-height:1.45;margin:0}
.portada{height:297mm;width:210mm;background:#0b0d12;color:#fff;position:relative;overflow:hidden;padding:28mm 20mm;page-break-after:always}
.b1{position:absolute;width:160mm;height:160mm;border-radius:50%;background:#FFD400;filter:blur(60px);opacity:.35;top:-70mm;left:-50mm}
.b2{position:absolute;width:140mm;height:140mm;border-radius:50%;background:#7c3aed;filter:blur(60px);opacity:.3;bottom:-60mm;right:-50mm}
.logo{position:relative;font-size:15pt}.logo b{font-weight:900}.la{display:inline-block;background:#FFD400;color:#0b0d12;font-weight:900;border-radius:8px;padding:1px 9px;margin-right:8px}
.portada h1{position:relative;font-size:44pt;line-height:1.03;letter-spacing:-.02em;font-weight:900;margin:44mm 0 8mm}.am{color:#FFC400}
.sub{position:relative;font-size:15pt;color:#c9cfdb;max-width:150mm}
.chips{position:relative;display:flex;flex-wrap:wrap;gap:8px;margin-top:12mm}.chips span{border:1px solid #333a48;border-radius:99px;padding:6px 12px;font-size:10pt;color:#dfe3ea}
.pie{position:absolute;bottom:20mm;left:20mm;right:20mm;display:flex;justify-content:space-between;color:#8b93a3;font-size:9.5pt}
h2{font-size:20pt;margin:0;line-height:1.1}.box{background:#fff8d6;border:1px solid #f4e19a;border-radius:12px;padding:5mm 6mm;margin:5mm 0}
ol.idx{list-style:none;padding:0}ol.idx li{display:flex;gap:10px;padding:3mm 0;border-bottom:1px solid #eee;font-weight:700;font-size:12pt}ol.idx em{margin-left:auto;font-style:normal;color:#586070;font-weight:400}
.cat{page-break-before:always}.cat-h{display:flex;gap:5mm;align-items:center;background:#0b0d12;color:#fff;border-radius:14px;padding:4.5mm 6mm;margin-bottom:3mm}
.ci{font-size:28pt}.cn{margin:0;color:#FFD400;font-weight:700;font-size:9pt;text-transform:uppercase;letter-spacing:.1em}.cs{margin:1mm 0 0;color:#c9cfdb}
.p{display:flex;gap:4mm;padding:2.3mm 0;border-bottom:1px solid #ececec;page-break-inside:avoid}
.pn{flex:none;width:10mm;height:10mm;border-radius:8px;background:linear-gradient(135deg,#FFD400,#FF8A00);display:grid;place-items:center;font-weight:900}
.p h4{margin:0 0 1mm;font-size:11pt}.p p{margin:0;color:#2b3039}.ph{background:#fff1a8;border-radius:4px;padding:0 3px;font-weight:700;color:#6b5200}
.fin{page-break-before:always}.cta{background:#0b0d12;color:#fff;border-radius:16px;padding:10mm;margin-top:6mm}.cta a{color:#FFD400}
.legal{color:#6b7280;font-size:8.5pt;margin-top:8mm}
"""
doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">{FONTS}<style>{CSS}</style></head><body>
<div class="portada"><div class="b1"></div><div class="b2"></div><div class="logo"><span class="la">A</span>El <b>Atajo</b></div>
<h1>{titulo_html}</h1><p class="sub">{e(data.get("subtitulo",""))}</p><div class="chips">{chips}</div>
<div class="pie"><span>Guía práctica · {e(data.get("edicion",""))}</span><span>ELATAJO en YouTube</span></div></div>
<section><h2>Cómo usar esta guía</h2><p>{e(data.get("introduccion",""))}</p>
<div class="box"><b>Regla de oro:</b> todo lo que está entre <span class="ph">[corchetes]</span> lo cambias por tu información.</div>
{"<h3>Consejos para sacarle el máximo</h3><ol>"+consejos+"</ol>" if consejos else ""}
<h3>Contenido</h3><ol class="idx">{indice}</ol>
<div class="box"><b>Importante:</b> contenido educativo. Revisa datos y decisiones importantes de dinero, salud o temas legales con un profesional.</div></section>
{secs}
<section class="fin"><h2>¿Y ahora qué?</h2><p>{e(data.get("cierre",""))}</p>
<div class="cta"><h2>Más atajos cada semana</h2><p>Videos cortos en el canal <b>ELATAJO</b> de YouTube y artículos en el blog: <a href="https://iv2s4.github.io/el-atajo-render/">iv2s4.github.io/el-atajo-render</a></p></div>
<p class="legal">© El Atajo. Guía para uso personal. No se permite revenderla ni compartirla públicamente. Contenido educativo, no es asesoría financiera, legal ni profesional.</p></section>
</body></html>"""
(out / "guia.html").write_text(doc, encoding="utf-8")
def portada(w, h, nombre, fs):
    p = f"""<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>body{{margin:0;width:{w}px;height:{h}px;background:#0b0d12;font-family:Inter,Arial,sans-serif;color:#fff;overflow:hidden;position:relative}}
.b1{{position:absolute;width:{w*.6}px;height:{w*.6}px;border-radius:50%;background:#FFD400;filter:blur(120px);opacity:.35;top:-{w*.3}px;left:-{w*.15}px}}
.b2{{position:absolute;width:{w*.5}px;height:{w*.5}px;border-radius:50%;background:#7c3aed;filter:blur(120px);opacity:.35;bottom:-{w*.25}px;right:-{w*.1}px}}
.t{{position:absolute;left:{w*.065}px;right:{w*.065}px;top:{h*.12}px}}h1{{font-size:{fs}px;line-height:1.02;font-weight:900;letter-spacing:-2px;margin:0}}.am{{color:#FFC400}}
p{{font-size:{fs*.33}px;color:#c9cfdb;margin:{fs*.35}px 0 0}}.lg{{position:absolute;left:{w*.065}px;bottom:{h*.13}px;font-size:{fs*.3}px}}.lg span{{background:#FFD400;color:#0b0d12;font-weight:900;border-radius:8px;padding:2px 10px;margin-right:8px}}
</style></head><body><div class="b1"></div><div class="b2"></div><div class="t"><h1>{titulo_html}</h1><p>{e(data.get("subtitulo",""))}</p></div><div class="lg"><span>A</span>El <b>Atajo</b> · Guía PDF</div></body></html>"""
    f = out / (nombre + ".html"); f.write_text(p, encoding="utf-8")
    subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--hide-scrollbars", "--virtual-time-budget=8000",
                    f"--window-size={w},{h}", f"--screenshot={out / (nombre + '.png')}", f.resolve().as_uri()], check=True)
subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--virtual-time-budget=10000", "--no-pdf-header-footer",
                f"--print-to-pdf={out / 'guia.pdf'}", (out / "guia.html").resolve().as_uri()], check=True)
portada(1080, 1080, "portada-cuadrada", 96)
portada(1280, 720, "portada-ancha", 78)
(out / "venta.txt").write_text(f"NOMBRE: {tit}\nPRECIO SUGERIDO: {data.get('precio','7')} USD\n\nRESUMEN:\n{data.get('resumen','')}\n\nDESCRIPCIÓN:\n{data.get('descripcion_venta','')}\n", encoding="utf-8")
print("ok", n, "items")
