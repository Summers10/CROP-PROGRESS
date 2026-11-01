"""Shared helpers: HTTP session, normalized record format, validation, output."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY = DATA / "history"

UA = "Mozilla/5.0 (crop-progress-terminal; +https://github.com) python-requests"


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = UA
    return s


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rec(crop, metric, current, *, prev_week=None, last_year=None, avg5=None,
        region="National", crop_local=None, season=None, dist=None):
    """One normalized row. Percentages are 0-100 floats (or None)."""
    def r(v):
        return None if v is None else round(float(v), 1)
    out = {
        "crop": crop,
        "crop_local": crop_local,
        "season": season,
        "region": region,
        "metric": metric,          # planted | emerged | harvested | condition_ge | <other stage>
        "current": r(current),
        "prev_week": r(prev_week),
        "last_year": r(last_year),
        "avg5": r(avg5),
    }
    if dist:
        out["dist"] = {k: r(v) for k, v in dist.items()}
    return out


class ValidationError(Exception):
    pass


def validate(rows: list[dict], min_rows: int = 1) -> None:
    """Reject obviously broken parses so we never overwrite good data with junk."""
    if len(rows) < min_rows:
        raise ValidationError(f"only {len(rows)} rows parsed (need >= {min_rows})")
    for row in rows:
        for k in ("current", "prev_week", "last_year", "avg5"):
            v = row.get(k)
            if v is not None and not (0 <= v <= 100):
                raise ValidationError(f"{row['crop']} {row['metric']} {k}={v} outside 0-100")
        if row["current"] is None:
            raise ValidationError(f"{row['crop']} {row['metric']} has no current value")


def write_country(code: str, payload: dict) -> Path:
    DATA.mkdir(exist_ok=True)
    path = DATA / f"{code}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    append_history(code, payload)
    return path


def append_history(code: str, payload: dict) -> None:
    """Append national rows to data/history/<code>.csv, de-duplicated by report date."""
    import csv

    HISTORY.mkdir(parents=True, exist_ok=True)
    path = HISTORY / f"{code}.csv"
    fields = ["report_date", "crop", "season", "region", "metric", "current", "last_year", "avg5"]
    existing = set()
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing.add((r["report_date"], r["crop"], r["region"], r["metric"]))
    new = []
    for r in payload["rows"]:
        key = (payload["report_date"], r["crop"], r["region"], r["metric"])
        if key not in existing:
            new.append({k: (payload["report_date"] if k == "report_date" else r.get(k)) for k in fields})
    if not new:
        return
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            w.writeheader()
        w.writerows(new)


def payload(code, name, source, source_url, report_date, rows, notes=None, beta=False):
    return {
        "code": code,
        "country": name,
        "source": source,
        "source_url": source_url,
        "report_date": report_date,
        "fetched_at": now_iso(),
        "beta": beta,
        "notes": notes or [],
        "rows": rows,
    }


def env(name: str) -> str | None:
    v = os.environ.get(name)
    return v.strip() if v else None


def polite_sleep(sec: float = 1.0) -> None:
    time.sleep(sec)
