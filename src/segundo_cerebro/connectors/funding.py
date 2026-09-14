"""Radar de financiamiento: convocatorias verificadas en la fuente oficial.

Dos entradas, una regla:
- `brain/self/funding.md`: convocatorias que sigues a mano (nombre, URL
  oficial, cierre, monto, palabras clave, proyecto).
- Páginas oficiales configuradas (ANID, CORFO, Start-Up Chile, Wellcome,
  Horizon/EIT Health, NIH…): barrido heurístico de títulos con fecha de
  cierre.

Regla del radar: **solo entra lo verificable como ABIERTO** — URL
alcanzable y fecha de cierre futura. Lo que no se puede verificar se
reporta como «sin verificar», nunca como oportunidad. Cada oportunidad es
un knowledge object `opportunity` con `valid_to` = cierre.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from ..areas import FRONTMATTER_RE
from ..models import KnowledgeObject
from .base import Connector, ConnectorSpec, SyncResult
from .validated import get_text

DEFAULT_FUNDING_FILE = os.environ.get("SB_FUNDING", "brain/self/funding.md")
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
         "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
         "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
DATE_RES = [
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})"),
    re.compile(r"(\d{1,2})\s+de\s+([a-záé]+)\s+(?:de\s+)?(\d{4})", re.IGNORECASE),
    re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})"),
]
CLOSE_WORDS = re.compile(r"(cierre|cierra|cerrad[ao]|plazo|hasta el|deadline|closes?|closed|due|vence)", re.IGNORECASE)
OPEN_WORDS = re.compile(r"(abiert[ao]|open|vigente|en curso|postulaci[oó]n|call)", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
ANCHOR_RE = re.compile(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
AMOUNT_RE = re.compile(r"(?:\$|CLP|USD|US\$|€|EUR|UF)\s?[\d.,]+(?:\s?(?:millones|MM|M|mil))?", re.IGNORECASE)


@dataclass
class Call:
    name: str
    url: str
    deadline: str | None = None          # YYYY-MM-DD
    amount: str | None = None
    funder: str = ""
    keywords: list[str] = field(default_factory=list)
    project: str | None = None
    origin: str = "manual"               # manual | scan
    verified: bool = False
    status: str = "sin verificar"        # abierta | cerrada | sin verificar
    note: str = ""

    @property
    def key(self) -> str:
        return hashlib.sha1(f"{self.url}|{self.name}".encode()).hexdigest()[:12]


def parse_date(text: str) -> str | None:
    """Primera fecha que aparece en el texto (por posición, no por formato)."""
    found = [(m.start(), rx, m) for rx in DATE_RES if (m := rx.search(text))]
    for _, rx, m in sorted(found, key=lambda t: t[0]):
        g = m.groups()
        try:
            if rx is DATE_RES[0]:
                return date(int(g[0]), int(g[1]), int(g[2])).isoformat()
            if rx is DATE_RES[1]:
                return date(int(g[2]), int(g[1]), int(g[0])).isoformat()
            month = MESES.get(g[1].lower()) if rx is DATE_RES[2] else MESES.get(g[0].lower())
            if month:
                day = int(g[0]) if rx is DATE_RES[2] else int(g[1])
                return date(int(g[2]), month, day).isoformat()
        except ValueError:
            continue
    return None


def load_manual(path: str | Path = DEFAULT_FUNDING_FILE) -> list[Call]:
    p = Path(path)
    if not p.exists():
        return []
    m = FRONTMATTER_RE.match(p.read_text(encoding="utf-8"))
    if not m:
        return []
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return []
    calls = []
    for raw in data.get("calls", []) or []:
        if not raw.get("name") or not raw.get("url"):
            continue
        dl = raw.get("deadline")
        calls.append(Call(name=str(raw["name"]), url=str(raw["url"]),
                          deadline=(dl.isoformat() if hasattr(dl, "isoformat") else (str(dl) if dl else None)),
                          amount=str(raw["amount"]) if raw.get("amount") else None,
                          funder=str(raw.get("funder", "")), keywords=[str(k).lower() for k in raw.get("keywords", []) or []],
                          project=raw.get("project"), origin="manual"))
    return calls


def scan_page(html: str, funder: str, base_url: str = "") -> list[Call]:
    """Heurística: enlaces cuyo texto o contexto cercano mencione apertura/
    cierre y contenga una fecha. Devuelve candidatos SIN verificar."""
    text_html = html
    calls = []
    anchors = list(ANCHOR_RE.finditer(text_html))
    for idx, m in enumerate(anchors):
        href, inner = m.group(1), TAG_RE.sub(" ", m.group(2))
        title = html_lib.unescape(re.sub(r"\s+", " ", inner)).strip()
        if len(title) < 12 or len(title) > 160:
            continue
        stop = anchors[idx + 1].start() if idx + 1 < len(anchors) else len(text_html)
        window = html_lib.unescape(TAG_RE.sub(" ", text_html[m.start(): min(stop, m.end() + 400)]))
        if not (CLOSE_WORDS.search(window) or OPEN_WORDS.search(window)):
            continue
        deadline = parse_date(window)
        amount = AMOUNT_RE.search(window)
        url = href if href.startswith("http") else (base_url.rstrip("/") + "/" + href.lstrip("/"))
        calls.append(Call(name=title, url=url, deadline=deadline, funder=funder,
                          amount=amount.group(0) if amount else None, origin="scan"))
    # dedupe por url
    seen, out = set(), []
    for c in calls:
        if c.url in seen:
            continue
        seen.add(c.url)
        out.append(c)
    return out


def verify(call: Call, today: date | None = None, fetch=None, check_url: bool = True) -> Call:
    """Abierta = URL alcanzable (si se pide) y cierre futuro. Sin cierre
    conocido → sin verificar (nunca se asume abierta)."""
    today = today or date.today()
    if check_url:
        try:
            get_text(call.url, fetch)
            call.verified = True
        except Exception as exc:
            call.verified = False
            call.status = "sin verificar"
            call.note = f"URL no alcanzable: {type(exc).__name__}"
            return call
    else:
        call.verified = True
    if not call.deadline:
        call.status = "sin verificar"
        call.note = "sin fecha de cierre confirmada"
    elif call.deadline >= today.isoformat():
        call.status = "abierta"
    else:
        call.status = "cerrada"
    return call


def match_project(call: Call, projects) -> str | None:
    if call.project:
        return call.project
    text = f"{call.name} {' '.join(call.keywords)}".lower()
    for p in projects:
        if any(k in text for k in p.keywords):
            return p.id
    return None


def upsert_opportunities(store, calls: list[Call], projects=None, today: date | None = None) -> list[KnowledgeObject]:
    """Solo las ABIERTAS entran a la memoria, con id determinista."""
    today = today or date.today()
    projects = projects or []
    kos = []
    for c in calls:
        if c.status != "abierta":
            continue
        pid = match_project(c, projects)
        pname = next((p.name for p in projects if p.id == pid), None)
        ko = KnowledgeObject(
            id=f"ko-fund-{c.key}", ko_type="opportunity", title=c.name[:120],
            statement=f"{c.name} — {c.funder or 'convocatoria'}; cierra {c.deadline}"
                      + (f"; monto {c.amount}" if c.amount else "") + f". {c.url}",
            date=today.isoformat(), project=pname, status="active", confidence="confirmed",
            tags=["financiamiento", c.origin] + ([f"proyecto:{pid}"] if pid else []),
            valid_from=today.isoformat(), valid_to=c.deadline,
            area=next((p.area for p in projects if p.id == pid), None))
        store.add_knowledge_object(ko)
        kos.append(ko)
    return kos


def radar(store, brain_dir: str | Path, sources: list[dict] | None = None, fetch=None,
          today: date | None = None, manual_path: str | Path = DEFAULT_FUNDING_FILE,
          check_urls: bool = True) -> dict:
    """Corre el radar: manual + barrido, verifica, registra abiertas e
    informa el resto."""
    from ..projects import load_projects
    today = today or date.today()
    projects = load_projects()
    calls = load_manual(manual_path)
    errors = {}
    for src in sources or []:
        try:
            calls += scan_page(get_text(src["url"], fetch), src.get("name", src["url"]), src["url"])
        except Exception as exc:
            errors[src.get("name", src["url"])] = f"{type(exc).__name__}: {exc}"
    for c in calls:
        verify(c, today, fetch, check_url=check_urls)
    opened = upsert_opportunities(store, calls, projects, today)
    # cerrar oportunidades vencidas ya registradas
    for ko in store.list_knowledge_objects(ko_type="opportunity", status="active", limit=500):
        if ko.valid_to and ko.valid_to < today.isoformat():
            store.update_ko(ko.id, status="done")
    report = ["# Radar de financiamiento — " + today.isoformat(), ""]
    for label in ("abierta", "cerrada", "sin verificar"):
        group = [c for c in calls if c.status == label]
        report.append(f"## {label.capitalize()} ({len(group)})")
        for c in group:
            report.append(f"- **{c.name}** · {c.funder or '—'} · cierre {c.deadline or '?'}"
                          + (f" · {c.amount}" if c.amount else "") + f" · {c.url}"
                          + (f" · _{c.note}_" if c.note else ""))
        report.append("")
    if errors:
        report.append("## Fuentes con error")
        report += [f"- {k}: {v}" for k, v in errors.items()]
    from ..agents import save_report
    path = save_report(brain_dir, "radar-financiamiento", "\n".join(report))
    return {"calls": calls, "open": len(opened), "report": str(path), "errors": errors,
            "counts": {s: sum(1 for c in calls if c.status == s) for s in ("abierta", "cerrada", "sin verificar")}}


class FundingConnector(Connector):
    spec = ConnectorSpec(
        id="funding", name="Radar de financiamiento", kind="api", privacy="read-cloud",
        description="Página oficial de convocatorias (ANID, CORFO, Wellcome…); solo entran las verificables como abiertas.",
        config_schema={"url": {"type": "str", "required": True, "help": "página oficial de convocatorias"},
                       "name": {"type": "str", "required": False, "help": "financista"}},
        setup_hint="sb connect add funding --config url=https://anid.cl/concursos/ --config name=ANID")
    fetch = None

    @property
    def label(self) -> str:
        return self.config.get("name") or self.config.get("url", self.id)

    def test(self) -> dict:
        try:
            n = len(scan_page(get_text(self.config["url"], type(self).fetch), self.label, self.config["url"]))
            return {"ok": True, "detail": f"{n} candidatas en la página (sin verificar)"}
        except Exception as exc:
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    def sync(self, store) -> SyncResult:
        r = radar(store, self.brain_dir, sources=[{"name": self.label, "url": self.config["url"]}],
                  fetch=type(self).fetch, manual_path=Path("/nonexistent"))
        return SyncResult(detail=f"abiertas {r['counts']['abierta']} · cerradas {r['counts']['cerrada']} "
                                 f"· sin verificar {r['counts']['sin verificar']}",
                          error=next(iter(r["errors"].values()), None))
