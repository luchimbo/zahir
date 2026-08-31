from scrapers.shared.contract import SourceResult, bounded
from scrapers.shared.tabular_source import TabularConfig, _in_palermo, parse_rows
from scrapers.source_catalog import SOURCES


def test_source_result_requires_no_errors():
    assert SourceResult(seen=2, accepted=1, written=1).ok
    assert not SourceResult(errors=["bad dataset"]).ok


def test_limit_applies_after_selection():
    assert bounded([1, 2, 3], 2) == [1, 2]
    assert bounded([1], 0) == []


def test_tabular_parser_and_palermo_filter():
    rows = parse_rows(b"nombre,latitud,longitud,barrio\nPlaza, -34.57,-58.42,Palermo\n", "text/csv")
    assert rows[0]["nombre"] == "Plaza"
    assert _in_palermo(rows[0], -34.57, -58.42)
    assert not _in_palermo({"barrio": "Belgrano"}, -34.55, -58.37)


def test_new_sources_are_contract_backed_and_have_safe_pilots():
    expected = {"trenes_sofse", "idecba_comuna", "gcba_ecocircular", "gcba_turismo", "sube_open", "cij_causas", "mpf_delitos", "rpi_consultas", "idecba_alquileres"}
    found = {source.name: source for source in SOURCES}
    assert expected <= found.keys()
    assert all(found[name].supports_contract and found[name].pilot_limit > 0 for name in expected)
