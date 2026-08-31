from scrapers.shared.geo_scope import point_in_caba, record_in_scope


def test_caba_scope_keeps_city_and_rejects_conurbano_points():
    assert point_in_caba(-34.6037, -58.3816)
    assert not point_in_caba(-34.7000, -58.6500)


def test_scope_accepts_official_row_without_coordinates():
    assert record_in_scope(row_neighborhood="Villa Pueyrredon", scope="caba")
    assert record_in_scope(row_neighborhood="Villa Pueyrredon", scope="caba", commune=12)
    assert not record_in_scope(row_neighborhood="Villa Pueyrredon", scope="caba", commune=14)
    assert record_in_scope(row_neighborhood="Palermo", scope="palermo")
