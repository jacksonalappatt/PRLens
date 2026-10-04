"""Codex CLI Review Harness."""

import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from .base import BaseHarness, HarnessResult, parse_review_report


class CodexHarness(BaseHarness):
    name = "codex"
    display_name = "Codex CLI (codex-cli)"
    DEFAULT_REASONING_MODELS: Dict[str, str] = {
        "high": "gpt-6",
        "medium": "gpt-6-luna",
        "low": "gpt-6-luna",
    }

    def check_availability(self) -> Tuple[bool, str]:
        cmd_path = shutil.which("codex") or shutil.which("codex.cmd")
        if not cmd_path:
            return False, "codex binary not found in PATH"
        try:
            res = subprocess.run([cmd_path, "--version"], capture_output=True, text=True, timeout=5)
            version = res.stdout.strip() or "Installed"
            return True, version
        except Exception as e:
            return False, str(e)

    def run_review(
        self,
        worktree_path: Path,
        pr_info: dict,
        diff_text: str,
        instructions_path: Path,
        output_file: Path,
        model_name: Optional[str] = None,
        reasoning: str = "high",
    ) -> HarnessResult:
        cmd_path = shutil.which("codex") or shutil.which("codex.cmd")
        if not cmd_path:
            return HarnessResult(success=False, error_message="Codex CLI executable not found.")

        resolved_model = model_name or self.resolve_model(reasoning)
        prompt = self.build_prompt(
            pr_info, instructions_path, output_file, model_name=resolved_model, reasoning=reasoning
        )
        start_time = time.time()

        cmd = [
            cmd_path,
            "exec",
            prompt,
            "-C",
            str(worktree_path),
            "-o",
            str(output_file.resolve()),
            "-s",
            "read-only",
            "-a",
            "never",
            "--add-dir",
            str(output_file.parent.resolve()),
            "--color",
            "never",
        ]

        if resolved_model:
            cmd.extend(["-m", resolved_model])

        if reasoning in ["low", "medium", "high"]:
            cmd.extend(["-c", f'model_reasoning_effort="{reasoning}"'])

        model_info = f" with model '{resolved_model}' [reasoning: {reasoning}]" if resolved_model else ""
        print(f"[CodexHarness] Executing static Codex review (read-only sandbox){model_info} in {worktree_path}...")
        try:
            process = subprocess.run(
                cmd,
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
                    error_message=f"Codex completed with exit code {process.returncode} but produced no report.",
                    model_name=resolved_model,
                    reasoning=reasoning,
                )

            vote, comments = parse_review_report(report_text)
            return HarnessResult(
                success=True,
                report_markdown=report_text,
                recommended_vote=vote,
                comments=comments,
                raw_log=raw_log,
                duration_seconds=duration,
                model_name=resolved_model,
                reasoning=reasoning,
            )

        except subprocess.TimeoutExpired:
            return HarnessResult(
                success=False,
                error_message="Codex review execution timed out after 900 seconds.",
                duration_seconds=time.time() - start_time,
                model_name=resolved_model,
                reasoning=reasoning,
            )
        except Exception as e:
            return HarnessResult(
                success=False,
                error_message=f"Codex execution failed: {e}",
                duration_seconds=time.time() - start_time,
                model_name=resolved_model,
                reasoning=reasoning,
            )
