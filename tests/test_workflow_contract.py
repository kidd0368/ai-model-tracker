from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "daily-update.yml"


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_taipei_schedule_is_explicit(self) -> None:
        self.assertIn('cron: "0 7 * * *"', self.text)
        self.assertIn('timezone: "Asia/Taipei"', self.text)

    def test_secret_and_minimum_job_permissions_are_explicit(self) -> None:
        secret_binding = "SITE_PASSWORD: ${{ secrets.SITE_PASSWORD }}"
        enrichment_token_binding = "AI_ENRICHMENT_TOKEN: ${{ secrets.AI_ENRICHMENT_TOKEN }}"
        enrichment_endpoint_binding = "AI_ENRICHMENT_ENDPOINT: ${{ vars.AI_ENRICHMENT_ENDPOINT }}"
        enrichment_model_binding = "AI_ENRICHMENT_MODEL: ${{ vars.AI_ENRICHMENT_MODEL }}"
        self.assertEqual(self.text.count(secret_binding), 4)
        self.assertEqual(self.text.count(enrichment_token_binding), 2)
        self.assertEqual(self.text.count(enrichment_endpoint_binding), 2)
        self.assertEqual(self.text.count(enrichment_model_binding), 2)
        update_job = self.text.split("\n  update:\n", 1)[1]
        update_job_preamble = update_job.split("\n    steps:\n", 1)[0]
        self.assertNotIn(secret_binding, update_job_preamble)
        self.assertNotIn(enrichment_token_binding, update_job_preamble)
        self.assertNotIn(enrichment_endpoint_binding, update_job_preamble)
        self.assertNotIn(enrichment_model_binding, update_job_preamble)
        dry_run_step = self.text.split("      - name: Collect official sources (dry run)\n", 1)[1].split(
            "\n      - name:", 1
        )[0]
        update_step = self.text.split("      - name: Collect and apply official sources\n", 1)[1].split(
            "\n      - name:", 1
        )[0]
        for step in (dry_run_step, update_step):
            self.assertIn(enrichment_token_binding, step)
            self.assertIn(enrichment_endpoint_binding, step)
            self.assertIn(enrichment_model_binding, step)
            self.assertIn("run: python update.py", step)
        self.assertIn("contents: write", self.text)
        self.assertNotIn("models: read", self.text)
        self.assertNotIn("GITHUB_MODELS", self.text)
        self.assertNotIn("AI_RESEARCH_MODEL", self.text)
        self.assertIn("pages: write", self.text)
        self.assertIn("id-token: write", self.text)

    def test_pages_artifact_cannot_include_plaintext_repository(self) -> None:
        self.assertIn("site_dir=\"$RUNNER_TEMP/ai-model-tracker-site\"", self.text)
        self.assertIn("path: ${{ runner.temp }}/ai-model-tracker-site", self.text)
        self.assertNotIn("path: .\n", self.text)
        self.assertIn('cp -- index.html "$site_dir/index.html"', self.text)
        self.assertIn('"${#artifact_entries[@]}" -ne 1', self.text)
        self.assertIn('"${artifact_entries[0]}" != "index.html"', self.text)
        self.assertNotIn(".nojekyll", self.text)
        self.assertNotIn("cp -- data.json", self.text)

    def test_main_ref_and_trigger_commit_are_pinned(self) -> None:
        self.assertNotIn("    paths:\n", self.text)
        self.assertIn("github.ref == 'refs/heads/main'", self.text)
        self.assertIn("ref: ${{ github.sha }}", self.text)
        self.assertIn("git push origin HEAD:main", self.text)
        self.assertNotIn("--force", self.text)

    def test_deploy_uses_the_exact_verified_commit(self) -> None:
        self.assertIn("deployed_sha: ${{ steps.deployment_source.outputs.sha }}", self.text)
        self.assertIn("id: deployment_source", self.text)
        self.assertIn("success() && (github.event_name == 'schedule' || inputs.mode == 'update')", self.text)
        self.assertIn("git rev-parse --verify 'HEAD^{commit}'", self.text)
        self.assertIn("needs.update.outputs.deployed_sha != ''", self.text)
        self.assertIn("ref: ${{ needs.update.outputs.deployed_sha || github.sha }}", self.text)
        self.assertNotIn("ref: main", self.text)

    def test_concurrency_separates_pull_requests_from_production(self) -> None:
        self.assertIn("ai-model-tracker-pr-{0}", self.text)
        self.assertIn("github.event.pull_request.number", self.text)
        self.assertIn("ai-model-tracker-production", self.text)

    def test_commit_allowlist_contains_only_encrypted_pair(self) -> None:
        self.assertIn("git add -- data.enc index.html", self.text)
        self.assertIn("data.json must never be tracked", self.text)
        self.assertNotIn("git add .", self.text)


if __name__ == "__main__":
    unittest.main()
