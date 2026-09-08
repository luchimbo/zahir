import pytest

from scrapers.shared.db_helpers import bulk_upsert_observations, observation_record_key


class FakeConnection:
    def __init__(self, existing=()):
        self.existing = set(existing)
        self.rows = []

    async def fetch(self, _sql, *_args):
        return [{"record_key": key} for key in self.existing]

    async def executemany(self, _sql, rows):
        self.rows.extend(rows)
        return len(rows)


def test_observation_hash_is_canonical_and_tracks_revision():
    first = observation_record_key("byma_merval_close", "2026-09-08", {"c": 10, "t": 1})
    assert first == observation_record_key("byma_merval_close", "2026-09-08", {"t": 1, "c": 10})
    assert first != observation_record_key("byma_merval_close", "2026-09-08", {"c": 11, "t": 1})


@pytest.mark.asyncio
async def test_bulk_observations_reports_only_new_rows():
    observation = {"entity_id": "entity", "series_key": "bcra_var_1", "observed_at": "2026-09-08",
                   "observed_period": "2026-09-08", "frequency": "daily", "value": 1,
                   "payload": {"valor": 1}, "origins": ["https://example.test"]}
    key = observation_record_key("bcra_var_1", "2026-09-08", {"valor": 1})
    conn = FakeConnection(existing=[key])
    assert await bulk_upsert_observations(conn, [observation], "source") == 0
    assert len(conn.rows) == 1  # igual actualiza last_seen_at
    with pytest.raises(ValueError, match="series_key"):
        await bulk_upsert_observations(conn, [{**observation, "series_key": "BAD KEY"}], "source")
    with pytest.raises(ValueError, match="frequency"):
        await bulk_upsert_observations(conn, [{**observation, "frequency": "hourly"}], "source")
