"""Offline behavioral unit tests for the PR watcher; no GitHub access needed."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "scripts" / "watch_pr.py"
spec = importlib.util.spec_from_file_location("watch_pr", PATH)
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


def pr(*, checks=None, decision=None, merge_state="CLEAN", state="OPEN", head="head-sha"):
    return {
        "state": state,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": merge_state,
        "reviewDecision": decision,
        "statusCheckRollup": checks or [],
        "comments": [],
        "reviews": [],
        "headRefOid": head,
    }


def check(name="test", status="SUCCESS"):
    return {"__typename": "CheckRun", "name": name, "status": "COMPLETED", "conclusion": status}


class OutcomeTests(unittest.TestCase):
    def outcome(self, payload, until="ready"):
        return watch.outcome(payload, watch.summarize(payload), until)

    def test_empty_checks_not_green(self):
        self.assertIsNone(self.outcome(pr(), "green"))
        self.assertIsNone(self.outcome(pr(), "ready"))

    def test_pending_checks_not_green(self):
        pending = {"__typename": "CheckRun", "name": "build", "status": "IN_PROGRESS"}
        self.assertIsNone(self.outcome(pr(checks=[pending]), "green"))

    def test_green_checks_pass_green_mode(self):
        self.assertEqual(self.outcome(pr(checks=[check()]), "green"), (0, "checks green"))

    def test_required_review_blocks_ready(self):
        result = self.outcome(pr(checks=[check()], decision="REVIEW_REQUIRED"))
        self.assertEqual(result, (1, "required review pending"))

    def test_successful_checks_and_approved_review_ready(self):
        result = self.outcome(pr(checks=[check()], decision="APPROVED"))
        self.assertEqual(result[0], 0)
        self.assertIn("ready", result[1])

    def test_failed_check_is_not_hidden_by_same_name(self):
        item = pr(checks=[check(status="FAILURE"), check(status="SUCCESS")])
        summary = watch.summarize(item)
        self.assertEqual(len(summary["checks"]), 2)
        self.assertEqual(len(summary["failed"]), 1)
        self.assertEqual(self.outcome(item)[0], 1)

    def test_conflicting_branch_is_blocked(self):
        item = pr(checks=[check()])
        item["mergeable"] = "CONFLICTING"
        self.assertEqual(self.outcome(item)[0], 1)

    def test_merged_pr_reports_merged_even_if_no_checks(self):
        self.assertEqual(self.outcome(pr(state="MERGED")), (0, "merged"))

    def test_comment_body_not_printed(self):
        previous = watch.summarize(pr())
        item = pr()
        item["comments"] = [{"id": 15, "author": {"login": "reviewer"}, "body": "SECRET-DO-NOT-PRINT"}]
        result = watch.events(previous, watch.summarize(item))
        self.assertTrue(result)
        self.assertNotIn("SECRET", str(result))

    def test_changed_head_event(self):
        previous = watch.summarize(pr(head="before"))
        current = watch.summarize(pr(head="after"))
        self.assertTrue(any("head changed" in x for x in watch.events(previous, current)))

    @patch.object(watch.shutil, "which", return_value=None)
    def test_missing_gh_is_actionable_error(self, _which):
        self.assertEqual(watch.main(["12"]), 2)


if __name__ == "__main__":
    unittest.main()
