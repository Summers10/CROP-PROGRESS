"""Brazil – CONAB weekly "Progresso de Safra" (planting & harvest by state).

Index page lists weekly folders; each folder has a 'Plantio e Colheita' .xlsx.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta

from common import payload, rec, session, validate

INDEX = "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/progresso-de-safra"

CROPS = {
    "soja": "Soybeans", "milho 1ª": "Corn (1st crop)", "milho 2ª": "Corn (2nd crop / safrinha)",
    "milho 3ª": "Corn (3rd crop)", "arroz": "Rice", "algodão": "Cotton", "trigo": "Wheat",
    "feijão 1ª": "Dry beans (1st)", "feijão 2ª": "Dry beans (2nd)", "feijão 3ª": "Dry beans (3rd)",
    "sorgo": "Sorghum", "cevada": "Barley", "aveia": "Oats",
}
OPS = {"semeadura": "planted", "plantio": "planted", "colheita": "harvested"}

TITLE_RE = re.compile(r"^(.+?)\s*-\s*Safra\s+(\d{4}(?:/\d{2,4})?)", re.I)
TOTAL_RE = re.compile(r"^\d+\s+estados?$", re.I)


def _excel_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 30000 < v < 80000:
        return date(1899, 12, 30) + timedelta(days=int(v))
    return None


def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


def parse_grid(grid: list[list]) -> tuple[str, list[dict]]:
    """grid: rows of cell values (row[0] = column A). Returns (report_date, rows)."""
    out, crop, season, op, cols, report = [], None, None, None, None, None

    def cell(row, i):
        return row[i] if i < len(row) else None

    for row in grid:
        b = cell(row, 1)
        text = str(b).strip() if b is not None else ""
        m = TITLE_RE.match(text)
        if m:
            crop_local, season = m.group(1).strip(), m.group(2)
            crop = CROPS.get(crop_local.lower(), crop_local)
            op = cols = None
            continue
        key = text.rstrip("*").strip().lower()
        if key in OPS:
            op, cols = OPS[key], None
            continue
        # date row: columns C,D,E hold week-ending dates
        dates = [_excel_date(cell(row, i)) for i in (2, 3, 4)]
        if not text and all(dates):
            cur = max(dates)
            report = max(report, cur) if report else cur
            cols = {}
            for i, d in zip((2, 3, 4), dates):
                if d == cur:
                    cols["current"] = i
                elif (cur - d).days > 200:
                    cols["last_year"] = i
                else:
                    cols["prev_week"] = i
            cols["avg5"] = 5
            continue
        if crop and op and cols and TOTAL_RE.match(text):
            vals = {k: _num(cell(row, i)) for k, i in cols.items()}
            pct = {k: (None if v is None else v * 100) for k, v in vals.items()}
            out.append(rec(crop, op, pct.get("current"), prev_week=pct.get("prev_week"),
                           last_year=pct.get("last_year"), avg5=pct.get("avg5"),
                           region=f"Brazil ({text})", crop_local=crop_local, season=season))
    return (report.isoformat() if report else None), out


def latest_xlsx_url(s) -> str:
    html = s.get(INDEX, timeout=60).text
    folders = re.findall(r'href="(' + re.escape(INDEX) + r'/acompanhamento-das-lavouras-[^"/]+)', html)
    if not folders:
        raise RuntimeError("no weekly folders found on CONAB index page")
    for folder in dict.fromkeys(folders):        # newest first, de-duplicated
        page = s.get(folder, timeout=60)
        links = re.findall(r'href="([^"]*plantio[^"]*\.xlsx[^"]*)"', page.text, re.I)
        if links:
            url = links[0]
            url = url if url.startswith("http") else folder.rstrip("/") + "/" + url.lstrip("/")
            # Plone links point at a "/view" page; the file itself is at the bare .xlsx URL
            return re.sub(r"(\.xlsx)/(view|@@.*)$", r"\1", url, flags=re.I)
    raise RuntimeError("no 'plantio e colheita' xlsx found in recent CONAB folders")


def fetch() -> dict:
    import openpyxl

    s = session()
    url = latest_xlsx_url(s)
    r = s.get(url, timeout=90)
    r.raise_for_status()
    if not r.content.startswith(b"PK"):           # got an HTML page, try Plone's download view
        r = s.get(url + "/@@download/file", timeout=90)
        r.raise_for_status()
        if not r.content.startswith(b"PK"):
            raise RuntimeError(f"CONAB link is not an xlsx file: {url}")
    wb = openpyxl.load_workbook(io.BytesIO(r.content), data_only=True, read_only=True)
    ws = wb.worksheets[0]
    grid = [list(row) for row in ws.iter_rows(values_only=True)]
    report_date, rows = parse_grid(grid)
    validate(rows, min_rows=1)
    return payload("br", "Brazil", "CONAB Progresso de Safra", url, report_date, rows,
                   notes=["National = sum of the main producing states listed by CONAB.",
                          "Harvest % is relative to area planted to date."])
