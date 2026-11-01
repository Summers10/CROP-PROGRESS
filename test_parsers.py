"""Parser tests built from the real layouts of each source (captured Nov 1, 2026)."""
import csv
import io
from datetime import date, timedelta

import ar_magyp, br_conab, fr_cereobs, us_nass

# ---------- Brazil: CONAB xlsx (column A empty, data from column B) ----------
CONAB = [
    [None, "Progresso de safra"],
    [None, "Soja - Safra 2026/27"],
    [None, "(Esses 12 estados correspondem a 95% da área cultivada)"],
    [None, "Semeadura"],
    [None, "Estado", "Semana até:", None, None, "Média  5 anos"],
    [None, None, 2025, 2026],
    [None, None, 45954, 46311, 46318],
    [None, "Mato Grosso", 0.6211, 0.6075, 0.7578, 0.70312],
    [None, "12 estados", 0.34831447982131747, 0.30099999999999999, 0.42761859991005846, 0.40221743857586711],
    [],
    [None, "Trigo - Safra 2026"],
    [None, "Colheita*"],
    [None, "Unidade da Federação", "Semana até:", None, None, "Média 5 anos"],
    [None, None, 2025, 2026],
    [None, None, 45954, 46311, 46318],
    [None, "8 estados", 0.43242136969448436, 0.455, 0.57329116559945859, 0.52655087493601771],
]


def test_conab():
    rd, rows = br_conab.parse_grid(CONAB)
    assert rd == "2026-10-23"
    soy = rows[0]
    assert (soy["crop"], soy["metric"], soy["season"]) == ("Soybeans", "planted", "2026/27")
    assert (soy["current"], soy["prev_week"], soy["last_year"], soy["avg5"]) == (42.8, 30.1, 34.8, 40.2)
    wheat = rows[1]
    assert (wheat["crop"], wheat["metric"], wheat["current"]) == ("Wheat", "harvested", 57.3)


# ---------- France: Céré'Obs xls ----------
FR_STAGE = """Stade de développement
Blé tendre-Semis-France,,,,,,
% de surface- récolte 2027,,,,,,
,Semaine se terminant le ,,,,,
,"26 octobre 2026
 %","19 octobre 2026
 %","26 octobre 2025
 %","Moyenne  2021 - 2025
 %",,
Bretagne,14,2,21,17,,
Ile-de-France,75,25,65,69,,
Moyenne France,62,45,67,59,,
"""
FR_COND = """Conditions culture
Conditions de culture  - Maïs grain - France,,,,,,
% de surface -  récolte 2026,,,,,,
,Semaine 43 se terminant le 26 octobre 2026,,,,,
,"Très mauvaises
 %","Mauvaises
 %","Assez bonnes
 %","Bonnes
 %","Très bonnes
 %",
Grand-Est,8,34,32,26,0,
Moyenne France (1),21,30,27,21,1,
2026-S42 (2),21,30,27,21,1,
2025-S43 (3),5,11,24,55,4,
"""


def grid(text):
    return [r + [""] * (7 - len(r)) for r in csv.reader(io.StringIO(text))]


def test_cereobs_stage():
    stage, v = fr_cereobs.parse_stage(grid(FR_STAGE))
    assert stage == "semis"
    assert v == {"current": 62, "prev_week": 45, "last_year": 67, "avg5": 59}


def test_cereobs_condition():
    res = fr_cereobs.parse_condition(grid(FR_COND))
    assert res["current"]["bonnes"] + res["current"]["très bonnes"] == 22
    assert res["last_year"]["bonnes"] + res["last_year"]["très bonnes"] == 59


