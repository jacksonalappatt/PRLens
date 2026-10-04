"""Git worktree manager for isolated PR review checkouts."""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple


class WorktreeManager:
    def __init__(self, repo_path: Path, worktrees_dir: Path):
        self.repo_path = repo_path.resolve()
        self.worktrees_dir = worktrees_dir.resolve()
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

    def _run_git(self, args: list, cwd: Path = None) -> subprocess.CompletedProcess:
        target_cwd = cwd or self.repo_path
        cmd = ["git"] + args
        return subprocess.run(
            cmd, cwd=str(target_cwd), capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

    def _clean_ref(self, ref_name: str) -> str:
        if ref_name.startswith("refs/heads/"):
            return ref_name[len("refs/heads/") :]
        return ref_name

    def setup_worktree(self, pr_id: int, source_ref: str, target_ref: str) -> Tuple[Path, str]:
        """Creates an isolated git worktree for the given PR and returns (worktree_path, diff_content)."""
        source_branch = self._clean_ref(source_ref)
        target_branch = self._clean_ref(target_ref)
        worktree_name = f"pr-{pr_id}"
        worktree_path = self.worktrees_dir / worktree_name
        local_branch_name = f"pr-review-{pr_id}"

        # 1. Fetch remote tracking refs into refs/remotes/origin/*
        print(f"[Worktree] Fetching origin for {source_branch} and {target_branch}...")
        self._run_git(["fetch", "origin", source_branch])
        self._run_git(["fetch", "origin", target_branch])

        # 2. Cleanup any previous worktree with this name
        if worktree_path.exists():
            self.cleanup_worktree(pr_id)

        # 3. Add isolated worktree
        print(f"[Worktree] Creating worktree at {worktree_path} on branch {source_branch}...")
        add_res = self._run_git(
            ["worktree", "add", "-B", local_branch_name, str(worktree_path), f"refs/remotes/origin/{source_branch}"]
        )
        if add_res.returncode != 0:
            # Fallback without refs/remotes/ prefix if local branch exists
            add_res = self._run_git(
                ["worktree", "add", "-B", local_branch_name, str(worktree_path), f"origin/{source_branch}"]
            )
            if add_res.returncode != 0:
                add_res = self._run_git(["worktree", "add", "-B", local_branch_name, str(worktree_path), source_branch])
                if add_res.returncode != 0:
                    raise RuntimeError(f"Failed to create git worktree: {add_res.stderr.strip()}")

        # 4. Generate 3-dot merge-base diff against refs/remotes/origin/{target_branch}
        print(f"[Worktree] Generating diff against origin/{target_branch}...")
        diff_res = self._run_git(["diff", f"refs/remotes/origin/{target_branch}...HEAD"], cwd=worktree_path)
        if diff_res.returncode != 0:
            diff_res = self._run_git(["diff", f"origin/{target_branch}...HEAD"], cwd=worktree_path)
        diff_text = diff_res.stdout if diff_res.returncode == 0 else ""

        # Write diff.patch into worktree for quick inspection
        (worktree_path / "pr_diff.patch").write_text(diff_text, encoding="utf-8")

        return worktree_path, diff_text

    def cleanup_worktree(self, pr_id: int):
        """Removes the worktree and temporary branch cleanly."""
        worktree_name = f"pr-{pr_id}"
        worktree_path = self.worktrees_dir / worktree_name
        local_branch_name = f"pr-review-{pr_id}"

        print(f"[Worktree] Cleaning up worktree {worktree_name}...")
        self._run_git(["worktree", "remove", "--force", str(worktree_path)])
        self._run_git(["branch", "-D", local_branch_name])
        self._run_git(["worktree", "prune"])

        if worktree_path.exists():
            try:
                shutil.rmtree(worktree_path, ignore_errors=True)
            except Exception as e:
                print(f"[Worktree] Warning removing folder: {e}", file=sys.stderr)
