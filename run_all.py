"""Run every fetcher independently. A failure in one source never touches the others,
and never overwrites that source's last good data file."""
from __future__ import annotations

import json
import sys
import traceback

from fetchers import ar_magyp, br_conab, fr_cereobs, us_nass
from fetchers.common import DATA, now_iso, write_country

SOURCES = {"us": us_nass, "br": br_conab, "fr": fr_cereobs, "ar": ar_magyp}


def main(only: list[str]) -> int:
    DATA.mkdir(exist_ok=True)
    status_path = DATA / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    failures = 0
    for code, mod in SOURCES.items():
        if only and code not in only:
            continue
        entry = status.get(code, {})
        entry["last_attempt"] = now_iso()
        try:
            data = mod.fetch()
            write_country(code, data)
            entry.update(ok=True, error=None, last_success=data["fetched_at"],
                         report_date=data["report_date"], rows=len(data["rows"]))
            print(f"[ok]   {code}: {len(data['rows'])} rows, report {data['report_date']}")
        except Exception as e:  # noqa: BLE001 – isolate every source
            failures += 1
            entry.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
            print(f"[FAIL] {code}: {e}", file=sys.stderr)
            traceback.print_exc()
        status[code] = entry
    status_path.write_text(json.dumps(status, indent=1))
    return failures


if __name__ == "__main__":
    fails = main(sys.argv[1:])
    # Don't fail the workflow for a single flaky source; data for the others still commits.
    sys.exit(0)
