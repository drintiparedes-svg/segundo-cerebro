"""Genera web/manual.html desde docs/MANUAL_DE_USO.md, con el mismo sistema visual del sitio."""
from __future__ import annotations

import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]

HEAD = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Manual de uso · Payment Integrity</title>
<meta name="description" content="Manual de uso y reglas de indicadores y métricas del Payment Integrity Engine">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{color-scheme:light;--page:#f5f7f9;--surface:#fcfcfb;--surface-2:#eef2f6;--ink:#0f1720;--ink-2:#4b5a68;--muted:#8a929b;
  --grid:#e1e0d9;--line:rgba(15,23,32,.10);--accent:#2a78d6;--info-bg:#e8f1fb;--info-ink:#1c5cab;--code-bg:#eef2f6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--surface-2:#242423;
  --ink:#fff;--ink-2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--line:rgba(255,255,255,.10);--accent:#3987e5;--info-bg:#16233a;--info-ink:#9ec5f4;--code-bg:#242423}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--surface-2:#242423;--ink:#fff;--ink-2:#c3c2b7;
  --muted:#898781;--grid:#2c2c2a;--line:rgba(255,255,255,.10);--accent:#3987e5;--info-bg:#16233a;--info-ink:#9ec5f4;--code-bg:#242423}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:15px;line-height:1.6}
.shell{display:grid;grid-template-columns:280px minmax(0,1fr);gap:32px;max-width:1240px;margin:0 auto;padding:0 24px 64px;align-items:start}
@media (max-width:980px){.shell{grid-template-columns:1fr;gap:16px}nav.toc{position:static!important;max-height:none!important}}
header.top{border-bottom:1px solid var(--line);background:var(--surface)}
header.top .in{max-width:1240px;margin:0 auto;padding:20px 24px;display:flex;flex-wrap:wrap;gap:12px;align-items:baseline;justify-content:space-between}
header.top strong{font-size:16px;font-weight:600}
header.top a{color:var(--accent);text-decoration:none;font-size:13px;font-weight:500}
header.top a:hover{text-decoration:underline}
nav.toc{position:sticky;top:24px;max-height:calc(100vh - 48px);overflow:auto;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px 18px;margin-top:28px}
nav.toc h2{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 10px}
nav.toc ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:2px}
nav.toc a{display:block;padding:4px 8px;border-radius:4px;color:var(--ink-2);text-decoration:none;font-size:13px;border-left:2px solid transparent}
nav.toc a:hover{background:var(--surface-2);color:var(--ink)}
nav.toc a:focus-visible{outline:2px solid var(--accent)}
main{min-width:0;padding-top:28px;max-width:78ch}
main h1{font-size:28px;font-weight:600;letter-spacing:-.015em;margin:0 0 6px;text-wrap:balance}
main h1+p{color:var(--ink-2);margin:0 0 8px}
main h2{font-size:20px;font-weight:600;margin:40px 0 12px;padding-top:12px;border-top:1px solid var(--line);text-wrap:balance;scroll-margin-top:20px}
main h3{font-size:16px;font-weight:600;margin:26px 0 8px;scroll-margin-top:20px}
main p,main li{color:var(--ink)}
main ul,main ol{padding-left:22px}
main li{margin:3px 0}
main hr{border:0;border-top:1px solid var(--line);margin:20px 0}
main strong{font-weight:600}
code{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-size:.88em;background:var(--code-bg);padding:1px 5px;border-radius:3px}
pre{background:var(--code-bg);border:1px solid var(--line);border-radius:6px;padding:12px 14px;overflow-x:auto}
pre code{background:none;padding:0;font-size:13px;line-height:1.5}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--surface);margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:8px 11px;border-bottom:1px solid var(--grid);text-align:left;vertical-align:top}
th{background:var(--surface-2);color:var(--ink-2);font-weight:600;font-size:12.5px;white-space:nowrap}
tr:last-child td{border-bottom:0}
blockquote{margin:14px 0;padding:10px 14px;background:var(--info-bg);color:var(--info-ink);border-radius:6px}
footer{border-top:1px solid var(--line);margin-top:48px;padding-top:16px;font-size:12.5px;color:var(--muted)}
</style></head><body>
<header class="top"><div class="in"><strong>Payment Integrity Engine</strong>
<span><a href="/">← Volver a la demostración</a></span></div></header>
<div class="shell">
"""

FOOTER = """<footer>Payment Integrity Engine · el score mide riesgo de pago indebido y prioriza auditorías; no constituye imputación. Todo caso de nivel 3 o 4 requiere revisión humana.</footer>
</main></div></body></html>"""


def slug(text: str) -> str:
    t = re.sub(r"<[^>]+>", "", text).lower()
    t = t.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t or "seccion"


def build() -> None:
    md = (ROOT / "docs" / "MANUAL_DE_USO.md").read_text(encoding="utf-8")
    html = markdown.markdown(md, extensions=["tables", "fenced_code"])
    html = html.replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>")

    # anclas en h2/h3 y tabla de contenidos con los h2
    toc = []
    def anchor(m):
        level, text = m.group(1), m.group(2)
        s = slug(text)
        if level == "2":
            toc.append((s, re.sub(r"<[^>]+>", "", text)))
        return f'<h{level} id="{s}">{text}</h{level}>'
    html = re.sub(r"<h([23])>(.*?)</h\1>", anchor, html, flags=re.S)

    nav = ['<nav class="toc" aria-label="Contenidos"><h2>Contenidos</h2><ol>']
    nav += [f'<li><a href="#{s}">{t}</a></li>' for s, t in toc]
    nav.append("</ol></nav><main>")
    (ROOT / "web" / "manual.html").write_text(HEAD + "".join(nav) + html + FOOTER, encoding="utf-8")
    print(f"web/manual.html: {len(html) / 1024:.0f} KB · {len(toc)} secciones")


if __name__ == "__main__":
    build()
