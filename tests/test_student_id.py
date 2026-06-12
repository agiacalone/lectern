"""Tests for lectern.student_id — CSULB student-ID normalization."""
from __future__ import annotations

from lectern.student_id import normalize_student_id, pad_student_id


class TestNormalizeStudentId:
    def test_canonical_9_digit_unchanged(self):
        sid, flags = normalize_student_id("040100001")
        assert sid == "040100001"
        assert flags == []

    def test_excel_truncated_8_digit_repaired_silently(self):
        """The common Excel/Sheets round-trip case: leading zero dropped."""
        sid, flags = normalize_student_id("40100001")
        assert sid == "040100001"
        assert flags == []  # NOT flagged — expected shape from spreadsheet

    def test_csulb_letter_prefix_form(self):
        """Campus Solutions C-prefix: drop letter, pad digits to 9."""
        sid, flags = normalize_student_id("C02962436")
        assert sid == "002962436"
        assert flags == []

    def test_letter_prefix_lowercase(self):
        sid, _ = normalize_student_id("c02962436")
        assert sid == "002962436"

    def test_under_9_digits_flagged(self):
        sid, flags = normalize_student_id("424657")
        assert sid == "000424657"
        assert "malformed_id_6d" in flags

    def test_over_9_digits_flagged(self):
        sid, flags = normalize_student_id("1234567890")
        assert sid == "1234567890"  # preserved for caller diagnosis
        assert "malformed_id_10d" in flags

    def test_empty_input(self):
        sid, flags = normalize_student_id("")
        assert sid == "000000000"
        assert "malformed_id_0d" in flags

    def test_none_safe(self):
        sid, flags = normalize_student_id(None)  # type: ignore[arg-type]
        assert sid == "000000000"
        assert "malformed_id_0d" in flags

    def test_whitespace_stripped(self):
        sid, _ = normalize_student_id("  040100001  ")
        assert sid == "040100001"

    def test_embedded_non_digits_stripped(self):
        sid, _ = normalize_student_id("040-100-001")
        assert sid == "040100001"

    def test_integer_string_from_pandas_or_excel(self):
        """Pandas/Excel may stringify the int 40100001 (no leading zero)."""
        sid, flags = normalize_student_id(str(40100001))
        assert sid == "040100001"
        assert flags == []


class TestPadStudentId:
    def test_returns_string_only(self):
        assert pad_student_id("40100001") == "040100001"

    def test_canonical_unchanged(self):
        assert pad_student_id("040100001") == "040100001"

    def test_empty(self):
        assert pad_student_id("") == "000000000"
