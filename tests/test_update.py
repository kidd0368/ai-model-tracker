from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import update


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "full_data.json"
NOW = dt.datetime(2026, 8, 18, 7, 0, tzinfo=ZoneInfo("Asia/Taipei"))
RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Official AI Feed</title>
<item><title>New inference model cuts token pricing</title>
<link>https://example.org/news/model?utm_source=test</link>
<description>Official API model and pricing announcement.</description>
<pubDate>Mon, 17 Aug 2026 23:00:00 GMT</pubDate></item>
</channel></rss>"""


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class UpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.work = Path(self.temporary.name)
        self.data_path = self.work / "data.json"
        self.config_path = self.work / "sources.json"
        shutil.copy2(FIXTURE, self.data_path)
        write_json(
            self.config_path,
            {
                "lookback_hours": 336,
                "minimum_successful_sources": 1,
                "max_candidates_per_source": 5,
                "max_items_per_run": 5,
                "sources": [
                    {
                        "id": "official",
                        "name": "Official Feed",
                        "url": "https://example.org/feed.xml",
                        "priority": 100,
                        "default_category": "模型",
                    }
                ],
            },
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_update_is_additive_source_backed_and_deduplicated(self) -> None:
        original = json.loads(self.data_path.read_text(encoding="utf-8"))
        deep_dive_before = {
            "expectation_comparison": original["arr_series"][
                "expectation_comparison"
            ],
            "momentum": original["arr_series"]["momentum"],
            "aa": original["cost"]["aa"],
            "monetization": original["revenue"]["monetization"],
            "product_comparison": original["revenue"]["product_comparison"],
            "references": original["method"]["references"],
        }
        with mock.patch("update.fetch_bytes", return_value=RSS), mock.patch.dict(
            os.environ,
            {
                "AI_ENRICHMENT_TOKEN": "",
                "AI_ENRICHMENT_ENDPOINT": "",
                "AI_ENRICHMENT_MODEL": "",
            },
        ):
            first = update.run(self.data_path, self.config_path, now=NOW)
            second = update.run(self.data_path, self.config_path, now=NOW)

        data = json.loads(self.data_path.read_text(encoding="utf-8"))
        canonical = "https://example.org/news/model"
        matching = [
            item
            for day in data["daily_log"]
            for item in day["items"]
            if item.get("url") == canonical
        ]
        self.assertEqual(1, len(matching))
        self.assertEqual(1, len(first["items"]))
        self.assertEqual(0, len(second["items"]))
        self.assertEqual("must survive", data["arr_series"]["companies"][0]["future_company_field"])
        self.assertEqual(43, data["meta"]["version"])
        self.assertEqual("2026-08-18 07:00（台北）", data["meta"]["last_checked"])
        self.assertTrue(
            any(event["url"] == canonical for event in data["section_updates"]["cost"])
        )
        self.assertEqual(
            deep_dive_before,
            {
                "expectation_comparison": data["arr_series"][
                    "expectation_comparison"
                ],
                "momentum": data["arr_series"]["momentum"],
                "aa": data["cost"]["aa"],
                "monetization": data["revenue"]["monetization"],
                "product_comparison": data["revenue"]["product_comparison"],
                "references": data["method"]["references"],
            },
        )

    def test_source_quorum_failure_does_not_touch_data(self) -> None:
        before = self.data_path.read_bytes()
        with mock.patch("update.fetch_source", side_effect=update.UpdateError("offline")):
            with self.assertRaisesRegex(update.UpdateError, "source quorum failed"):
                update.run(self.data_path, self.config_path, now=NOW)
        self.assertEqual(before, self.data_path.read_bytes())

    def test_sitemap_adapter_filters_path_and_date(self) -> None:
        body = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.org/news/new-model</loc><lastmod>2026-08-17</lastmod></url>
          <url><loc>https://example.org/company/about</loc><lastmod>2026-08-17</lastmod></url>
          <url><loc>https://example.org/news/old-model</loc><lastmod>2025-01-01</lastmod></url>
        </urlset>"""
        source = {
            "id": "newsroom",
            "name": "Official Newsroom",
            "url": "https://example.org/sitemap.xml",
            "type": "sitemap",
            "include_path_prefixes": ["/news/"],
            "priority": 90,
            "default_category": "模型",
        }
        items = update.parse_sitemap_source(
            source,
            body,
            NOW.astimezone(dt.timezone.utc),
            NOW.astimezone(dt.timezone.utc) - dt.timedelta(days=14),
        )
        self.assertEqual(["https://example.org/news/new-model"], [item["url"] for item in items])

    def test_canonical_url_removes_tracking_not_meaningful_query(self) -> None:
        value = update.canonical_url(
            "HTTPS://Example.COM/news/item/?utm_source=x&id=7&fbclid=y#section"
        )
        self.assertEqual("https://example.com/news/item?id=7", value)

    def test_enrichment_api_empty_selection_is_success(self) -> None:
        candidates = [
            {
                "url": "https://example.org/routine-update",
                "source": "Official Feed",
                "title": "Routine update",
                "summary": "No material AI industry impact.",
                "published": "2026-08-18T00:00:00+00:00",
                "default_category": "產業",
            }
        ]
        with mock.patch.dict(
            os.environ,
            {
                "AI_ENRICHMENT_TOKEN": "test-token",
                "AI_ENRICHMENT_ENDPOINT": "https://api.example.test/v1/",
                "AI_ENRICHMENT_MODEL": "test/model",
            },
        ), mock.patch("update.openai_compatible_items", return_value=[]) as api_items:
            items, enrichment = update.enrich(candidates, limit=5)

        self.assertEqual([], items)
        self.assertEqual("api:test/model", enrichment)
        api_items.assert_called_once_with(
            candidates,
            "test-token",
            "test/model",
            "https://api.example.test/v1/",
            5,
        )

    def test_enrichment_api_partial_configuration_falls_back(self) -> None:
        candidates = [
            {
                "url": "https://example.org/model-release",
                "source": "Official Feed",
                "title": "New model release",
                "summary": "Official model announcement.",
                "published": "2026-08-18T00:00:00+00:00",
                "default_category": "模型",
            }
        ]
        with mock.patch.dict(
            os.environ,
            {
                "AI_ENRICHMENT_TOKEN": "test-token",
                "AI_ENRICHMENT_ENDPOINT": "",
                "AI_ENRICHMENT_MODEL": "test/model",
            },
        ), mock.patch("builtins.print") as warning, mock.patch(
            "update.openai_compatible_items"
        ) as api_items:
            items, enrichment = update.enrich(candidates, limit=5)

        self.assertEqual("deterministic-fallback", enrichment)
        self.assertEqual(["https://example.org/model-release"], [item["url"] for item in items])
        api_items.assert_not_called()
        self.assertIn("AI_ENRICHMENT_ENDPOINT", warning.call_args.args[0])

    def test_enrichment_api_malformed_response_falls_back(self) -> None:
        candidates = [
            {
                "url": "https://example.org/model-release",
                "source": "Official Feed",
                "title": "New model release",
                "summary": "Official model announcement.",
                "published": "2026-08-18T00:00:00+00:00",
                "default_category": "模型",
            }
        ]
        with mock.patch.dict(
            os.environ,
            {
                "AI_ENRICHMENT_TOKEN": "test-token",
                "AI_ENRICHMENT_ENDPOINT": "https://api.example.test/v1",
                "AI_ENRICHMENT_MODEL": "test/model",
            },
        ), mock.patch("update.urllib.request.urlopen") as urlopen, mock.patch(
            "update.json.load", return_value={"choices": []}
        ):
            items, enrichment = update.enrich(candidates, limit=5)

        self.assertEqual("deterministic-fallback", enrichment)
        self.assertEqual(["https://example.org/model-release"], [item["url"] for item in items])
        request = urlopen.call_args.args[0]
        self.assertEqual("https://api.example.test/v1/chat/completions", request.full_url)
        self.assertEqual("Bearer test-token", request.get_header("Authorization"))
        self.assertEqual("test/model", json.loads(request.data)["model"])

    def test_enrichment_api_transport_errors_fall_back(self) -> None:
        candidates = [
            {
                "url": "https://example.org/model-release",
                "source": "Official Feed",
                "title": "New model release",
                "summary": "Official model announcement.",
                "published": "2026-08-18T00:00:00+00:00",
                "default_category": "模型",
            }
        ]
        for error in (TimeoutError("timed out"), OSError("connection reset")):
            with self.subTest(error=type(error).__name__), mock.patch.dict(
                os.environ,
                {
                    "AI_ENRICHMENT_TOKEN": "test-token",
                    "AI_ENRICHMENT_ENDPOINT": "https://api.example.test/v1",
                    "AI_ENRICHMENT_MODEL": "test/model",
                },
            ), mock.patch("update.openai_compatible_items", side_effect=error):
                items, enrichment = update.enrich(candidates, limit=5)

            self.assertEqual("deterministic-fallback", enrichment)
            self.assertEqual(
                ["https://example.org/model-release"], [item["url"] for item in items]
            )

    def test_unpublished_candidates_are_not_marked_seen(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data.setdefault("automation", {})["seen_urls"] = ["https://example.org/already-seen"]
        selected_url = "https://example.org/selected"
        deferred_url = "https://example.org/deferred"
        candidates = [{"url": selected_url}, {"url": deferred_url}]
        selected = {
            "url": selected_url,
            "text": "官方發布具重大影響的新模型更新。",
            "cat": "模型",
            "sections": ["analysis"],
            "source": "Official Feed",
        }
        config = {"max_items_per_run": 5, "sources": [{"name": "Official Feed"}]}
        source_status = [{"name": "Official Feed", "ok": True, "items": 2}]

        with mock.patch("update.enrich", return_value=([selected], "test")):
            update.apply_update(data, config, candidates, source_status, NOW)

        self.assertEqual(
            [selected_url, "https://example.org/already-seen"],
            data["automation"]["seen_urls"],
        )
        self.assertNotIn(deferred_url, data["automation"]["seen_urls"])

    def test_section_updates_preserve_item_priority(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        items = [
            {
                "url": "https://example.org/high-priority",
                "text": "最高優先事件",
                "cat": "模型",
                "sections": ["analysis"],
                "source": "Official Feed",
            },
            {
                "url": "https://example.org/lower-priority",
                "text": "次要事件",
                "cat": "產業",
                "sections": ["analysis"],
                "source": "Official Feed",
            },
        ]

        update.insert_section_updates(data, NOW.date().isoformat(), items)

        self.assertEqual(
            ["https://example.org/high-priority", "https://example.org/lower-priority"],
            [event["url"] for event in data["section_updates"]["analysis"][:2]],
        )


if __name__ == "__main__":
    unittest.main()
