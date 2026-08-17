#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the clear-text data used by the static site build.

The validator is intentionally non-destructive: it never normalizes or filters
the input, so fields added by future updater versions remain available.  Only
the fields currently consumed by ``build.py`` are required and type checked.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.parse
from collections.abc import Callable
from typing import Any


ROOT = os.path.dirname(os.path.abspath(__file__))
ARR_MONTH_RE = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")
SECTION_UPDATE_KEYS = {
    "analysis",
    "arrchart",
    "cost",
    "revenue",
    "compute",
    "contracts",
    "interconnect",
}
MISSING = object()


class DataValidationError(ValueError):
    """Raised when one or more site-data validation rules fail."""

    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        super().__init__("Invalid site data:\n- " + "\n- ".join(errors))


class _Validator:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def error(self, path: str, message: str) -> None:
        self.errors.append(f"{path}: {message}")

    def mapping(self, value: Any, path: str) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            self.error(path, "expected an object")
            return None
        return value

    def required(self, obj: dict[str, Any], key: str, path: str) -> Any:
        if key not in obj:
            self.error(f"{path}.{key}", "required field is missing")
            return MISSING
        return obj[key]

    def object_field(
        self, obj: dict[str, Any], key: str, path: str, *, optional: bool = False
    ) -> dict[str, Any] | None:
        if optional and key not in obj:
            return None
        value = self.required(obj, key, path)
        if value is MISSING:
            return None
        return self.mapping(value, f"{path}.{key}")

    def string_field(
        self,
        obj: dict[str, Any],
        key: str,
        path: str,
        *,
        optional: bool = False,
        allow_empty: bool = False,
    ) -> str | None:
        if optional and key not in obj:
            return None
        value = self.required(obj, key, path)
        field_path = f"{path}.{key}"
        if value is MISSING:
            return None
        if not isinstance(value, str):
            self.error(field_path, "expected a string")
            return None
        if not allow_empty and not value.strip():
            self.error(field_path, "must not be empty")
            return None
        return value

    def integer_field(
        self, obj: dict[str, Any], key: str, path: str, *, minimum: int | None = None
    ) -> int | None:
        value = self.required(obj, key, path)
        field_path = f"{path}.{key}"
        if value is MISSING:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            self.error(field_path, "expected an integer")
            return None
        if minimum is not None and value < minimum:
            self.error(field_path, f"must be at least {minimum}")
            return None
        return value

    def http_url_field(
        self, obj: dict[str, Any], key: str, path: str, *, optional: bool = True
    ) -> str | None:
        value = self.string_field(
            obj, key, path, optional=optional, allow_empty=optional
        )
        if not value:
            return value
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self.error(f"{path}.{key}", "expected an absolute http(s) URL")
            return None
        return value

    def positive_number_field(
        self, obj: dict[str, Any], key: str, path: str
    ) -> int | float | None:
        value = self.required(obj, key, path)
        field_path = f"{path}.{key}"
        if value is MISSING:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.error(field_path, "expected a number")
            return None
        if not math.isfinite(value) or value <= 0:
            self.error(field_path, "must be a finite positive number")
            return None
        return value

    def list_field(
        self,
        obj: dict[str, Any],
        key: str,
        path: str,
        *,
        optional: bool = False,
        min_items: int = 0,
    ) -> list[Any] | None:
        if optional and key not in obj:
            return None
        value = self.required(obj, key, path)
        field_path = f"{path}.{key}"
        if value is MISSING:
            return None
        if not isinstance(value, list):
            self.error(field_path, "expected an array")
            return None
        if len(value) < min_items:
            self.error(field_path, f"must contain at least {min_items} item(s)")
        return value

    def string_list(self, obj: dict[str, Any], key: str, path: str) -> None:
        values = self.list_field(obj, key, path)
        if values is None:
            return
        field_path = f"{path}.{key}"
        for index, value in enumerate(values):
            if not isinstance(value, str):
                self.error(f"{field_path}[{index}]", "expected a string")
            elif not value.strip():
                self.error(f"{field_path}[{index}]", "must not be empty")

    def object_list(
        self,
        obj: dict[str, Any],
        key: str,
        path: str,
        callback: Callable[[dict[str, Any], str], None],
        *,
        optional: bool = False,
        min_items: int = 0,
    ) -> None:
        values = self.list_field(
            obj, key, path, optional=optional, min_items=min_items
        )
        if values is None:
            return
        field_path = f"{path}.{key}"
        for index, value in enumerate(values):
            item_path = f"{field_path}[{index}]"
            item = self.mapping(value, item_path)
            if item is not None:
                callback(item, item_path)


