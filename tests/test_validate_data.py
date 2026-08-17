from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

from validate_data import DataValidationError, validate_data, validate_or_raise


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "full_data.json"


def full_data() -> dict:
    with FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


class DataSchemaTests(unittest.TestCase):
    def test_full_fixture_is_valid_and_unknown_fields_are_preserved(self) -> None:
        data = full_data()
        snapshot = copy.deepcopy(data)

        self.assertEqual([], validate_data(data))
        self.assertIs(data, validate_or_raise(data))
        self.assertEqual(snapshot, data)
        self.assertEqual("must survive", data["arr_series"]["companies"][0]["future_company_field"])
        self.assertIn("future_root_field", data)

    def test_missing_nested_build_field_is_reported(self) -> None:
        data = full_data()
        del data["cost"]["alphasense"]["rows"][0]["quality"]

        errors = validate_data(data)

        self.assertTrue(
            any("$.cost.alphasense.rows[0].quality" in error for error in errors),
            errors,
        )
        with self.assertRaises(DataValidationError):
            validate_or_raise(data)

    def test_arr_month_must_be_strict_yyyy_mm(self) -> None:
        for bad_month in ("2024-1", "2024-00", "2024-13", "24-01", "2024/01"):
            with self.subTest(month=bad_month):
                data = full_data()
                data["arr_series"]["companies"][0]["points"][0]["d"] = bad_month
                errors = validate_data(data)
                self.assertTrue(any("valid YYYY-MM" in error for error in errors), errors)

    def test_arr_values_must_be_finite_positive_numbers(self) -> None:
        for bad_value in (0, -1, math.inf, -math.inf, math.nan, True, "12"):
            with self.subTest(value=bad_value):
                data = full_data()
                data["arr_series"]["companies"][0]["points"][0]["v"] = bad_value
                errors = validate_data(data)
                self.assertTrue(
                    any("$.arr_series.companies[0].points[0].v" in error for error in errors),
                    errors,
                )

    def test_arr_company_requires_at_least_one_observed_point(self) -> None:
        data = full_data()
        data["arr_series"]["companies"][0]["points"] = []

        errors = validate_data(data)

        self.assertTrue(any("must contain at least 1" in error for error in errors), errors)

    def test_daily_and_section_update_urls_must_be_absolute_http_urls(self) -> None:
        data = full_data()
        data["daily_log"][0]["items"][0]["url"] = "javascript:alert(1)"
        data["section_updates"]["analysis"][0]["url"] = "/relative"

        errors = validate_data(data)

        url_errors = [error for error in errors if "absolute http(s) URL" in error]
        self.assertEqual(2, len(url_errors), errors)

    def test_section_updates_reject_unknown_sections_and_malformed_events(self) -> None:
        data = full_data()
        data["section_updates"]["unknown-panel"] = []
        data["section_updates"]["cost"] = [{"cat": "定價"}]

        errors = validate_data(data)

        self.assertTrue(any("unknown section key" in error for error in errors), errors)
        self.assertTrue(
            any("$.section_updates.cost[0].text" in error for error in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
