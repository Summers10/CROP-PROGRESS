"""Argentina – Ministry of Agriculture (MAGyP) weekly 'Informe Semanal' PDF.

BETA: PDF table extraction. Parses the 'AVANCE DE LA SIEMBRA/COSECHA DE <crop>'
pages and reads the TOTAL PAÍS rows for this campaign and last.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from common import payload, rec, session, validate

LIST = "https://www.magyp.gob.ar/sitio/areas/estimaciones/estimaciones/informes/"
BASE = "https://www.magyp.gob.ar"

CROPS = {"MAIZ": "Corn", "MAÍZ": "Corn", "SOJA": "Soybeans", "GIRASOL": "Sunflower", "TRIGO": "Wheat",
         "ARROZ": "Rice", "SORGO": "Sorghum", "CEBADA": "Barley", "MANI": "Peanuts", "MANÍ": "Peanuts",
         "ALGODON": "Cotton", "ALGODÓN": "Cotton", "AVENA": "Oats", "COLZA": "Canola"}

HEAD_RE = re.compile(r"AVANCE\s+DE\s+(?:LA\s+)?(SIEMBRA|COSECHA)\s+DE\s+([A-ZÁÉÍÓÚÑ ]+?)\s*(?:\(|$|\n|CAMPA)", re.I)
CAMP_RE = re.compile(r"CAMPAÑA:?\s*(\d{4})\s*/\s*(\d{2,4})", re.I)
DATES_RE = re.compile(r"^(?:\d{2}/\d{2}\s*){3,}$")


def _num(tok: str) -> float:
    return float(tok.replace(".", "").replace(",", "."))


def clean_url(url: str) -> str:
    """Percent-encode spaces in the path so the PDF link stays a single URL."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe="/%"), parts.query, ""))


def document_name(url: str) -> str:
    name = unquote(urlsplit(url).path).rsplit("/", 1)[-1]
    # Drop the archive id prefix (261105_) so the visible citation is the document name.
    name = re.sub(r"^\d+_", "", name)
    return name or "MAGyP Informe Semanal.pdf"


def _row_after(line: str, label: str):
    """'26/27 11.465.367 13,13 19,0 27 31 35 37' -> (area, [pcts])"""
    m = re.search(r"(?<![\d/])" + re.escape(label) + r"\s+(\d{1,3}(?:\.\d{3})+|\d+)((?:\s+\d{1,3}(?:,\d+)?)*)\s*$", line)
    if not m:
        return None
    pcts = [_num(t) for t in m.group(2).split()]
    return _num(m.group(1)), pcts


def parse_page(text: str):
    """Return dict(crop, op, season, report_dates, cur, ly) or None."""
    h = HEAD_RE.search(text)
    c = CAMP_RE.search(text)
    if not h or not c:
        return None
    op = "planted" if h.group(1).upper() == "SIEMBRA" else "harvested"
    crop_local = h.group(2).strip().upper()
    y1, y2 = int(c.group(1)), int(c.group(2))
    cur_lbl, ly_lbl = f"{y1 % 100:02d}/{y2 % 100:02d}", f"{(y1 - 1) % 100:02d}/{(y2 - 1) % 100:02d}"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    dates = next((ln.split() for ln in lines if DATES_RE.match(ln)), None)
    if not dates:
        return None

    def total(label):
        best, best_i = None, None
        for i, ln in enumerate(lines):
            r = _row_after(ln, label)
            if r and (best is None or r[0] > best[0]):
                best, best_i = r, i
        if best and not best[1] and best_i is not None:
            # values sometimes land on an adjacent line of pure numbers
            for j in (best_i - 1, best_i + 1, best_i - 2):
                if 0 <= j < len(lines) and re.fullmatch(r"(?:\d{1,3}(?:,\d+)?\s*){2,}", lines[j]):
                    best = (best[0], [_num(t) for t in lines[j].split()])
                    break
        return best

    cur, ly = total(cur_lbl), total(ly_lbl)
    if not cur or not cur[1]:
        return None
    return {"crop_local": crop_local, "crop": CROPS.get(crop_local, crop_local.title()), "op": op,
            "season": f"{y1}/{y2 % 100:02d}", "dates": dates, "cur": cur, "ly": ly}


def to_row(p, *, source_document=None, source_page=None):
    pcts = p["cur"][1]
    cur = pcts[-1]
    prev = pcts[-2] if len(pcts) >= 2 else 0.0
    ly = p["ly"][1][-1] if p["ly"] and p["ly"][1] else None
    extra = {}
    if source_document and source_page is not None:
        doc = clean_url(source_document)
        page = int(source_page)
        extra = {
            "source_document": doc,
            "source_page": page,
            "source_label": f"{document_name(doc)}, p. {page}",
        }
    return rec(p["crop"], p["op"], cur, prev_week=prev, last_year=ly, region="Argentina",
               crop_local=p["crop_local"].title(), season=p["season"], **extra)


def latest_pdf(s) -> tuple[str, date]:
    today = date.today()
    for back in range(0, 3):
        y, m = today.year, today.month - back
        while m <= 0:
            y, m = y - 1, m + 12
        html = s.get(LIST, params={"mes": f"{y}-{m:02d}"}, timeout=60).text
        hrefs = re.findall(r'href="([^"]*Informe(?:%20|\s)Semanal[^"]*\.pdf)"', html, re.I)
        dated = []
        for h in hrefs:
            d = re.search(r"(\d{2})_(\d{2})_(\d{4})\.pdf", h)
            if d:
                dated.append((date(int(d.group(3)), int(d.group(2)), int(d.group(1))), h))
        if dated:
            d, h = max(dated)
            return (h if h.startswith("http") else BASE + h), d
    raise RuntimeError("no weekly MAGyP report found in last 3 months")


def fetch() -> dict:
    import pdfplumber

    s = session()
    url, rdate = latest_pdf(s)
    url = clean_url(url)
    r = s.get(url, timeout=120)
    r.raise_for_status()
    rows = []
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "AVANCE" not in text.upper():
                continue
            p = parse_page(text)
            if p:
                # page.page_number matches the printed page number in this report.
                rows.append(to_row(p, source_document=url, source_page=page.page_number))
    validate(rows, min_rows=1)
    return payload("ar", "Argentina", "MAGyP Estimaciones Agrícolas (Informe Semanal)", url,
                   rdate.isoformat(), rows, beta=True,
                   notes=["Parsed from the weekly PDF. Cross-check a figure against the cited page if it looks off.",
                          "Last year is the same week of the previous campaign. No 5-year average is published.",
                          "Each row cites the source PDF and the page it was read from."])
