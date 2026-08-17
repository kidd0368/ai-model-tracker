#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify that both encrypted site artifacts match the current data.json.

This is a read-only post-build check.  It validates the same AES-256-GCM /
PBKDF2-SHA256 envelope used by build.py, decrypts both outputs, and checks that
the encrypted data is identical to the clear-text source and that the rendered
page contains the current source-backed content.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import html
import json
import os
import sys
from typing import Any, Iterable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from validate_data import DataValidationError, load_and_validate, validate_or_raise


ROOT = os.path.dirname(os.path.abspath(__file__))
ITERATIONS = 300_000
SALT_BYTES = 16
IV_BYTES = 12
GCM_TAG_BYTES = 16
PAYLOAD_MARKER = "const PAYLOAD = "
REQUIRED_SECTIONS = (
    "analysis",
    "arrchart",
    "log",
    "cost",
    "revenue",
    "compute",
    "contracts",
    "interconnect",
    "method",
)


class BuildVerificationError(RuntimeError):
    """Raised when an encrypted build artifact is malformed or stale."""


def _decode_base64(value: Any, field: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise BuildVerificationError(f"{field} must be a non-empty base64 string")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BuildVerificationError(f"{field} is not valid base64") from exc


def _envelope_parts(payload: Any, label: str) -> tuple[bytes, bytes, bytes]:
    if not isinstance(payload, dict):
        raise BuildVerificationError(f"{label} must be a JSON object")
    missing = [field for field in ("salt", "iv", "ct", "iter") if field not in payload]
    if missing:
        raise BuildVerificationError(f"{label} is missing: {', '.join(missing)}")
    iterations = payload["iter"]
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise BuildVerificationError(f"{label}.iter must be an integer")
    if iterations != ITERATIONS:
        raise BuildVerificationError(
            f"{label}.iter must be {ITERATIONS}, got {iterations}"
        )

    salt = _decode_base64(payload["salt"], f"{label}.salt")
    iv = _decode_base64(payload["iv"], f"{label}.iv")
    ciphertext = _decode_base64(payload["ct"], f"{label}.ct")
    if len(salt) != SALT_BYTES:
        raise BuildVerificationError(
            f"{label}.salt must decode to {SALT_BYTES} bytes"
        )
    if len(iv) != IV_BYTES:
        raise BuildVerificationError(f"{label}.iv must decode to {IV_BYTES} bytes")
    if len(ciphertext) < GCM_TAG_BYTES:
        raise BuildVerificationError(f"{label}.ct is shorter than the GCM tag")
    return salt, iv, ciphertext


def decrypt_payload(payload: Any, password: str, *, label: str = "payload") -> bytes:
    """Decrypt one build.py envelope after validating its cryptographic format."""

    if not isinstance(password, str) or not password:
        raise BuildVerificationError("SITE_PASSWORD must not be empty")
    salt, iv, ciphertext = _envelope_parts(payload, label)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ITERATIONS,
    )
    key = kdf.derive(password.encode("utf-8"))
    try:
        return AESGCM(key).decrypt(iv, ciphertext, None)
    except InvalidTag as exc:
        raise BuildVerificationError(
            f"{label} authentication failed (wrong password or modified artifact)"
        ) from exc


def extract_index_payload(index_text: str) -> dict[str, Any]:
    """Extract the JSON object assigned to PAYLOAD in the encrypted shell."""

    marker_at = index_text.find(PAYLOAD_MARKER)
    if marker_at < 0:
        raise BuildVerificationError("index.html does not contain an encrypted PAYLOAD")
    if index_text.find(PAYLOAD_MARKER, marker_at + len(PAYLOAD_MARKER)) >= 0:
        raise BuildVerificationError("index.html contains more than one PAYLOAD")
    json_at = marker_at + len(PAYLOAD_MARKER)
    try:
        payload, end = json.JSONDecoder().raw_decode(index_text, json_at)
    except json.JSONDecodeError as exc:
        raise BuildVerificationError("index.html PAYLOAD is not valid JSON") from exc
    if index_text[end:].lstrip()[:1] != ";":
        raise BuildVerificationError("index.html PAYLOAD assignment is not terminated")
    if not isinstance(payload, dict):
        raise BuildVerificationError("index.html PAYLOAD must be a JSON object")
    return payload


