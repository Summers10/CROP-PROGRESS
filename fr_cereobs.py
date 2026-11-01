"""France – FranceAgriMer Céré'Obs weekly crop progress & conditions.

Uses the public JSON API behind cereobs.franceagrimer.fr, which lists the
weekly national publications; each has an .xls we parse.
"""
from __future__ import annotations

import re

from common import payload, rec, session, validate

BASE = "https://cereobs.franceagrimer.fr/cereobs-sp/api/public/"
SITE = "https://cereobs.franceagrimer.fr/cereobs-sp/"

CROPS = {"Blé tendre": "Soft wheat", "Orge d'hiver": "Winter barley", "Blé dur": "Durum wheat",
         "Orge de printemps": "Spring barley", "Maïs grain": "Grain corn"}
STAGES = {"semis": "planted", "levée": "emerged", "récolte": "harvested", "épiaison": "headed",
          "floraison": "flowering", "épi 1 cm": "ear 1 cm", "2 noeuds": "2 nodes",
          "début tallage": "tillering", "6-8 feuilles": "6-8 leaves", "floraison femelle": "silking"}


def _s(v):
    return re.sub(r"\s+", " ", str(v)).strip() if v not in (None, "") else ""


def _n(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_stage(grid) -> tuple[str, dict]:
    """Stage sheet: title 'Blé tendre-Semis-France'; columns
    [region, this week, last week, same week last year, 5-yr avg]."""
    stage, cols = None, None
    for row in grid:
        a = _s(row[0]) if row else ""
        if stage is None and a.endswith("-France") and a.count("-") >= 2 and not a.lower().startswith("ile-de"):
            stage = a.rsplit("-", 2)[1].strip().lower()
        heads = [_s(c).lower() for c in row]
        if any(h.startswith("moyenne") and re.search(r"\d{4}\s*-\s*\d{4}", h) for h in heads):
            cols = heads
        if a.lower().startswith("moyenne france"):
            if not cols or "moyenne" not in cols[4]:
                raise ValueError("unexpected Céré'Obs stage layout")
            vals = [_n(row[i]) for i in range(1, 5)]
            return stage, dict(zip(("current", "prev_week", "last_year", "avg5"), vals))
    raise ValueError("no 'Moyenne France' row")


def parse_condition(grid) -> dict:
    """Condition sheet: columns Très mauvaises/Mauvaises/Assez bonnes/Bonnes/Très bonnes;
    rows 'Moyenne France (1)', '<prev week> (2)', '<last year> (3)'."""
    idx, res = None, {}
    for row in grid:
        heads = [_s(c).lower().replace("%", "").strip() for c in row]
        if "bonnes" in heads and "très bonnes" in heads:
            idx = {k: heads.index(k) for k in ("très mauvaises", "mauvaises", "assez bonnes", "bonnes", "très bonnes")}
            continue
        if not idx or not row:
            continue
        a = _s(row[0])
        tag = re.search(r"\((\d)\)\s*$", a)
        if not tag:
            continue
        d = {k: _n(row[i]) for k, i in idx.items()}
        res[{"1": "current", "2": "prev_week", "3": "last_year"}[tag.group(1)]] = d
    if "current" not in res:
        raise ValueError("no national condition row")
    return res


def _xls(s, pub_id):
    import xlrd

    r = s.get(BASE + "publications/rapportExcel", params={"idPublication": pub_id}, timeout=60)
    r.raise_for_status()
    book = xlrd.open_workbook(file_contents=r.content)
    sh = book.sheet_by_index(0)
    return [sh.row_values(i) for i in range(sh.nrows)]


def _latest_xls(pubs):
    """Keep only national XLS publications from the most recent observation week."""
    xls = [p for p in pubs if (p.get("typePublication") or {}).get("format") == "XLS"
           and p.get("region") is None and p.get("zpc") is None]
    if not xls:
        return []
    wk = max(p["semaineObservation"]["dateFin"] for p in xls)
    return [p for p in xls if p["semaineObservation"]["dateFin"] == wk]


def fetch() -> dict:
    s = session()
    cultures = s.get(BASE + "culturesRetenues", params={"sort": "ordreInteret", "ordreInteret.dir": "asc"},
                     timeout=60).json()
    rows, report = [], None
    for c in cultures:
        name = c["libelleCulture"]
        crop = CROPS.get(name, name)
        for p in _latest_xls(s.get(BASE + "publications/getPublicationsStadeDev",
                                   params={"libelleCulture": name}, timeout=60).json()):
            stage, v = parse_stage(_xls(s, p["id"]))
            report = max(report or "", p["semaineObservation"]["dateFin"][:10])
            rows.append(rec(crop, STAGES.get(stage, stage), v["current"], prev_week=v["prev_week"],
                            last_year=v["last_year"], avg5=v["avg5"], region="France", crop_local=name))
        for p in _latest_xls(s.get(BASE + "publications/getPublicationsCondCulture",
                                   params={"libelleCulture": name}, timeout=60).json()):
            res = parse_condition(_xls(s, p["id"]))
            report = max(report or "", p["semaineObservation"]["dateFin"][:10])

            def ge(d):
                return None if not d else (d["bonnes"] or 0) + (d["très bonnes"] or 0)
            cur = res["current"]
            rows.append(rec(crop, "condition_ge", ge(cur), prev_week=ge(res.get("prev_week")),
                            last_year=ge(res.get("last_year")), region="France", crop_local=name,
                            dist={"vp": cur["très mauvaises"], "pr": cur["mauvaises"], "fr": cur["assez bonnes"],
                                  "gd": cur["bonnes"], "ex": cur["très bonnes"]}))
    validate(rows, min_rows=1)
    return payload("fr", "France", "FranceAgriMer Céré'Obs", SITE, report, rows,
                   notes=["Week-ending date shown (Céré'Obs publishes Fridays).",
                          "Condition = % Bonnes + Très bonnes (good + excellent). Céré'Obs stops updating a "
                          "region's condition once its harvest passes 50%."])
