"""Antigravity Headless Agent / AGY Review Harness."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .base import BaseHarness, HarnessResult, parse_review_report


class AntigravityHarness(BaseHarness):
    name = "antigravity"
    display_name = "Antigravity Agent (Headless)"
    DEFAULT_REASONING_MODELS: Dict[str, str] = {
        "high": "3.8",
        "medium": "3.8",
        "low": "3.8",
    }

    AGENTAPI_PATHS = [
        Path(os.path.expanduser(r"~\.gemini\antigravity\bin\agentapi.bat")),
        Path(os.environ.get("USERPROFILE", "")) / r".gemini\antigravity\bin\agentapi.bat",
        Path(os.environ.get("LOCALAPPDATA", "")) / r"Programs\antigravity\resources\bin\language_server.exe",
        Path(r"C:\Users\jackson.alappatt\AppData\Local\Programs\antigravity\resources\bin\language_server.exe"),
    ]

    IDE_PATHS = [
        Path(os.path.expanduser(r"~\AppData\Local\Programs\Antigravity IDE\bin\antigravity-ide.cmd")),
        Path(os.environ.get("LOCALAPPDATA", "")) / r"Programs\Antigravity IDE\bin\antigravity-ide.cmd",
        Path(os.path.expanduser(r"~\AppData\Roaming\Antigravity\bin\agy-node.cmd")),
        Path(os.environ.get("APPDATA", "")) / r"Antigravity\bin\agy-node.cmd",
    ]

    def _get_agentapi_cmd(self) -> Optional[List[str]]:
        for candidate in self.AGENTAPI_PATHS:
            if candidate.exists():
                if candidate.name.lower().endswith((".bat", ".cmd")):
                    return [str(candidate)]
                elif candidate.name.lower() == "language_server.exe":
                    return [str(candidate), "agentapi"]
        which_agentapi = shutil.which("agentapi")
        if which_agentapi:
            return [which_agentapi]
        return None

    def _get_ide_executable(self) -> Optional[str]:
        for candidate in self.IDE_PATHS:
            if candidate.exists():
                return str(candidate)
        return shutil.which("antigravity-ide") or shutil.which("agy")

    @staticmethod
    def _discover_language_server_env() -> Dict[str, str]:
        """Discovers active Antigravity Language Server address and CSRF token when run from a standalone terminal."""
        env_vars = {}
        if os.environ.get("ANTIGRAVITY_LS_ADDRESS"):
            env_vars["ANTIGRAVITY_LS_ADDRESS"] = os.environ["ANTIGRAVITY_LS_ADDRESS"]
        if os.environ.get("ANTIGRAVITY_CSRF_TOKEN"):
            env_vars["ANTIGRAVITY_CSRF_TOKEN"] = os.environ["ANTIGRAVITY_CSRF_TOKEN"]

        if not (env_vars.get("ANTIGRAVITY_LS_ADDRESS") and env_vars.get("ANTIGRAVITY_CSRF_TOKEN")):
            ps_cmd = (
                "Get-CimInstance Win32_Process -Filter \"Name = 'language_server.exe' and CommandLine like '%--csrf_token%'\" "
                "| ForEach-Object { "
                "    $pid_num = $_.ProcessId; "
                "    $cmd = $_.CommandLine; "
                "    $port = (Get-NetTCPConnection -OwningProcess $pid_num -State Listen | Sort-Object LocalPort -Descending | Select-Object -First 1).LocalPort; "
                "    $tok = if ($cmd -match '--csrf_token\\s+([a-zA-Z0-9\\-]+)') { $matches[1] } else { '' }; "
                "    \"$port|$tok\" "
                "}"
            )
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                for line in res.stdout.strip().splitlines():
                    line = line.strip()
                    if "|" in line:
                        port, token = line.split("|", 1)
                        port = port.strip()
                        token = token.strip()
                        if port.isdigit():
                            env_vars["ANTIGRAVITY_LS_ADDRESS"] = f"localhost:{port}"
                        if token:
                            env_vars["ANTIGRAVITY_CSRF_TOKEN"] = token
                        if env_vars.get("ANTIGRAVITY_LS_ADDRESS"):
                            break
            except Exception:
                pass

        env_vars["ANTIGRAVITY_PROJECT_ID"] = os.environ.get("ANTIGRAVITY_PROJECT_ID") or "outside-of-project"
        env_vars["ANTIGRAVITY_AGENT"] = "1"
        env_vars["ANTIGRAVITY_APP_DATA_DIR"] = (
            os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
            or str(Path(os.path.expanduser("~/.gemini/antigravity")).resolve())
        )

        return env_vars

    def check_availability(self) -> Tuple[bool, str]:
        cmd = self._get_agentapi_cmd()
        if cmd:
            env = self._discover_language_server_env()
            addr = env.get("ANTIGRAVITY_LS_ADDRESS")
            if addr:
                return True, f"Antigravity Headless Agent (Active on {addr})"
            return True, "Antigravity Headless Agent (Native Background)"
        ide_exe = self._get_ide_executable()
        if ide_exe:
            return True, "Antigravity IDE (GUI)"
        return False, "Antigravity Agent API or IDE not found"

    def _resolve_agentapi_tier(self, model_name: Optional[str], reasoning: str) -> str:
        tier_map = {
            "high": "pro",
            "medium": "flash",
            "low": "flash_lite",
        }
        if model_name:
            clean = model_name.strip().lower().replace("-", "_")
            if clean in ("pro", "flash", "flash_lite"):
                return clean
        return tier_map.get(reasoning.lower(), "pro")

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
        agentapi_cmd = self._get_agentapi_cmd()
        if agentapi_cmd:
            return self._run_headless_agentapi(
                agentapi_cmd=agentapi_cmd,
                worktree_path=worktree_path,
                pr_info=pr_info,
                diff_text=diff_text,
                instructions_path=instructions_path,
                output_file=output_file,
                model_name=model_name,
                reasoning=reasoning,
            )

        ide_exe = self._get_ide_executable()
        if ide_exe:
            return self._run_ide_gui(
                ide_exe=ide_exe,
                worktree_path=worktree_path,
                pr_info=pr_info,
                diff_text=diff_text,
                instructions_path=instructions_path,
                output_file=output_file,
                model_name=model_name,
                reasoning=reasoning,
            )

        return HarnessResult(success=False, error_message="Antigravity agent or IDE binary not found.")

    def _run_headless_agentapi(
        self,
        agentapi_cmd: List[str],
        worktree_path: Path,
        pr_info: dict,
        diff_text: str,
        instructions_path: Path,
        output_file: Path,
        model_name: Optional[str] = None,
        reasoning: str = "high",
    ) -> HarnessResult:
        start_time = time.time()
        tier = self._resolve_agentapi_tier(model_name, reasoning)

        prompt_file = worktree_path / "REVIEW_PROMPT.md"
        prompt_content = self.build_prompt(
            pr_info, instructions_path, output_file, model_name=tier, reasoning=reasoning
        )
        prompt_file.write_text(prompt_content, encoding="utf-8")

        diff_file = worktree_path / "pr_diff.patch"
        diff_file.write_text(diff_text, encoding="utf-8")

        output_file.parent.mkdir(parents=True, exist_ok=True)
        if output_file.exists():
            try:
                output_file.unlink()
            except Exception:
                pass

        pr_id = pr_info.get("pr_id") or pr_info.get("id") or "PR"
        pr_title = pr_info.get("title", "")
        repo_name = pr_info.get("repository") or ""
        org = pr_info.get("organization") or ""
        project = pr_info.get("project") or ""

        context_lines = []
        if org:
            context_lines.append(f"- Organization: {org}")
        if project:
            context_lines.append(f"- Project: {project}")
        if repo_name:
            context_lines.append(f"- Repository: {repo_name}")
        context_lines.append(f"- Local Worktree Workspace: {worktree_path.resolve()}")
        context_str = "\n".join(context_lines)

        launch_prompt = (
            f"You are conducting an autonomous code review for Azure DevOps PR #{pr_id}: '{pr_title}'.\n"
            f"{context_str}\n\n"
            f"Instructions:\n"
            f"1. Read the complete review instructions and diff in {prompt_file.resolve()}.\n"
            f"2. Read the PR git patch in {diff_file.resolve()}.\n"
            f"3. Strictly following all instructions and quality guidelines, perform your architectural and logic code review.\n"
            f"4. Use your file writing tool to write the complete review Markdown report directly to: {output_file.resolve()}.\n"
            f"5. Also include your full review Markdown report in your final response."
        )

        child_env = dict(os.environ)
        if not child_env.get("ANTIGRAVITY_LS_ADDRESS") or not child_env.get("ANTIGRAVITY_CSRF_TOKEN"):
            discovered = self._discover_language_server_env()
            child_env.update(discovered)
            os.environ.update(discovered)

        if not child_env.get("ANTIGRAVITY_LS_ADDRESS"):
            return HarnessResult(
                success=False,
                error_message=(
                    "Antigravity Language Server is not running. "
                    "Please launch Antigravity Desktop or Antigravity IDE so the local language server is active, "
                    "or select the Codex CLI harness for standalone execution."
                ),
                duration_seconds=time.time() - start_time,
                model_name=tier,
                reasoning=reasoning,
            )

        # Essential project environment variables required by the language server
        child_env["ANTIGRAVITY_PROJECT_ID"] = child_env.get("ANTIGRAVITY_PROJECT_ID") or "outside-of-project"
        child_env["ANTIGRAVITY_AGENT"] = "1"
        child_env["ANTIGRAVITY_APP_DATA_DIR"] = (
            child_env.get("ANTIGRAVITY_APP_DATA_DIR")
            or str(Path(os.path.expanduser("~/.gemini/antigravity")).resolve())
        )

        cmd = [
            *agentapi_cmd,
            "new-conversation",
            f"--model={tier}",
            f"--title=PRLens Review PR #{pr_id}",
            launch_prompt,
        ]

        print(
            f"[AntigravityHarness] Launching 100% headless background review for PR #{pr_id} "
            f"(Model Tier: {tier}, Reasoning: {reasoning.upper()})..."
        )
        try:
            process = subprocess.run(
                cmd,
                cwd=str(worktree_path),
                env=child_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except Exception as e:
            return HarnessResult(
                success=False,
                error_message=f"Failed to execute Antigravity agentapi: {e}",
                duration_seconds=time.time() - start_time,
                model_name=tier,
                reasoning=reasoning,
            )

        if process.returncode != 0:
            return HarnessResult(
                success=False,
                error_message=f"Antigravity agentapi failed: {process.stderr or process.stdout}",
                raw_log=f"STDOUT:\n{process.stdout}\n\nSTDERR:\n{process.stderr}",
                duration_seconds=time.time() - start_time,
                model_name=tier,
                reasoning=reasoning,
            )

        convo_id = None
        try:
            data = json.loads(process.stdout)
            convo_id = data.get("response", {}).get("newConversation", {}).get("conversationId")
        except Exception:
            pass

        if not convo_id:
            return HarnessResult(
                success=False,
                error_message="Could not obtain conversation ID from Antigravity agentapi.",
                raw_log=process.stdout,
                duration_seconds=time.time() - start_time,
                model_name=tier,
                reasoning=reasoning,
            )

        print(f"[AntigravityHarness] Headless agent active (Conversation ID: {convo_id}). Monitoring progress...")

        transcript_path = (
            Path(os.path.expanduser(r"~\.gemini\antigravity\brain"))
            / convo_id
            / ".system_generated"
            / "logs"
            / "transcript.jsonl"
        )

        poll_timeout = 600  # 10 minutes
        poll_deadline = time.time() + poll_timeout
        report_text = ""
        last_step_index = -1
        convo_dir = Path(os.path.expanduser(r"~\.gemini\antigravity\brain")) / convo_id

        while time.time() < poll_deadline:
            time.sleep(3)

            # 1. First priority: Check if agent saved the report directly via write_to_file
            if output_file.exists() and output_file.stat().st_size > 80:
                try:
                    candidate = output_file.read_text(encoding="utf-8", errors="replace")
                    if self.is_valid_report(candidate):
                        report_text = candidate
                        break
                except Exception:
                    pass

            # 2. Second priority: Check if agent saved a report artifact in its brain directory
            if convo_dir.exists():
                for md_file in convo_dir.glob("*.md"):
                    if md_file.name.lower() not in ("review_prompt.md", "prompt.md"):
                        try:
                            md_content = md_file.read_text(encoding="utf-8", errors="replace")
                            if self.is_valid_report(md_content):
                                report_text = md_content
                                break
                        except Exception:
                            pass
            if report_text:
                break

            # 3. Third priority: Inspect transcript for completed MODEL response
            agent_finished = False
            if transcript_path.exists():
                try:
                    lines = transcript_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
                    for line in lines:
                        if not line.strip():
                            continue
                        step = json.loads(line)
                        idx = step.get("step_index", 0)
                        if idx > last_step_index:
                            last_step_index = idx
                            if step.get("type") == "PLANNER_RESPONSE" and step.get("tool_calls"):
                                for tc in step.get("tool_calls", []):
                                    summary = tc.get("args", {}).get("toolSummary", "")
                                    action = tc.get("args", {}).get("toolAction", "")
                                    name = tc.get("name", "")
                                    msg = (summary or action or name).strip('"\'' )
                                    if msg:
                                        print(f"   [Antigravity] {msg}")

                        # Strictly ignore anything not from MODEL
                        if step.get("source") != "MODEL":
                            continue

                        content = step.get("content", "")

                        # Agent completed final response without pending tool calls
                        if (
                            step.get("type") == "PLANNER_RESPONSE"
                            and step.get("status") == "DONE"
                            and not step.get("tool_calls")
                        ):
                            if content and self.is_valid_report(content):
                                report_text = content
                                break
                            agent_finished = True
                    if report_text:
                        break
                except Exception:
                    pass

            if agent_finished:
                # Give filesystem a brief moment to sync any final report writes
                time.sleep(2)
                if output_file.exists() and output_file.stat().st_size > 80:
                    try:
                        candidate = output_file.read_text(encoding="utf-8", errors="replace")
                        if self.is_valid_report(candidate):
                            report_text = candidate
                            break
                    except Exception:
                        pass
                if convo_dir.exists():
                    for md_file in convo_dir.glob("*.md"):
                        if md_file.name.lower() not in ("review_prompt.md", "prompt.md"):
                            try:
                                md_content = md_file.read_text(encoding="utf-8", errors="replace")
                                if self.is_valid_report(md_content):
                                    report_text = md_content
                                    break
                            except Exception:
                                pass
                break

        duration = time.time() - start_time
        if not report_text:
            if output_file.exists():
                try:
                    content = output_file.read_text(encoding="utf-8", errors="replace")
                    if not self.is_valid_report(content):
                        output_file.unlink(missing_ok=True)
                except Exception:
                    pass
            return HarnessResult(
                success=False,
                error_message=f"Antigravity headless review timed out after {int(duration)}s without a valid report.",
                duration_seconds=duration,
                model_name=tier,
                reasoning=reasoning,
            )

        try:
            output_file.write_text(report_text, encoding="utf-8")
        except Exception:
            pass

        vote, comments = parse_review_report(report_text)
        return HarnessResult(
            success=True,
            report_markdown=report_text,
            recommended_vote=vote,
            comments=comments,
            raw_log=f"Conversation ID: {convo_id}\nModel Tier: {tier}\nDuration: {int(duration)}s",
            duration_seconds=duration,
            model_name=tier,
            reasoning=reasoning,
        )

    def _run_ide_gui(
        self,
        ide_exe: str,
        worktree_path: Path,
        pr_info: dict,
        diff_text: str,
        instructions_path: Path,
        output_file: Path,
        model_name: Optional[str] = None,
        reasoning: str = "high",
    ) -> HarnessResult:
        resolved_model = model_name or self.resolve_model(reasoning)
        prompt = self.build_prompt(
            pr_info, instructions_path, output_file, model_name=resolved_model, reasoning=reasoning
        )
        start_time = time.time()

        prompt_file = worktree_path / "REVIEW_PROMPT.md"
        prompt_file.write_text(prompt, encoding="utf-8")

        diff_file = worktree_path / "pr_diff.patch"

        cmd = [
            ide_exe,
            "chat",
            "-",
            "-m",
            "agent",
            "-r",
            "-a",
            str(diff_file.resolve()),
            "-a",
            str(prompt_file.resolve()),
        ]

        model_info = f" (Model: {resolved_model}, Reasoning: {reasoning.upper()})" if resolved_model else ""
        print(f"[AntigravityHarness] Invoking Antigravity IDE agent session{model_info} in {worktree_path}...")
        try:
            process = subprocess.run(
                cmd,
                cwd=str(worktree_path),
                input=prompt,
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
                candidate = output_file.read_text(encoding="utf-8", errors="replace")
                if self.is_valid_report(candidate):
                    report_text = candidate

            if not report_text and process.stdout and self.is_valid_report(process.stdout):
                report_text = process.stdout
                output_file.write_text(report_text, encoding="utf-8")

            if not report_text:
                print(
                    "[AntigravityHarness] Review session dispatched to your active Antigravity IDE window."
                )
                print(
                    f"   Worktree active at: {worktree_path}\n"
                    f"   Waiting for review report to be saved at: {output_file.resolve()} (up to 300s)..."
                )
                poll_deadline = time.time() + 300
                while time.time() < poll_deadline:
                    time.sleep(3)
                    if output_file.exists() and output_file.stat().st_size > 80:
                        candidate = output_file.read_text(encoding="utf-8", errors="replace")
                        if self.is_valid_report(candidate):
                            report_text = candidate
                            break

            if not report_text:
                if output_file.exists():
                    try:
                        content = output_file.read_text(encoding="utf-8", errors="replace")
                        if not self.is_valid_report(content):
                            output_file.unlink(missing_ok=True)
                    except Exception:
                        pass

                return HarnessResult(
                    success=False,
                    raw_log=raw_log,
                    duration_seconds=time.time() - start_time,
                    error_message=(
                        f"Antigravity IDE session timed out waiting for review report at {output_file.name}. "
                        "Antigravity IDE operates via the interactive editor window. "
                        "For 100% headless autonomous background reviews (zero GUI windows), select Codex CLI."
                    ),
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
                error_message="Antigravity review execution timed out.",
                duration_seconds=time.time() - start_time,
                model_name=resolved_model,
                reasoning=reasoning,
            )
        except Exception as e:
            return HarnessResult(
                success=False,
                error_message=f"Antigravity execution failed: {e}",
                duration_seconds=time.time() - start_time,
                model_name=resolved_model,
                reasoning=reasoning,
            )