def _strings(v: _Validator, obj: dict[str, Any], path: str, names: tuple[str, ...]) -> None:
    for name in names:
        v.string_field(obj, name, path)


def _validate_arr_point(v: _Validator, point: dict[str, Any], path: str) -> None:
    month = v.string_field(point, "d", path)
    if month is not None and ARR_MONTH_RE.fullmatch(month) is None:
        v.error(f"{path}.d", "expected a valid YYYY-MM month")
    v.positive_number_field(point, "v", path)
    v.string_field(point, "label", path)


def _validate_arr_forecast(v: _Validator, point: dict[str, Any], path: str) -> None:
    _validate_arr_point(v, point, path)
    if "range" in point:
        value = point["range"]
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            v.error(f"{path}.range", "expected a string or number")
        elif isinstance(value, float) and not math.isfinite(value):
            v.error(f"{path}.range", "number must be finite")


def _validate_arr(v: _Validator, arr: dict[str, Any], path: str) -> None:
    _strings(v, arr, path, ("note", "bars_note"))

    def company(item: dict[str, Any], item_path: str) -> None:
        _strings(v, item, item_path, ("name", "color"))
        v.object_list(
            item,
            "points",
            item_path,
            lambda p, pp: _validate_arr_point(v, p, pp),
            min_items=1,
        )
        v.object_list(
            item,
            "estimates",
            item_path,
            lambda p, pp: _validate_arr_point(v, p, pp),
            optional=True,
        )
        v.object_list(
            item,
            "forecasts",
            item_path,
            lambda p, pp: _validate_arr_forecast(v, p, pp),
            optional=True,
        )

    def latest_bar(item: dict[str, Any], item_path: str) -> None:
        _strings(v, item, item_path, ("name", "color", "note"))
        v.positive_number_field(item, "v", item_path)

    v.object_list(arr, "companies", path, company)
    v.object_list(arr, "latest_bars", path, latest_bar, optional=True)


