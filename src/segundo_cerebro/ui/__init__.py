"""UI del Segundo Cerebro.

`index.html` se escribe sin el esqueleto (doctype/html/head) para poder
publicarse tal cual como Artifact; `render_page()` lo completa para
servirlo por HTTP o generarlo como sitio estático.
"""

from __future__ import annotations

from importlib import resources

SKELETON_OPEN = "<!doctype html>\n<html lang=\"es\">\n"
SKELETON_CLOSE = "\n</html>\n"


def ui_body() -> str:
    return resources.files(__package__).joinpath("index.html").read_text("utf-8")


def render_page() -> str:
    return SKELETON_OPEN + ui_body() + SKELETON_CLOSE
