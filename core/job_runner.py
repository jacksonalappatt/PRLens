"""Job orchestration and execution engine."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from harnesses.base import BaseHarness, HarnessResult

from .ado_client import AdoClient
from .worktree_manager import WorktreeManager


class JobRunner:
    def __init__(
        self,
        ado_client: AdoClient,
        worktree_manager: WorktreeManager,
        harness: BaseHarness,
        jobs_dir: Path,
        instructions_path: Path,
    ):
        self.ado_client = ado_client
        self.worktree_manager = worktree_manager
        self.harness = harness
        self.jobs_dir = jobs_dir.resolve()
        self.instructions_path = instructions_path.resolve()
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.jobs_dir / "registry.json"
        self._ensure_registry()

    def _ensure_registry(self):
        if not self.registry_file.exists():
            self._save_registry({})

    def _load_registry(self) -> Dict[str, Any]:
        try:
            if self.registry_file.exists():
                return json.loads(self.registry_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[JobRunner] Warning loading registry: {e}", file=sys.stderr)
        return {}

    def _save_registry(self, data: Dict[str, Any]):
        self.registry_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_pr_processed(self, pr_id: int) -> bool:
        registry = self._load_registry()
        job = registry.get(str(pr_id))
        if not job:
            return False
        return job.get("status") in ["COMPLETED", "APPROVED", "SUBMITTED"]

    def set_job_status(self, pr_id: int, status: str, extra: Optional[Dict[str, Any]] = None):
        registry = self._load_registry()
        key = str(pr_id)
        if key not in registry:
            registry[key] = {"pr_id": pr_id}
        registry[key]["status"] = status
        registry[key]["updated_at"] = datetime.now(timezone.utc).isoformat()
        if extra:
            registry[key].update(extra)
        self._save_registry(registry)

    def process_pr(self, pr_info: Dict[str, Any]) -> bool:
        pr_id = pr_info["pr_id"]
        title = pr_info.get("title", "")
        source_branch = pr_info.get("sourceBranch", "")
        target_branch = pr_info.get("targetBranch", "")

        print("\n" + "=" * 70)
        print(f"🚀 [JobRunner] Starting Review for PR #{pr_id}: {title}")
        print(f"   Branches: {source_branch} -> {target_branch}")
        print(f"   Harness: {self.harness.display_name}")
        print("=" * 70)

        job_dir = self.jobs_dir / str(pr_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "job.json").write_text(json.dumps(pr_info, indent=2), encoding="utf-8")

        self.set_job_status(
            pr_id,
            "RUNNING",
            {"title": title, "harness": self.harness.name, "started_at": datetime.now(timezone.utc).isoformat()},
        )

        worktree_path = None
        try:
            worktree_path, diff_text = self.worktree_manager.setup_worktree(
                pr_id=pr_id, source_ref=source_branch, target_ref=target_branch
            )
            (job_dir / "diff.patch").write_text(diff_text, encoding="utf-8")

            report_file = job_dir / "review_report.md"
            print(f"[JobRunner] Invoking {self.harness.display_name} in isolated worktree...")
            result: HarnessResult = self.harness.run_review(
                worktree_path=worktree_path,
                pr_info=pr_info,
                diff_text=diff_text,
                instructions_path=self.instructions_path,
                output_file=report_file,
            )

            (job_dir / "harness.log").write_text(result.raw_log, encoding="utf-8")

            if result.success:
                print(f"\n🎉 [JobRunner] Review completed successfully in {result.duration_seconds:.1f}s!")
                print(f"   Report: {report_file}")
                print(f"   Recommended Vote: {result.recommended_vote}")
                print(f"   Inline Comments: {len(result.comments)}")

                self.set_job_status(
                    pr_id,
                    "COMPLETED",
                    {
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "recommended_vote": result.recommended_vote,
                        "comments_count": len(result.comments),
                        "report_file": str(report_file),
                        "duration_seconds": result.duration_seconds,
                    },
                )
                return True
            else:
                print(f"❌ [JobRunner] Harness failed: {result.error_message}", file=sys.stderr)
                self.set_job_status(
                    pr_id,
                    "FAILED",
                    {"failed_at": datetime.now(timezone.utc).isoformat(), "error": result.error_message},
                )
                return False

        except Exception as e:
            print(f"❌ [JobRunner] Unexpected error processing PR #{pr_id}: {e}", file=sys.stderr)
            self.set_job_status(pr_id, "ERROR", {"failed_at": datetime.now(timezone.utc).isoformat(), "error": str(e)})
            return False

        finally:
            if worktree_path:
                try:
                    self.worktree_manager.cleanup_worktree(pr_id)
                except Exception as e:
                    print(f"[JobRunner] Warning during worktree cleanup: {e}", file=sys.stderr)