def validate_data(data: Any) -> list[str]:
    """Return all schema errors without changing *data*.

    An empty list means the document is valid.  Unknown object fields are
    deliberately ignored so updater-specific metadata survives validation.
    """

    v = _Validator()
    root = v.mapping(data, "$")
    if root is None:
        return v.errors

    meta = v.object_field(root, "meta", "$")
    if meta is not None:
        _strings(v, meta, "$.meta", ("title", "subtitle", "updated"))
        v.integer_field(meta, "version", "$.meta", minimum=1)

    analysis = v.object_field(root, "analysis", "$")
    if analysis is not None:
        v.string_field(analysis, "headline", "$.analysis")
        v.string_list(analysis, "paragraphs", "$.analysis")

    def daily_day(day: dict[str, Any], path: str) -> None:
        _strings(v, day, path, ("date", "title"))

        def daily_item(item: dict[str, Any], item_path: str) -> None:
            _strings(v, item, item_path, ("cat", "text"))
            v.http_url_field(item, "url", item_path)

        v.object_list(day, "items", path, daily_item)

    v.object_list(root, "daily_log", "$", daily_day)

    cost = v.object_field(root, "cost", "$")
    if cost is not None:
        v.string_field(cost, "intro", "$.cost")
        alpha = v.object_field(cost, "alphasense", "$.cost")
        if alpha is not None:
            v.string_field(alpha, "desc", "$.cost.alphasense")
            v.object_list(
                alpha,
                "rows",
                "$.cost.alphasense",
                lambda item, path: _strings(
                    v, item, path, ("model", "maker", "type", "quality", "cost")
                ),
            )
        aa = v.object_field(cost, "aa", "$.cost")
        if aa is not None:
            v.string_field(aa, "desc", "$.cost.aa")
            v.object_list(
                aa,
                "rows",
                "$.cost.aa",
                lambda item, path: _strings(v, item, path, ("model", "ii", "cost")),
            )
        v.object_list(
            cost,
            "pricing",
            "$.cost",
            lambda item, path: _strings(v, item, path, ("model", "input", "output", "note")),
        )
        v.string_list(cost, "insights", "$.cost")

    revenue = v.object_field(root, "revenue", "$")
    if revenue is not None:
        v.object_list(
            revenue,
            "rows",
            "$.revenue",
            lambda item, path: _strings(
                v, item, path, ("company", "arr", "growth", "profit", "valuation", "mix")
            ),
        )
        v.string_field(revenue, "gemini_note", "$.revenue")
        v.string_list(revenue, "observations", "$.revenue")

    compute = v.object_field(root, "compute", "$")
    if compute is not None:
        v.object_list(
            compute,
            "cards",
            "$.compute",
            lambda item, path: _strings(
                v, item, path, ("company", "training", "inference", "mix", "asic")
            ),
        )
        v.string_field(compute, "china_note", "$.compute")

    contracts = v.object_field(root, "contracts", "$")
    if contracts is not None:
        v.object_list(
            contracts,
            "rows",
            "$.contracts",
            lambda item, path: _strings(
                v, item, path, ("date", "buyer", "partner", "desc", "size", "status")
            ),
        )

    interconnect = v.object_field(root, "interconnect", "$")
    if interconnect is not None:
        v.string_field(interconnect, "intro", "$.interconnect")
        v.object_list(
            interconnect,
            "camps",
            "$.interconnect",
            lambda item, path: _strings(
                v, item, path, ("camp", "leader", "scaleup", "scaleout", "deploy", "status")
            ),
        )
        v.object_list(
            interconnect,
            "cluster_choices",
            "$.interconnect",
            lambda item, path: _strings(v, item, path, ("cluster", "choice", "detail")),
        )
        v.string_list(interconnect, "updates", "$.interconnect")

    method = v.object_field(root, "method", "$")
    if method is not None:
        v.string_list(method, "sources", "$.method")
        v.string_list(method, "notes", "$.method")

    if "arr_series" in root:
        arr = v.mapping(root["arr_series"], "$.arr_series")
        if arr is not None:
            _validate_arr(v, arr, "$.arr_series")

    if "section_updates" in root:
        section_updates = v.mapping(root["section_updates"], "$.section_updates")
        if section_updates is not None:
            for section, events in section_updates.items():
                section_path = f"$.section_updates.{section}"
                if section not in SECTION_UPDATE_KEYS:
                    v.error(section_path, "unknown section key")
                    continue
                if not isinstance(events, list):
                    v.error(section_path, "expected an array")
                    continue
                for index, event_value in enumerate(events):
                    event_path = f"{section_path}[{index}]"
                    event = v.mapping(event_value, event_path)
                    if event is None:
                        continue
                    v.string_field(event, "text", event_path)
                    v.http_url_field(event, "url", event_path)
                    for field in ("date", "cat", "source"):
                        v.string_field(
                            event,
                            field,
                            event_path,
                            optional=True,
                            allow_empty=True,
                        )

    return v.errors


def validate_or_raise(data: Any) -> Any:
    """Validate and return the same object, raising on any schema error."""

    errors = validate_data(data)
    if errors:
        raise DataValidationError(errors)
    return data


def load_and_validate(path: str) -> Any:
    """Load a UTF-8 JSON document and validate it without rewriting it."""

    with open(path, encoding="utf-8") as handle:
        return validate_or_raise(json.load(handle))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate AI model tracker data.json")
    parser.add_argument(
        "path",
        nargs="?",
        default=os.path.join(ROOT, "data.json"),
        help="clear-text JSON file (default: repository data.json)",
    )
    parser.add_argument("--quiet", action="store_true", help="print only errors")
    args = parser.parse_args(argv)

    try:
        data = load_and_validate(args.path)
    except (OSError, json.JSONDecodeError, DataValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        meta = data.get("meta", {})
        print(
            "OK: %s is valid (version %s, updated %s)"
            % (args.path, meta.get("version"), meta.get("updated"))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
