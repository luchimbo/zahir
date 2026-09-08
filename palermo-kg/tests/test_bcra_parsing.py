from scrapers.bcra_estadisticas import frequency_for, parse_cotizaciones, parse_monetarias_detalle


def test_bcra_parsers_tolerate_missing_results_and_keep_frequency():
    assert parse_monetarias_detalle({}) == []
    assert frequency_for({"periodicidad": "M"}) == "monthly"
    assert parse_cotizaciones({"results": [{"fecha": "2026-09-08", "detalle": [{"codigoMoneda": "USD", "tipoCotizacion": 1}]}]}) == [{"fecha": "2026-09-08", "codigoMoneda": "USD", "tipoCotizacion": 1}]
