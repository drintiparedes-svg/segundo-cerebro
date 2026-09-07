"""Construye web/index.html (Vercel, documento completo) y, opcionalmente, una variante body-only
para publicación como artefacto, inyectando data.json e informe.html en web/template.html."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def build(artifact_out: Path | None = None) -> None:
    tpl = (WEB / "template.html").read_text(encoding="utf-8")
    data = (WEB / "data.json").read_text(encoding="utf-8")
    report_html = (WEB / "informe.html").read_text(encoding="utf-8")
    for blob in (data, report_html):
        if "</script" in blob.lower():
            raise ValueError("el contenido inyectado no puede contener cierres de script")
    page = tpl.replace("/*__DATA__*/{}", data).replace('/*__REPORT__*/""', json.dumps(report_html, ensure_ascii=False))
    full = ("<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<meta name='description' content='Payment Integrity Engine: demostración con resultados precalculados sobre data sintética'>"
            "</head><body>" + page + "</body></html>")
    (WEB / "index.html").write_text(full, encoding="utf-8")
    print(f"web/index.html: {len(full) / 1024:.0f} KB")
    if artifact_out:
        artifact_out.write_text(page, encoding="utf-8")
        print(f"artefacto: {artifact_out}")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
