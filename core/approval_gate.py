"""User Approval Gate for reviewing and submitting feedback to Azure DevOps."""

import json
import sys
from pathlib import Path

from harnesses.base import parse_review_report

from .ado_client import AdoClient


class ApprovalGate:
    def __init__(self, ado_client: AdoClient, jobs_dir: Path):
        self.ado_client = ado_client
        self.jobs_dir = jobs_dir.resolve()

    def review_and_submit(self, pr_id: int) -> bool:
        job_dir = self.jobs_dir / str(pr_id)
        report_file = job_dir / "review_report.md"
        job_file = job_dir / "job.json"

        if not report_file.exists():
            print(f"❌ Error: No review report found for PR #{pr_id} at {report_file}", file=sys.stderr)
            return False

        report_text = report_file.read_text(encoding="utf-8")
        pr_info = json.loads(job_file.read_text(encoding="utf-8")) if job_file.exists() else {}

        vote, comments = parse_review_report(report_text)
        repo_id = pr_info.get("repositoryId") or pr_info.get("repository") or self.ado_client.project

        print("\n" + "=" * 70)
        print(f"📋 PULL REQUEST REVIEW GATE: PR #{pr_id}")
        print(f"   Title: {pr_info.get('title', 'N/A')}")
        print(f"   Author: {pr_info.get('createdBy', 'N/A')}")
        print(f"   Recommended Vote: {vote}")
        print(f"   Proposed Inline Comments: {len(comments)}")
        print("=" * 70)

        if comments:
            print("\nProposed Inline Comments:")
            for idx, c in enumerate(comments, 1):
                print(f"  {idx}. [{c.get('filePath')}:{c.get('line')}] {c.get('comment')}")

        while True:
            print("\nOptions:")
            print("  [A] Approve PR (Vote: +10)")
            print("  [S] Approve with Suggestions (Vote: +5, post inline comments)")
            print("  [W] Waiting for Author (Vote: -5, post inline comments)")
            print("  [R] Reject (Vote: -10, post inline comments)")
            print("  [V] View Full Review Report")
            print("  [X] Cancel / Do Nothing")

            choice = input("\nEnter choice [A/S/W/R/V/X]: ").strip().upper()

            if choice == "V":
                print("\n" + "-" * 70)
                print(report_text)
                print("-" * 70)
                continue

            if choice == "X":
                print("Submission cancelled.")
                return False

            vote_map = {"A": 10, "S": 5, "W": -5, "R": -10}
            if choice in vote_map:
                chosen_vote = vote_map[choice]
                confirm = (
                    input(
                        f"Are you sure you want to submit vote ({chosen_vote}) and {len(comments)} comments to Azure DevOps? (y/N): "
                    )
                    .strip()
                    .lower()
                )
                if confirm != "y":
                    print("Cancelled.")
                    return False

                if choice in ["S", "W", "R"] and comments:
                    print(f"[ApprovalGate] Posting {len(comments)} inline comments to ADO...")
                    for c in comments:
                        try:
                            self.ado_client.post_comment(
                                repo_id=repo_id,
                                pr_id=pr_id,
                                comment_text=c.get("comment", ""),
                                file_path=c.get("filePath"),
                                line_num=c.get("line"),
                            )
                            print(f"  ✓ Posted comment on {c.get('filePath')}:{c.get('line')}")
                        except Exception as e:
                            print(f"  ✗ Failed to post comment on {c.get('filePath')}: {e}", file=sys.stderr)

                print(f"[ApprovalGate] Setting PR vote to {chosen_vote}...")
                try:
                    self.ado_client.set_vote(repo_id=repo_id, pr_id=pr_id, vote=chosen_vote)
                    print(f"✅ Successfully cast vote ({chosen_vote}) on PR #{pr_id} in Azure DevOps!")
                    return True
                except Exception as e:
                    print(f"❌ Failed to cast vote on PR #{pr_id}: {e}", file=sys.stderr)
                    return False
            else:
                print("Invalid option. Please choose A, S, W, R, V, or X.")
