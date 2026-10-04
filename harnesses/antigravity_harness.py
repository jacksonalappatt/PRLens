"""Antigravity IDE / AGY CLI Review Harness."""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from .base import BaseHarness, HarnessResult, parse_review_report


class AntigravityHarness(BaseHarness):
    name = "antigravity"
    display_name = "Antigravity IDE / AGY"

    KNOWN_PATHS = [
        Path(os.path.expanduser(r"~\AppData\Local\Programs\Antigravity IDE\bin\antigravity-ide.cmd")),
        Path(os.environ.get("LOCALAPPDATA", "")) / r"Programs\Antigravity IDE\bin\antigravity-ide.cmd",
        Path(os.path.expanduser(r"~\AppData\Roaming\Antigravity\bin\agy-node.cmd")),
        Path(os.environ.get("APPDATA", "")) / r"Antigravity\bin\agy-node.cmd",
    ]

    def _get_executable(self) -> Optional[str]:
        for candidate in self.KNOWN_PATHS:
            if candidate.exists():
                return str(candidate)
        return shutil.which("antigravity-ide") or shutil.which("agy")

    def check_availability(self) -> Tuple[bool, str]:
        exe = self._get_executable()
        if not exe:
            return False, "Antigravity IDE or AGY CLI not found"
        try:
            res = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=5)
            version = res.stdout.strip() or "Installed"
            return True, f"Antigravity IDE ({version})"
        except Exception:
            return True, "Antigravity IDE (Detected)"

    def run_review(
        self, worktree_path: Path, pr_info: dict, diff_text: str, instructions_path: Path, output_file: Path
    ) -> HarnessResult:
        exe = self._get_executable()
        if not exe:
            return HarnessResult(success=False, error_message="Antigravity IDE binary not found.")

        prompt = self.build_prompt(pr_info, instructions_path, output_file)
        start_time = time.time()

        prompt_file = worktree_path / "REVIEW_PROMPT.md"
        prompt_file.write_text(prompt, encoding="utf-8")

        diff_file = worktree_path / "pr_diff.patch"

        cmd = [exe, "chat", prompt, "-m", "agent", "-a", str(diff_file.resolve())]

        print(f"[AntigravityHarness] Invoking Antigravity IDE agent session in {worktree_path}...")
        try:
            process = subprocess.run(
                cmd,
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=900,
            )
            duration = time.time() - start_time
            raw_log = f"STDOUT:\n{process.stdout}\n\nSTDERR:\n{process.stderr}"

            report_text = ""
            if output_file.exists() and output_file.stat().st_size > 0:
                report_text = output_file.read_text(encoding="utf-8", errors="replace")
            elif process.stdout:
                report_text = process.stdout
                output_file.write_text(report_text, encoding="utf-8")

            if not report_text:
                return HarnessResult(
                    success=False,
                    raw_log=raw_log,
                    duration_seconds=duration,
                    error_message="Antigravity completed but output report was not found.",
                )

            vote, comments = parse_review_report(report_text)
            return HarnessResult(
                success=True,
                report_markdown=report_text,
                recommended_vote=vote,
                comments=comments,
                raw_log=raw_log,
                duration_seconds=duration,
            )

        except subprocess.TimeoutExpired:
            return HarnessResult(
                success=False,
                error_message="Antigravity review execution timed out.",
                duration_seconds=time.time() - start_time,
            )
        except Exception as e:
            return HarnessResult(
                success=False,
                error_message=f"Antigravity execution failed: {e}",
                duration_seconds=time.time() - start_time,
            )
