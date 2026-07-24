from scrapers.source_catalog import SOURCES


def test_paid_sources_are_not_publicly_enabled_by_default():
    paid = [source for source in SOURCES if source.cost_policy != "free"]
    assert paid
    assert all(source.mode in {"credential", "approval"} for source in paid)


def test_every_source_has_operational_policy():
    assert all(source.data_class in {"current", "historical", "aggregate", "contextual"} for source in SOURCES)
    assert all(source.refresh_schedule for source in SOURCES)
