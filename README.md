# Crop Progress Terminal

Weekly planting, harvest and crop-condition tracker for the US, Brazil, France and Argentina.
It's a static GitHub Pages site. A GitHub Actions cron fetches the official data server-side and
commits clean JSON to `data/`.

## Sources

| Code | Country | Source | Format | Released | Reliability |
|---|---|---|---|---|---|
| `us` | United States | USDA NASS Crop Progress (Quick Stats API) | JSON API | Mon 4pm ET | High |
| `br` | Brazil | CONAB *Progresso de Safra* | Weekly .xlsx | Mon | High |
| `fr` | France | FranceAgriMer Céré'Obs (public API) | Weekly .xls | Fri | High |
| `ar` | Argentina | MAGyP *Informe Semanal* | PDF | Thu | **Beta** (parsed from PDF) |

The Buenos Aires Grain Exchange (BAGE) was left out because its site is behind Cloudflare bot
protection, so it can't be fetched reliably. MAGyP is the official alternative.

## How reliability is handled

- **Each source runs separately.** If one fails, the others still update.
- **Bad data is never saved.** Every parse is checked for values between 0 and 100 and for a
  non-empty result. If a check fails, the last good file is kept and the error appears on the
  page as **LAST RUN FAILED**.
- **Old reports are flagged.** A report more than 10 days old is tagged **STALE**. This is
  normal in the off-season.
- **Parser tests run first.** The tests use the real layout of each source and run before
  every fetch, so a broken parser is caught before it touches the data.
- **History is kept.** Every report is added to `data/history/<code>.csv`, so you build your
  own archive over time.

## Setup (about 5 minutes)

1. Create a new GitHub repo (for example `crop-progress-terminal`) and push these files.
2. Get a free NASS API key at https://quickstats.nass.usda.gov/api. Then go to
   **Settings → Secrets and variables → Actions → New secret** and save it as `NASS_API_KEY`.
3. Go to **Settings → Pages** and set the source to **Deploy from branch**, `main`, `/ (root)`.
4. Go to **Actions → Update crop progress data → Run workflow**. This runs the first fetch.
5. Open `https://<your-user>.github.io/crop-progress-terminal/`.

## Run locally

```bash
pip install -r requirements.txt
python -m pytest -q
NASS_API_KEY=xxxx python run_all.py          # all sources
python run_all.py br fr                       # just some sources
python -m http.server  # then open http://localhost:8000
```

## Data format (`data/<code>.json`)

```json
{ "code": "br", "report_date": "2026-10-23", "source_url": "...", "beta": false,
  "rows": [ { "crop": "Soybeans", "season": "2026/27", "region": "Brazil (12 estados)",
              "metric": "planted", "current": 42.8, "prev_week": 30.1,
              "last_year": 34.8, "avg5": 40.2 } ] }
```

- `metric` is one of `planted`, `emerged`, `harvested`, or `condition_ge` (% good + excellent),
  or another crop stage name.
- `condition_ge` rows also carry `dist`, the full condition breakdown:
  `vp` (very poor), `pr` (poor), `fr` (fair), `gd` (good), `ex` (excellent).

## Notes on comparisons

- **US:** NASS doesn't publish the 5-yr average through the API. It is calculated here from
  history, matched to the same calendar week. Expect small differences (about 1 point or less)
  from the printed NASS report, which interpolates.
- **Brazil and France:** last year and the 5-yr average are taken directly from the agency's
  file.
- **Argentina:** MAGyP publishes the same week of the previous campaign but no 5-yr average.

## Roadmap

- **v2:**
  - Canadian provincial crop reports (Saskatchewan, Manitoba, Alberta) for the 2027 season.
  - GEOGLAM Crop Monitor for the EU, Black Sea and Australia.
  - US state-level drill-down.
- **Charts:** week-by-week progress curves from the `data/history` files.
