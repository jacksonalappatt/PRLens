"""Unit tests for standalone Azure DevOps PR Review Agent."""

import json
import sys
import unittest
import urllib.request
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.workspace_detector import inspect_git_remote, is_git_repo
from harnesses.base import parse_review_report
from server.webhook_server import WebhookServer


class TestReviewParser(unittest.TestCase):
    def test_parse_vote_and_comments(self):
        sample_report = """# Senior Architectural & Logic PR Review: PR #1001
## 2. Five-Axis Quality Evaluation Matrix
- [x] Correctness & Spec

## 3. Findings & Named Structural Remedies
### 🟡 Major (Requires Revision)
- `[src/components/user-card.ts#L42]`: Missing null safety on numeric conversion.
- `[src/services/data-stream.ts:115]`: Subscription stream not cleaned up on disposal.

### 🟢 Praise
- Clean unidirectional state flow.

## 4. Proposed ADO Actions & User Approval Gate
- Proposed Reviewer Vote: `Approved with Suggestions (+5)`
- Proposed ADO Comments:
  - Inline suggestions listed above.
"""
        vote, comments = parse_review_report(sample_report)
        self.assertEqual(vote, 5)
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["filePath"], "src/components/user-card.ts")
        self.assertEqual(comments[0]["line"], 42)
        self.assertIn("Missing null safety", comments[0]["comment"])
        self.assertEqual(comments[1]["filePath"], "src/services/data-stream.ts")
        self.assertEqual(comments[1]["line"], 115)

    def test_parse_approved_vote(self):
        sample_report = """
- Proposed Reviewer Vote: `Approved (+10)`
"""
        vote, comments = parse_review_report(sample_report)
        self.assertEqual(vote, 10)
        self.assertEqual(len(comments), 0)


class TestWorkspaceDetector(unittest.TestCase):
    def test_is_git_repo(self):
        self.assertTrue(is_git_repo(PROJECT_ROOT))
        self.assertFalse(is_git_repo(Path(r"D:\non_existent_folder_98765")))

    def test_inspect_git_remote_fallback(self):
        info = inspect_git_remote(PROJECT_ROOT)
        self.assertIn("repository", info)
        self.assertEqual(info["repository"], PROJECT_ROOT.name)


class TestWebhookServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.received_events = []

        def on_pr(pr_info):
            cls.received_events.append(pr_info)

        cls.server = WebhookServer(host="127.0.0.1", port=7898, secret="", on_pr_callback=on_pr)
        cls.server.start(background=True)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_health_check(self):
        req = urllib.request.Request("http://127.0.0.1:7898/health")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("service"), "prlens-webhook-listener")

    def test_webhook_pr_payload(self):
        payload = {
            "eventType": "git.pullrequest.created",
            "resource": {
                "pullRequestId": 88888,
                "title": "Standalone Agent Test PR",
                "createdBy": {"displayName": "Test Bot"},
                "repository": {"name": "sample-repo", "id": "sample-repo-id", "project": {"name": "sample-proj"}},
                "sourceRefName": "refs/heads/feature/test-2",
                "targetRefName": "refs/heads/main",
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:7898/webhook",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res_data.get("status"), "accepted")
            self.assertEqual(res_data.get("prId"), 88888)


if __name__ == "__main__":
    unittest.main()
