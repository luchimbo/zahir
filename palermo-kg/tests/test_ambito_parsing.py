from datetime import date

from scrapers.ambito_series import parse_ddmmyyyy, parse_es_number, parse_history_response, year_chunks


def test_parse_es_number_handles_es_ar_format_and_raw_json_numbers():
    assert parse_es_number("3.126.275,37") == 3126275.37
    assert parse_es_number("-0,60") == -0.6
    assert parse_es_number("") is None
    assert parse_es_number(None) is None
    # Ámbito a veces devuelve un valor ya como int/float JSON crudo en vez
    # del string formateado es-AR habitual (visto en filas de 2025).
    assert parse_es_number(0) == 0.0
    assert parse_es_number(12.5) == 12.5


def test_parse_ddmmyyyy():
    assert parse_ddmmyyyy("30-01-2024") == date(2024, 1, 30)


def test_parse_history_response_maps_headers_to_rows():
    sample = [
        ["Fecha", "Apertura", "Ultimo", "Var %", "Max.", "Min."],
        ["30-01-2024", "1.253.607,96", "1.271.673,16", "1,44", "1.278.752,49", "1.253.607,96"],
    ]
    rows = parse_history_response(sample)
    assert len(rows) == 1
    assert rows[0]["date"] == date(2024, 1, 30)
    assert rows[0]["close"] == 1271673.16
    assert rows[0]["open"] == 1253607.96
    assert rows[0]["var_pct"] == 1.44


def test_parse_history_response_handles_empty_or_header_only():
    assert parse_history_response([]) == []
    assert parse_history_response([["Fecha", "Apertura", "Ultimo", "Var %", "Max.", "Min."]]) == []


def test_year_chunks_splits_by_calendar_year():
    chunks = year_chunks(date(2022, 6, 1), date(2024, 3, 15))
    assert chunks[0] == (date(2022, 6, 1), date(2022, 12, 31))
    assert chunks[1] == (date(2023, 1, 1), date(2023, 12, 31))
    assert chunks[-1] == (date(2024, 1, 1), date(2024, 3, 15))
