from datetime import datetime, timedelta, timezone

from scrapers.source_catalog import SOURCES, SourceSpec
from scripts.run_sources import is_due


def test_paid_sources_are_not_publicly_enabled_by_default():
    paid = [source for source in SOURCES if source.cost_policy != "free"]
    assert paid
    assert all(source.mode in {"credential", "approval"} for source in paid)


def test_every_source_has_operational_policy():
    assert all(source.data_class in {"current", "historical", "aggregate", "contextual"} for source in SOURCES)
    assert all(source.refresh_schedule for source in SOURCES)


def test_scheduled_refresh_selects_only_expired_free_public_sources():
    source = SourceSpec("test", "scrapers.test", "https://example.test", 1, "public", "test", refresh_schedule="weekly")
    now = datetime(2026, 8, 3, tzinfo=timezone.utc)
    assert is_due(source, None, now)
    assert not is_due(source, now - timedelta(days=6), now)
    assert is_due(source, now - timedelta(days=7), now)


def test_scheduled_refresh_does_not_enable_paid_or_approval_sources():
    paid = SourceSpec("test", "scrapers.test", "https://example.test", 1, "credential", "test", refresh_schedule="daily", cost_policy="paid")
    approval = SourceSpec("test", "scrapers.test", "https://example.test", 1, "approval", "test", refresh_schedule="daily", cost_policy="free")
    assert not is_due(paid, None)
    assert not is_due(approval, None)


def test_new_official_public_sources_are_registered_for_automation():
    names = {source.name for source in SOURCES}
    assert {"gcba_parcels", "gcba_urban_documents", "gcba_productoras", "gcba_sports"} <= names


def test_source_pilots_are_opt_in_contracts():
    assert all(source.pilot_limit > 0 for source in SOURCES)


def test_national_financial_sources_are_explicit_and_contract_backed():
    sources = {source.name: source for source in SOURCES}
    expected = {"byma_merval", "byma_ypf", "ambito_merval", "ambito_ypf", "bcra_estadisticas", "bcra_comunicaciones"}
    assert expected <= sources.keys()
    assert all(sources[name].territory == "national" and sources[name].supports_contract for name in expected)
