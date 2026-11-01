"""United States – USDA NASS Crop Progress & Condition via the Quick Stats API.

Needs a free key: https://quickstats.nass.usda.gov/api  -> secret NASS_API_KEY
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from .common import env, payload, rec, session, validate

API = "https://quickstats.nass.usda.gov/api/api_GET/"
SOURCE_URL = "https://www.nass.usda.gov/Publications/National_Crop_Progress/"

STAGE_MAP = {
    "PLANTED": "planted", "EMERGED": "emerged", "HARVESTED": "harvested",
    "SILKING": "silking", "DOUGH": "dough", "DENTED": "dented", "MATURE": "mature",
    "BLOOMING": "blooming", "SETTING PODS": "setting pods", "DROPPING LEAVES": "dropping leaves",
    "HEADED": "headed", "COLORING": "coloring", "SQUARING": "squaring",
    "SETTING BOLLS": "setting bolls", "BOLLS OPENING": "bolls opening",
    "JOINTED": "jointed", "BOOTED": "booted", "HEADED OUT": "headed",
}

CONDITION_UNITS = {"PCT EXCELLENT": "ex", "PCT GOOD": "gd", "PCT FAIR": "fr",
                   "PCT POOR": "pr", "PCT VERY POOR": "vp"}


def crop_label(short_desc: str) -> str:
    # "CORN, GRAIN - PROGRESS, MEASURED IN PCT HARVESTED" -> "Corn, Grain"
    return short_desc.split(" - ")[0].title()


def _get(s, key, **params):
    params = {"key": key, "format": "JSON", "source_desc": "SURVEY",
              "sector_desc": "CROPS", "agg_level_desc": "NATIONAL", **params}
    r = s.get(API, params=params, timeout=90)
    if r.status_code == 400 and "exceeds limit" in r.text.lower():
        raise RuntimeError("Quick Stats row limit exceeded – narrow the query")
    r.raise_for_status()
    return r.json().get("data", [])


def _val(v):
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None   # "(D)", "(NA)" etc.


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _nearest(series: dict[date, float], target: date, tol_days=4, fill=False):
    """Value reported closest to `target` (within tol_days).
    With fill=True, also handles weeks outside that year's reporting window:
    before the first report of the season -> 0, after the last -> last value
    (e.g. harvest finished and NASS stopped reporting)."""
    best = None
    for d, v in series.items():
        if abs((d - target).days) <= tol_days and (best is None or abs((d - target).days) < abs((best[0] - target).days)):
            best = (d, v)
    if best or not fill:
        return best[1] if best else None
    before = [d for d in series if target - timedelta(days=70) <= d < target]
    after = [d for d in series if target < d <= target + timedelta(days=70)]
    if before and not after:
        return series[max(before)]
    if after and not before:
        return 0.0
    return None


def parse(rows: list[dict], today: date | None = None) -> tuple[str, list[dict]]:
    """rows: raw Quick Stats records for PROGRESS and CONDITION (5+ years).
    Returns (report_date, normalized rows). 5-yr average and last year are
    computed from history by matching week-ending dates (±4 days), which is
    how USDA's tables line up week-to-week."""
    prog = defaultdict(dict)   # (crop, stage) -> {week_ending: value}
    cond = defaultdict(lambda: defaultdict(dict))  # crop -> week -> {bucket: value}
    for r in rows:
        if not r.get("week_ending"):
            continue
        cat = r.get("statisticcat_desc")
        v = _val(r.get("Value"))
        if v is None:
            continue
        we = _d(r["week_ending"])
        crop = crop_label(r["short_desc"])
        unit = r.get("unit_desc", "")
        if cat == "PROGRESS" and unit.startswith("PCT "):
            stage = unit[4:]
            prog[(crop, STAGE_MAP.get(stage, stage.lower()))][we] = v
        elif cat == "CONDITION" and unit in CONDITION_UNITS:
            cond[crop][we][CONDITION_UNITS[unit]] = v

    all_weeks = [w for s in prog.values() for w in s] + [w for c in cond.values() for w in c]
    if not all_weeks:
        return None, []
    latest = max(all_weeks)
    out = []

    for (crop, stage), series in sorted(prog.items()):
        if latest not in series:
            continue  # not active this week
        cur = series[latest]
        prev = _nearest(series, latest - timedelta(days=7), 1)
        ly = _nearest(series, latest - timedelta(days=364), fill=True)
        hist = [_nearest(series, latest - timedelta(days=364 * k), fill=True) for k in range(1, 6)]
        hist = [h for h in hist if h is not None]
        avg5 = sum(hist) / len(hist) if len(hist) == 5 else None
        out.append(rec(crop, stage, cur, prev_week=prev, last_year=ly, avg5=avg5, region="United States"))

    def ge(d):
        return (d.get("gd") or 0) + (d.get("ex") or 0) if d else None

    for crop, weeks in sorted(cond.items()):
        if latest not in weeks:
            continue
        cur = weeks[latest]
        series_ge = {w: ge(d) for w, d in weeks.items()}
        prev = _nearest(series_ge, latest - timedelta(days=7), 1)
        ly = _nearest(series_ge, latest - timedelta(days=364))
        hist = [_nearest(series_ge, latest - timedelta(days=364 * k)) for k in range(1, 6)]
        hist = [h for h in hist if h is not None]
        avg5 = sum(hist) / len(hist) if len(hist) == 5 else None
        out.append(rec(crop, "condition_ge", ge(cur), prev_week=prev, last_year=ly, avg5=avg5,
                       region="United States", dist=cur))
    return latest.isoformat(), out


def fetch() -> dict:
    key = env("NASS_API_KEY")
    if not key:
        raise RuntimeError("NASS_API_KEY secret not set")
    s = session()
    y0 = date.today().year - 6
    raw = []
    for cat in ("PROGRESS", "CONDITION"):
        raw += _get(s, key, statisticcat_desc=cat, year__GE=str(y0))
    report_date, rows = parse(raw)
    validate(rows, min_rows=2)
    return payload("us", "United States", "USDA NASS Crop Progress", SOURCE_URL, report_date, rows,
                   notes=["Week-ending date shown. Last year / 5-yr avg matched to the same calendar week.",
                          "Condition = % Good + Excellent."])
