from scrapers.byma_merval import parse_history_payload as parse_merval
from scrapers.byma_ypf import parse_history_payload as parse_ypf


def test_byma_chart_parser_maps_ohlcv_and_epoch():
    payload = {"s": "ok", "t": [0, 86400], "o": [1, 2], "h": [3, 4], "l": [0, 1], "c": [2, 3], "v": [10, 20]}
    rows = parse_merval(payload)
    assert len(rows) == 2
    assert rows[0]["date"].isoformat() == "1970-01-01"
    assert rows[1]["c"] == 3
    assert parse_ypf({"s": "no_data"}) == []
