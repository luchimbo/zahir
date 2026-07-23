from scrapers.igj import period_from_name, polygon_contains, resource_order, subtype_name


def test_periodo_extraido_de_csv_mensual():
    assert period_from_name("igj-domicilios-202512.csv") == "2025-12"
    assert period_from_name("sin_fecha.csv") == "unknown"


def test_poligono_admite_interior_y_rechaza_exterior():
    polygon = {"type": "Polygon", "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]]}
    assert polygon_contains((0, 0), polygon)
    assert not polygon_contains((2, 0), polygon)


def test_orden_de_recursos_es_historico():
    old = {"name": "IGJ - 2016 semestre 2", "url": "https://example.test/old.zip"}
    new = {"name": "IGJ - 2026 semestre 1", "url": "https://example.test/new.zip"}
    assert resource_order(old) < resource_order(new)


def test_subtipo_es_snake_case():
    assert subtype_name("SOCIEDAD DE RESPONSABILIDAD LIMITADA") == "sociedad_de_responsabilidad_limitada"