# ---------- Argentina: MAGyP PDF text ----------
AR_MAIZE = """22
AVANCE DE LA SIEMBRA DE MAIZ
CAMPAÑA: 2026/2027 (*)
ÁREA
24/09 01/10 08/10 15/10 22/10 29/10
DELEGACIÓN SEMBRADA
26/27 3.336.577 6 9 15 20 24 29
BUENOS AIRES
25/26 3.333.312 1 5 10 14 20 30
26/27 11.465.367 13,13 19,0 27 31 35 37
TOTAL PAÍS
25/26 11.681.664 12,8 19 23 27 31 36
(*) Cifras Provisorias"""

AR_RICE = """AVANCE DE LA SIEMBRA DE ARROZ
CAMPAÑA: 2026/2027 (*)
24/09 01/10 08/10 15/10 22/10 29/10
LF 169.800 22 34 50 60 70 75
26/27 189.300 19 31 46 57 67 72
TOTAL PAÍS
9 18 24 35 50 62
25/26 213.900
(*) Cifras Provisorias"""


def test_magyp_maize():
    row = ar_magyp.to_row(ar_magyp.parse_page(AR_MAIZE))
    assert (row["crop"], row["metric"], row["season"]) == ("Corn", "planted", "2026/27")
    assert (row["current"], row["prev_week"], row["last_year"]) == (37, 35, 36)


def test_magyp_rice_split_line():
    row = ar_magyp.to_row(ar_magyp.parse_page(AR_RICE))
    assert (row["crop"], row["current"], row["prev_week"], row["last_year"]) == ("Rice", 72, 67, 62)


# ---------- US: NASS Quick Stats records ----------
def _qs(crop, unit, we, v, cat="PROGRESS"):
    return {"statisticcat_desc": cat, "short_desc": f"{crop} - {cat}, MEASURED IN {unit}",
            "unit_desc": unit, "week_ending": we.isoformat(), "Value": str(v)}


def test_nass():
    latest = date(2026, 10, 25)
    raw = [_qs("CORN, GRAIN", "PCT HARVESTED", latest, 66),
           _qs("CORN, GRAIN", "PCT HARVESTED", latest - timedelta(7), 52)]
    for k, v in zip(range(1, 6), (60, 50, 55, 65, 70)):
        raw.append(_qs("CORN, GRAIN", "PCT HARVESTED", latest - timedelta(364 * k), v))
    raw += [_qs("WHEAT, WINTER", u, latest, v, "CONDITION") for u, v in
            (("PCT EXCELLENT", 5), ("PCT GOOD", 40), ("PCT FAIR", 35), ("PCT POOR", 15), ("PCT VERY POOR", 5))]
    rd, rows = us_nass.parse(raw)
    assert rd == "2026-10-25"
    corn = next(r for r in rows if r["metric"] == "harvested")
    assert (corn["current"], corn["prev_week"], corn["last_year"], corn["avg5"]) == (66, 52, 60, 60)
    ww = next(r for r in rows if r["metric"] == "condition_ge")
    assert ww["current"] == 45 and ww["crop"] == "Wheat, Winter"


def test_nass_fill_after_season_end():
    # last year's harvest finished (100) two weeks before this week -> carry forward
    latest = date(2026, 11, 22)
    raw = [_qs("SOYBEANS", "PCT HARVESTED", latest, 97),
           _qs("SOYBEANS", "PCT HARVESTED", latest - timedelta(364 + 14), 100)]
    _, rows = us_nass.parse(raw)
    assert rows[0]["last_year"] == 100


def test_nass_interpolates_shutdown_gap():
    # no report for last year's matching week; reports 3 weeks before (40) and 3 weeks after (70)
    latest = date(2026, 10, 25)
    ly = latest - timedelta(364)
    raw = [_qs("CORN, GRAIN", "PCT HARVESTED", latest, 60),
           _qs("CORN, GRAIN", "PCT HARVESTED", ly - timedelta(21), 40),
           _qs("CORN, GRAIN", "PCT HARVESTED", ly + timedelta(21), 70)]
    _, rows = us_nass.parse(raw)
    assert rows[0]["last_year"] == 55
