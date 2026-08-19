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

    def test_deep_dive_source_types_are_allowlisted(self) -> None:
        data = full_data()
        data["arr_series"]["expectation_comparison"]["latest"][
            "source_type"
        ] = "official-ish"

        errors = validate_data(data)

        self.assertTrue(
            any(
                "$.arr_series.expectation_comparison.latest.source_type" in error
                and "expected one of" in error
                for error in errors
            ),
            errors,
        )

    def test_monetization_shares_must_be_positive_percentages(self) -> None:
        for field, value in (
            ("token_share_pct", 0),
            ("spend_share_pct", 100.01),
            ("coding_agent_spend_share_pct", 101),
        ):
            with self.subTest(field=field, value=value):
                data = full_data()
                data["revenue"]["monetization"]["rows"][0][field] = value

                errors = validate_data(data)

                self.assertTrue(
                    any(
                        f"$.revenue.monetization.rows[0].{field}" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_momentum_months_must_be_unique_and_strictly_increasing(self) -> None:
        for label, replacement in (
            ("duplicate", "2099-02"),
            ("unordered", "2099-01"),
        ):
            with self.subTest(case=label):
                data = full_data()
                data["arr_series"]["momentum"]["points"][1]["d"] = replacement

                errors = validate_data(data)

                self.assertTrue(
                    any(
                        "$.arr_series.momentum.points[1].d" in error
                        and "strictly increasing" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_expectation_display_must_match_qualifier_and_value(self) -> None:
        data = full_data()
        data["arr_series"]["expectation_comparison"]["latest"]["display"] = ">750"

        errors = validate_data(data)

        self.assertTrue(
            any(
                "$.arr_series.expectation_comparison.latest.display" in error
                and "qualifier + value" in error
                for error in errors
            ),
            errors,
        )

    def test_structured_reference_url_must_be_absolute_http(self) -> None:
        data = full_data()
        data["method"]["references"][0]["url"] = "javascript:alert(1)"

        errors = validate_data(data)

        self.assertTrue(
            any(
                "$.method.references[0].url" in error
                and "absolute http(s) URL" in error
                for error in errors
            ),
            errors,
        )

    def test_product_weekly_series_dates_and_points_must_align(self) -> None:
        data = full_data()
        comparison = data["revenue"]["product_comparison"]
        comparison["dates"] = ["2099-01-01", "2099-02-30"]
        comparison["rows"][0]["points"] = [10, 20, 30]
        comparison["rows"][1]["points"] = [8, 18]

        errors = validate_data(data)

        self.assertTrue(
            any("$.revenue.product_comparison.dates[1]" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any(
                "$.revenue.product_comparison.rows[0].points" in error
                and "every comparison date" in error
                for error in errors
            ),
            errors,
        )

    def test_product_weekly_series_requires_points_when_dates_exist(self) -> None:
        data = full_data()
        comparison = data["revenue"]["product_comparison"]
        del comparison["rows"][1]["points"]

        errors = validate_data(data)

        self.assertTrue(
            any(
                "$.revenue.product_comparison.rows[1].points" in error
                and "required" in error
                for error in errors
            ),
            errors,
        )

    def test_product_weekly_series_too_short_reports_error_without_crashing(self) -> None:
        for points in ([], [100]):
            with self.subTest(points=points):
                data = full_data()
                data["revenue"]["product_comparison"]["rows"][0]["points"] = points

                errors = validate_data(data)

                self.assertTrue(
                    any(
                        "$.revenue.product_comparison.rows[0].points" in error
                        and "at least 2" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_product_weekly_series_empty_dates_reports_error_without_crashing(self) -> None:
        data = full_data()
        data["revenue"]["product_comparison"]["dates"] = []

        errors = validate_data(data)

        self.assertTrue(
            any(
                "$.revenue.product_comparison.dates" in error
                and "at least 2" in error
                for error in errors
            ),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
