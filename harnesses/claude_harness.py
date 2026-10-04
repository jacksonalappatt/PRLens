"""Claude Code CLI Review Harness."""

import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from .base import BaseHarness, HarnessResult, parse_review_report


class ClaudeHarness(BaseHarness):
    name = "claude"
    display_name = "Claude Code CLI (@anthropic-ai/claude-code)"
    DEFAULT_REASONING_MODELS: Dict[str, str] = {
        "high": "claude-3-7-sonnet",
        "medium": "claude-3-5-sonnet",
        "low": "claude-3-5-haiku",
    }

    def _get_command(self) -> Optional[list]:
        claude_bin = shutil.which("claude") or shutil.which("claude.cmd")
        if claude_bin:
            return [claude_bin]
        return None

    def check_availability(self) -> Tuple[bool, str]:
        cmd = self._get_command()
        if not cmd:
            return False, "Not found in PATH (Install via: npm i -g @anthropic-ai/claude-code)"
        try:
            res = subprocess.run(cmd + ["--version"], capture_output=True, text=True, timeout=5)
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
        cmd = self._get_command()
        if not cmd:
            return HarnessResult(
                success=False,
                error_message="Claude Code CLI not installed. Run 'npm i -g @anthropic-ai/claude-code'.",
            )

        resolved_model = model_name or self.resolve_model(reasoning)
        prompt = self.build_prompt(
            pr_info, instructions_path, output_file, model_name=resolved_model, reasoning=reasoning
        )
        start_time = time.time()

        full_cmd = [
            *cmd,
            "-p",
            prompt,
            "--dangerously-skip-permissions",
        ]
        if resolved_model:
            full_cmd.extend(["--model", resolved_model])

        model_info = f" with model '{resolved_model}' [reasoning: {reasoning}]" if resolved_model else ""
        print(f"[ClaudeHarness] Invoking Claude Code CLI non-interactively{model_info} in {worktree_path}...")
        try:
            process = subprocess.run(
                full_cmd,
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
                    error_message="Claude completed but produced no review report.",
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
                error_message="Claude review execution timed out.",
                duration_seconds=time.time() - start_time,
                model_name=resolved_model,
                reasoning=reasoning,
            )
        except Exception as e:
            return HarnessResult(
                success=False,
                error_message=f"Claude execution failed: {e}",
                duration_seconds=time.time() - start_time,
                model_name=resolved_model,
                reasoning=reasoning,
            )
