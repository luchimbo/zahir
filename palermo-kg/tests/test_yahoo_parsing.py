from scrapers.shared.byma_client import select_ars_tickers
from scrapers.shared.db_helpers import SERIES_KEY_RE
from scrapers.shared.yahoo_client import parse_chart, yahoo_symbol
from scrapers.yahoo_equities import observations_for, series_slug


def chart_payload(**overrides):
    result = {
        "meta": {"currency": "ARS", "longName": "Grupo Financiero Galicia S.A.",
                 "fullExchangeName": "Buenos Aires"},
        "timestamp": [0, 86400],
        "indicators": {
            "quote": [{"open": [1.0, 2.0], "high": [3.0, 4.0], "low": [0.5, 1.5],
                       "close": [2.0, 3.0], "volume": [10, 20]}],
            "adjclose": [{"adjclose": [1.8, 2.7]}],
        },
    }
    result.update(overrides)
    return {"chart": {"result": [result], "error": None}}


def test_parse_chart_maps_ohlcv_adjclose_and_epoch():
    meta, rows, dividends, splits = parse_chart(chart_payload())
    assert meta == {"currency": "ARS", "long_name": "Grupo Financiero Galicia S.A.",
                    "exchange": "Buenos Aires"}
    assert len(rows) == 2
    assert rows[0]["date"].isoformat() == "1970-01-01"
    assert rows[1]["date"].isoformat() == "1970-01-02"
    assert rows[1]["close"] == 3.0
    assert rows[0]["adj_close"] == 1.8
    assert (dividends, splits) == ([], [])


def test_parse_chart_omits_missing_values_instead_of_zero_filling():
    """Yahoo deja None en ruedas sin operaciones y a veces acorta las listas de
    indicadores; ninguno de los dos casos es un precio de cero."""
    payload = chart_payload(indicators={
        "quote": [{"open": [1.0, None], "high": [3.0], "low": [0.5, 1.5],
                   "close": [2.0, None], "volume": [10, 20]}],
        "adjclose": [{"adjclose": [1.8]}],
    })
    _, rows, _, _ = parse_chart(payload)
    assert rows[1]["open"] is None
    assert rows[1]["close"] is None
    assert rows[1]["high"] is None       # lista más corta que timestamp
    assert rows[1]["adj_close"] is None
    assert rows[1]["low"] == 1.5


def test_parse_chart_tolerates_missing_or_failed_results():
    for payload in ({"chart": {"result": None, "error": {"code": "Not Found"}}},
                    {"chart": {"result": []}},
                    {"chart": {}},
                    {},
                    None):
        assert parse_chart(payload) == ({}, [], [], [])


def test_parse_chart_without_timestamps_returns_no_rows():
    payload = chart_payload(timestamp=[])
    meta, rows, _, _ = parse_chart(payload)
    assert rows == []
    assert meta["currency"] == "ARS"


def test_parse_chart_reads_dividends_and_splits():
    payload = chart_payload(events={
        "dividends": {"86400": {"amount": 1.25, "date": 86400}},
        "splits": {"0": {"date": 0, "numerator": 2, "denominator": 1, "splitRatio": "2:1"}},
    })
    _, _, dividends, splits = parse_chart(payload)
    assert dividends == [{"date": dividends[0]["date"], "amount": 1.25}]
    assert dividends[0]["date"].isoformat() == "1970-01-02"
    assert splits[0]["ratio"] == 2.0
    assert splits[0]["date"].isoformat() == "1970-01-01"


def test_parse_chart_skips_incomplete_events():
    payload = chart_payload(events={
        "dividends": {"1": {"date": 86400}},                       # sin amount
        "splits": {"2": {"date": 0, "numerator": 2, "denominator": 0}},  # división por cero
    })
    _, _, dividends, splits = parse_chart(payload)
    assert (dividends, splits) == ([], [])


def panel_row(symbol, ccy="ARS", settlement="1", panel="general-equity"):
    return {"symbol": symbol, "denominationCcy": ccy, "settlementType": settlement,
            "securityType": "CS", "securitySubType": "G", "_panel": panel}


def test_select_ars_tickers_dedupes_settlement_types_and_panels():
    rows = [panel_row("GGAL"), panel_row("GGAL", settlement="2"),
            panel_row("GGAL", panel="leading-equity")]
    assert [spec["symbol"] for spec in select_ars_tickers(rows)] == ["GGAL"]


def test_select_ars_tickers_drops_non_ars():
    rows = [panel_row("GGAL"), panel_row("GGALD", ccy="USD"), panel_row("GGALC", ccy="EXT")]
    assert [spec["symbol"] for spec in select_ars_tickers(rows)] == ["GGAL"]


def test_select_ars_tickers_collapses_settlement_classes_onto_their_root():
    """ALUAB/ALUAD y MOLA5 son la misma empresa que ALUA y MOLA."""
    rows = [panel_row(s) for s in ("ALUA", "ALUAB", "ALUAD", "MOLA", "MOLA5", "BMA", "BMA.5")]
    assert [spec["symbol"] for spec in select_ars_tickers(rows)] == ["ALUA", "BMA", "MOLA"]


def test_select_ars_tickers_keeps_species_whose_root_does_not_list():
    """CECO2/DGCU2/TECO2 terminan en dígito pero no son clases; CECOB queda
    porque su raíz 'CECO' no cotiza por separado."""
    rows = [panel_row(s) for s in ("CECO2", "DGCU2", "TECO2", "CECOB", "A3", "A3B")]
    assert [spec["symbol"] for spec in select_ars_tickers(rows)] == [
        "A3", "CECO2", "CECOB", "DGCU2", "TECO2"]


def test_series_slug_is_a_valid_series_key_for_awkward_tickers():
    for symbol in ("BMA.5", "A3", "MOLA5", "CECO2", "GGAL"):
        assert SERIES_KEY_RE.fullmatch(f"yahoo_{series_slug(symbol)}_close")
    assert series_slug("BMA.5") == "bma_5"


def test_yahoo_symbol_replaces_dot_with_dash():
    assert yahoo_symbol("BMA.5") == "BMA-5.BA"
    assert yahoo_symbol("GGAL") == "GGAL.BA"


def test_observations_for_builds_one_point_per_field_and_skips_nulls():
    _, rows, _, _ = parse_chart(chart_payload(indicators={
        "quote": [{"open": [1.0], "high": [3.0], "low": [0.5], "close": [2.0], "volume": [None]}],
        "adjclose": [{"adjclose": [1.8]}],
    }, timestamp=[0]))
    dividends = [{"date": rows[0]["date"], "amount": 1.25}]
    splits = [{"date": rows[0]["date"], "ratio": 2.0, "numerator": 2, "denominator": 1}]

    observations = observations_for("e1", "BMA.5", rows, dividends, splits, "https://origin")
    keys = {obs["series_key"] for obs in observations}
    assert keys == {"yahoo_bma_5_open", "yahoo_bma_5_high", "yahoo_bma_5_low",
                    "yahoo_bma_5_close", "yahoo_bma_5_adj_close",
                    "yahoo_bma_5_dividend", "yahoo_bma_5_split_ratio"}
    assert all(obs["entity_id"] == "e1" for obs in observations)
    by_key = {obs["series_key"]: obs for obs in observations}
    assert by_key["yahoo_bma_5_close"]["unit"] == "ARS"
    assert by_key["yahoo_bma_5_close"]["frequency"] == "daily"
    assert by_key["yahoo_bma_5_dividend"]["frequency"] == "irregular"
    assert by_key["yahoo_bma_5_split_ratio"]["value"] == 2.0