def _data_payload(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildVerificationError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BuildVerificationError(f"{path} must contain a JSON object")
    return payload


def _known_visible_values(data: dict[str, Any]) -> Iterable[Any]:
    """Yield source values that the current renderer must expose after decrypting."""

    meta = data["meta"]
    yield from (meta["title"], meta["subtitle"], meta["updated"])
    analysis = data["analysis"]
    yield analysis["headline"]
    yield from analysis["paragraphs"]

    for day in data["daily_log"]:
        yield from (day["date"], day["title"])
        for item in day["items"]:
            yield from (item["cat"], item["text"])

    cost = data["cost"]
    yield cost["intro"]
    yield cost["alphasense"]["desc"]
    for row in cost["alphasense"]["rows"]:
        yield from (row["model"], row["maker"], row["type"], row["quality"], row["cost"])
    yield cost["aa"]["desc"]
    for row in cost["aa"]["rows"]:
        yield from (row["model"], row["ii"], row["cost"])
    for row in cost["pricing"]:
        yield from (row["model"], row["input"], row["output"], row["note"])
    yield from cost["insights"]

    revenue = data["revenue"]
    for row in revenue["rows"]:
        yield from (
            row["company"],
            row["arr"],
            row["growth"],
            row["profit"],
            row["valuation"],
            row["mix"],
        )
    yield revenue["gemini_note"]
    yield from revenue["observations"]

    compute = data["compute"]
    for card in compute["cards"]:
        yield from (
            card["company"],
            card["training"],
            card["inference"],
            card["mix"],
            card["asic"],
        )
    yield compute["china_note"]

    for row in data["contracts"]["rows"]:
        yield from (
            row["date"],
            row["buyer"],
            row["partner"],
            row["desc"],
            row["size"],
            row["status"],
        )

    interconnect = data["interconnect"]
    yield interconnect["intro"]
    for row in interconnect["camps"]:
        yield from (
            row["camp"],
            row["leader"],
            row["scaleup"],
            row["scaleout"],
            row["deploy"],
            row["status"],
        )
    for row in interconnect["cluster_choices"]:
        yield from (row["cluster"], row["choice"], row["detail"])
    yield from interconnect["updates"]
    yield from data["method"]["sources"]
    yield from data["method"]["notes"]

    arr = data.get("arr_series")
    if arr:
        yield from (arr["note"], arr["bars_note"])
        for company in arr["companies"]:
            yield company["name"]
            for group in ("points", "estimates", "forecasts"):
                for point in company.get(group, []):
                    yield point["label"]
        for bar in arr.get("latest_bars", []):
            yield from (bar["name"], bar["note"])

    for events in data.get("section_updates", {}).values():
        for event in events:
            yield event["text"]
            for field in ("date", "cat", "source"):
                if event.get(field):
                    yield event[field]


def _verify_rendered_html(rendered: str, expected: dict[str, Any]) -> None:
    if "<!DOCTYPE html>" not in rendered or "</html>" not in rendered:
        raise BuildVerificationError("decrypted index PAYLOAD is not a complete HTML page")
    missing_sections = [
        name for name in REQUIRED_SECTIONS if f'<section id="{name}">' not in rendered
    ]
    if missing_sections:
        raise BuildVerificationError(
            "decrypted index is missing sections: " + ", ".join(missing_sections)
        )

    missing_values: list[str] = []
    for value in _known_visible_values(expected):
        rendered_value = html.escape(str(value), quote=False)
        if rendered_value not in rendered:
            missing_values.append(str(value))
            if len(missing_values) == 5:
                break
    if missing_values:
        preview = ", ".join(repr(value) for value in missing_values)
        raise BuildVerificationError(
            f"decrypted index does not match data.json; missing rendered value(s): {preview}"
        )


def verify_build(
    password: str,
    *,
    data_path: str | None = None,
    encrypted_data_path: str | None = None,
    index_path: str | None = None,
) -> dict[str, Any]:
    """Verify the build and return non-sensitive hashes and sizes on success."""

    data_path = data_path or os.path.join(ROOT, "data.json")
    encrypted_data_path = encrypted_data_path or os.path.join(ROOT, "data.enc")
    index_path = index_path or os.path.join(ROOT, "index.html")

    try:
        expected = load_and_validate(data_path)
    except (OSError, json.JSONDecodeError, DataValidationError) as exc:
        raise BuildVerificationError(f"invalid data.json: {exc}") from exc

    encrypted_data = _data_payload(encrypted_data_path)
    clear_data_bytes = decrypt_payload(
        encrypted_data, password, label=os.path.basename(encrypted_data_path)
    )
    try:
        built_data = json.loads(clear_data_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildVerificationError("data.enc plaintext is not valid UTF-8 JSON") from exc
    try:
        validate_or_raise(built_data)
    except DataValidationError as exc:
        raise BuildVerificationError(f"data.enc plaintext failed schema validation: {exc}") from exc
    if built_data != expected:
        raise BuildVerificationError("data.enc plaintext does not match data.json")

    try:
        with open(index_path, encoding="utf-8") as handle:
            index_text = handle.read()
    except OSError as exc:
        raise BuildVerificationError(f"cannot read {index_path}: {exc}") from exc
    index_payload = extract_index_payload(index_text)
    rendered_bytes = decrypt_payload(
        index_payload, password, label=f"{os.path.basename(index_path)} PAYLOAD"
    )
    try:
        rendered = rendered_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildVerificationError("index.html PAYLOAD is not valid UTF-8") from exc
    _verify_rendered_html(rendered, expected)

    return {
        "data_sha256": hashlib.sha256(clear_data_bytes).hexdigest(),
        "rendered_sha256": hashlib.sha256(rendered_bytes).hexdigest(),
        "data_bytes": len(clear_data_bytes),
        "rendered_bytes": len(rendered_bytes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify encrypted tracker build outputs")
    parser.add_argument("--data", default=os.path.join(ROOT, "data.json"))
    parser.add_argument("--encrypted-data", default=os.path.join(ROOT, "data.enc"))
    parser.add_argument("--index", default=os.path.join(ROOT, "index.html"))
    args = parser.parse_args(argv)

    password = os.environ.get("SITE_PASSWORD", "")
    if not password:
        print("ERROR: 請以 SITE_PASSWORD 環境變數提供密碼", file=sys.stderr)
        return 2
    try:
        result = verify_build(
            password,
            data_path=args.data,
            encrypted_data_path=args.encrypted_data,
            index_path=args.index,
        )
    except BuildVerificationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "OK: encrypted outputs match data.json "
        f"(data {result['data_bytes']} bytes, page {result['rendered_bytes']} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
