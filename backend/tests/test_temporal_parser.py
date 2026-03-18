import sys
from datetime import date
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.temporal_parser import extract_date, extract_duration_minutes


class TemporalParserDurationTests(unittest.TestCase):
    def test_word_hour_variants(self):
        self.assertEqual(extract_duration_minutes("for one hour"), 60)
        self.assertEqual(extract_duration_minutes("an hour"), 60)
        self.assertEqual(extract_duration_minutes("two hours"), 120)

    def test_half_and_quarter(self):
        self.assertEqual(extract_duration_minutes("half an hour"), 30)
        self.assertEqual(extract_duration_minutes("quarter hour"), 15)

    def test_and_a_half(self):
        self.assertEqual(extract_duration_minutes("one and a half hours"), 90)
        self.assertEqual(extract_duration_minutes("2 and a half hours"), 150)

    def test_word_minutes(self):
        self.assertEqual(extract_duration_minutes("five minutes"), 5)
        self.assertEqual(extract_duration_minutes("twelve minutes"), 12)

    def test_ordinal_day(self):
        self.assertEqual(extract_date("18th", today=date(2026, 3, 17)), "2026-03-18")


if __name__ == "__main__":
    unittest.main()
