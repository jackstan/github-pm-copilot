from datetime import datetime, timedelta
import unittest

from eng_health_copilot.ingest import _select_since_for_ingest


class TestIngestIncrementalWindow(unittest.TestCase):
    def test_backfills_when_existing_data_is_too_shallow(self) -> None:
        now = datetime(2026, 2, 8, 12, 0, 0)
        base_since = now - timedelta(days=180)
        incremental_since = now - timedelta(days=2)
        oldest_existing = now - timedelta(days=60)

        since = _select_since_for_ingest(base_since, incremental_since, oldest_existing)
        self.assertEqual(since, base_since)

    def test_uses_incremental_when_existing_data_covers_requested_window(self) -> None:
        now = datetime(2026, 2, 8, 12, 0, 0)
        base_since = now - timedelta(days=90)
        incremental_since = now - timedelta(days=2)
        oldest_existing = now - timedelta(days=180)

        since = _select_since_for_ingest(base_since, incremental_since, oldest_existing)
        self.assertEqual(since, incremental_since)

    def test_backfills_when_no_existing_data(self) -> None:
        now = datetime(2026, 2, 8, 12, 0, 0)
        base_since = now - timedelta(days=90)
        incremental_since = now - timedelta(days=2)

        since = _select_since_for_ingest(base_since, incremental_since, None)
        self.assertEqual(since, base_since)


if __name__ == "__main__":
    unittest.main()
