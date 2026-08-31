from geography_catalog import COMMUNES, geography_rows, resolve_commune, resolve_neighborhood


def test_catalog_has_official_caba_division():
    assert len(COMMUNES) == 15
    assert sum(len(items) for items in COMMUNES.values()) == 48
    assert resolve_neighborhood("villa pueyrredon") == "Villa Pueyrredón"
    assert resolve_neighborhood("Palermo Hollywood") == "Palermo"


def test_geography_rows_are_stable_for_clients():
    rows = geography_rows()
    assert rows[0]["slug"] == "caba"
    assert len([row for row in rows if row["level"] == "neighborhood"]) == 48
    assert resolve_commune("comuna-14") == 14
