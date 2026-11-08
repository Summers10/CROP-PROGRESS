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


def test_magyp_source_citation():
    row = ar_magyp.to_row(
        ar_magyp.parse_page(AR_MAIZE),
        source_document="https://example.test/reports/Informe Semanal.pdf",
        source_page=22,
    )
    assert row["source_page"] == 22
    assert row["source_document"] == "https://example.test/reports/Informe%20Semanal.pdf"
    assert row["source_label"] == "Informe Semanal.pdf, p. 22"
    prefixed = ar_magyp.to_row(
        ar_magyp.parse_page(AR_MAIZE),
        source_document="https://example.test/261105_Informe Semanal.pdf",
        source_page=20,
    )
    assert prefixed["source_label"] == "Informe Semanal.pdf, p. 20"
    assert "source_page" not in ar_magyp.to_row(ar_magyp.parse_page(AR_MAIZE))


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
    assert "quality" not in corn and "avg5_observed" not in corn


def test_nass_fill_after_season_end():
    # last year's harvest finished (100) two weeks before this week -> carry forward
    latest = date(2026, 11, 22)
    raw = [_qs("SOYBEANS", "PCT HARVESTED", latest, 97),
           _qs("SOYBEANS", "PCT HARVESTED", latest - timedelta(364 + 14), 100)]
    _, rows = us_nass.parse(raw)
    assert rows[0]["last_year"] == 100
    assert rows[0]["quality"]["last_year"] == "estimated"


def test_nass_interpolates_shutdown_gap():
    # no report for last year's matching week; reports 3 weeks before (40) and 3 weeks after (70)
    latest = date(2026, 10, 25)
    ly = latest - timedelta(364)
    raw = [_qs("CORN, GRAIN", "PCT HARVESTED", latest, 60),
           _qs("CORN, GRAIN", "PCT HARVESTED", ly - timedelta(21), 40),
           _qs("CORN, GRAIN", "PCT HARVESTED", ly + timedelta(21), 70)]
    _, rows = us_nass.parse(raw)
    assert rows[0]["last_year"] == 55
    assert rows[0]["quality"]["last_year"] == "interpolated"


def test_nass_avg_marks_interpolated_component():
    latest = date(2026, 10, 25)
    raw = [_qs("CORN, GRAIN", "PCT HARVESTED", latest, 60)]
    ly = latest - timedelta(364)
    raw += [
        _qs("CORN, GRAIN", "PCT HARVESTED", ly - timedelta(21), 40),
        _qs("CORN, GRAIN", "PCT HARVESTED", ly + timedelta(21), 70),
    ]
    for k, v in ((2, 50), (3, 60), (4, 70)):
        raw.append(_qs("CORN, GRAIN", "PCT HARVESTED", latest - timedelta(364 * k), v))
    _, rows = us_nass.parse(raw)
    corn = rows[0]
    assert corn["last_year"] == 55
    assert corn["quality"]["last_year"] == "interpolated"
    assert corn["quality"]["avg5"] == "interpolated"
    assert corn["avg5"] == 58.8
    assert corn["avg5_observed"] == 60
    assert corn["avg5_observed_n"] == 3


def test_nass_avg_without_enough_observed_years():
    latest = date(2026, 10, 25)
    raw = [_qs("CORN, GRAIN", "PCT HARVESTED", latest, 60)]
    ly = latest - timedelta(364)
    raw += [
        _qs("CORN, GRAIN", "PCT HARVESTED", ly - timedelta(21), 40),
        _qs("CORN, GRAIN", "PCT HARVESTED", ly + timedelta(21), 70),
        _qs("CORN, GRAIN", "PCT HARVESTED", latest - timedelta(364 * 2), 50),
        _qs("CORN, GRAIN", "PCT HARVESTED", latest - timedelta(364 * 3), 60),
    ]
    _, rows = us_nass.parse(raw)
    corn = rows[0]
    assert corn["quality"]["avg5"] == "interpolated"
    assert corn["avg5_observed"] is None
    assert corn["avg5_observed_n"] == 2


def test_nass_before_season_is_estimated():
    latest = date(2026, 6, 7)
    raw = [
        _qs("CORN", "PCT PLANTED", latest, 40),
        _qs("CORN", "PCT PLANTED", latest - timedelta(364) + timedelta(14), 8),
    ]
    _, rows = us_nass.parse(raw)
    assert rows[0]["last_year"] == 0
    assert rows[0]["quality"]["last_year"] == "estimated"


def test_nass_avg_marks_carried_component():
    latest = date(2026, 11, 22)
    raw = [_qs("SOYBEANS", "PCT HARVESTED", latest, 97),
           _qs("SOYBEANS", "PCT HARVESTED", latest - timedelta(364 + 14), 100)]
    for k, v in ((2, 80), (3, 70), (4, 60)):
        raw.append(_qs("SOYBEANS", "PCT HARVESTED", latest - timedelta(364 * k), v))
    _, rows = us_nass.parse(raw)
    soy = rows[0]
    assert soy["last_year"] == 100
    assert soy["quality"]["last_year"] == "estimated"
    assert soy["quality"]["avg5"] == "estimated"
    assert soy["avg5"] == 77.5
    assert soy["avg5_observed"] == 70
    assert soy["avg5_observed_n"] == 3


def test_nass_condition_does_not_invent_zero():
    latest = date(2026, 6, 7)
    raw = [_qs("WHEAT, WINTER", u, latest, v, "CONDITION") for u, v in
           (("PCT EXCELLENT", 10), ("PCT GOOD", 50), ("PCT FAIR", 20), ("PCT POOR", 10), ("PCT VERY POOR", 10))]
    raw += [_qs("WHEAT, WINTER", u, latest - timedelta(364) + timedelta(14), 1, "CONDITION")
            for u in ("PCT EXCELLENT", "PCT GOOD", "PCT FAIR", "PCT POOR", "PCT VERY POOR")]
    _, rows = us_nass.parse(raw)
    row = rows[0]
    assert row["metric"] == "condition_ge" and row["current"] == 60
    assert row["last_year"] is None
    assert "quality" not in row


def test_ui_marks_interpolated_values():
    from pathlib import Path
    html = (Path(__file__).resolve().parent / "index.html").read_text(encoding="utf-8")
    for phrase in (
        'lang="en-CA"',
        "Exclude interpolated and estimated",
        "Interpolated and estimated excluded",
        "not available",
        "interp-tag",
        "est-tag",
        "avg5_observed",
        "Estimated value.",
        "source_page",
        "source_label",
        "2025 US government shutdown",
    ):
        assert phrase in html, phrase
