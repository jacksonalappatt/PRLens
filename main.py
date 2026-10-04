#!/usr/bin/env python3
"""PRLens: Autonomous Azure DevOps PR Review Agent."""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

# Setup paths and Windows UTF-8 encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from core.ado_client import AdoClient
from core.approval_gate import ApprovalGate
from core.job_runner import JobRunner
from core.workspace_detector import resolve_workspace
from core.worktree_manager import WorktreeManager
from harnesses.registry import HARNESS_REGISTRY, get_harness, prompt_harness_selection
from server.poller import PrPoller
from server.webhook_server import WebhookServer


def check_harnesses():
    print("\n🔍 Checking Local AI Harnesses (Zero Direct APIs):")
    print("-" * 55)
    for key, harness in HARNESS_REGISTRY.items():
        avail, detail = harness.check_availability()
        symbol = "✅" if avail else "❌"
        print(f" {symbol} {harness.display_name:<35} {detail}")
    print("-" * 55 + "\n")


def main():
    parser = argparse.ArgumentParser(description="PRLens: Autonomous Azure DevOps PR Review Agent")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "review", "approve", "list", "status"],
        help="Action to execute (run daemon, review single PR, approve PR, list jobs)",
    )
    parser.add_argument("pr_id", nargs="?", type=int, help="Target PR ID for review or approve command")
    parser.add_argument(
        "--harness", choices=["codex", "antigravity", "claude"], help="Bypass interactive picker with specific harness"
    )
    parser.add_argument(
        "--tier",
        choices=["high", "medium", "low"],
        help="Model reasoning tier: high, medium, or low (overrides config.json)",
    )
    parser.add_argument(
        "--model",
        help="Explicit model name override (e.g. o3-mini, claude-3-7-sonnet)",
    )
    parser.add_argument("--workspace", help="Bypass interactive workspace prompt with specific repository path")
    parser.add_argument(
        "--check-harnesses", action="store_true", help="Display diagnostic status of all local AI harnesses"
    )
    args = parser.parse_args()

    if args.check_harnesses:
        check_harnesses()
        return

    config_file = PROJECT_DIR / "config.json"
    jobs_dir = PROJECT_DIR / "jobs"
    worktrees_dir = PROJECT_DIR / "worktrees"
    instructions_path = PROJECT_DIR / "instructions" / "AGENTS.md"

    # Quick read config for defaults
    cfg = {}
    if config_file.exists():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    pat_env = cfg.get("ado", {}).get("pat_env_var", "AZURE_DEVOPS_PAT")
    pat = (
        os.environ.get(pat_env)
        or os.environ.get("AZURE_DEVOPS_PAT")
        or os.environ.get("ADO_PAT")
        or os.environ.get("AZURE_DEVOPS_EXT_PAT")
    )
    if not pat:
        print(f"❌ Error: Missing Azure DevOps Personal Access Token in environment ({pat_env}).", file=sys.stderr)
        sys.exit(1)

    # Resolve Workspace (Requirement 3: Prompt user, auto-populate previous workspace)
    workspace_path, detected_ado = resolve_workspace(config_file, cli_override=args.workspace)
    org = detected_ado.get("organization") or cfg.get("ado", {}).get("organization", "")
    project = detected_ado.get("project") or cfg.get("ado", {}).get("project", "")
    repo_name = detected_ado.get("repository") or cfg.get("ado", {}).get("repository", "")

    # Initialize ADO client
    ado_client = AdoClient(org=org, project=project, pat=pat)
    try:
        user_info = ado_client.get_current_user_info()
    except Exception as e:
        print(f"❌ Failed to authenticate with Azure DevOps: {e}", file=sys.stderr)
        sys.exit(1)

    # 1. COMMAND: list
    if args.command in ["list", "status"]:
        reg_file = jobs_dir / "registry.json"
        reg = json.loads(reg_file.read_text(encoding="utf-8")) if reg_file.exists() else {}
        print("\n" + "=" * 70)
        print("📁 AZURE DEVOPS PR REVIEW JOBS REGISTRY")
        print("=" * 70)
        if not reg:
            print("No PR review jobs recorded yet.")
        else:
            for pid, j in reg.items():
                status = j.get("status", "UNKNOWN")
                status_icon = "✅" if status in ["COMPLETED", "APPROVED"] else "⏳" if status == "RUNNING" else "⚠️"
                print(
                    f"{status_icon} PR #{pid:<7} Status: {status:<12} Vote: {j.get('recommended_vote', 'N/A'):<4} Title: {j.get('title', '')[:40]}"
                )
        print("=" * 70 + "\n")
        return

    # 2. COMMAND: approve
    if args.command == "approve":
        if not args.pr_id:
            print(
                "Error: PR ID is required for approve command (e.g. 'python main.py approve <pr_id>')", file=sys.stderr
            )
            sys.exit(1)
        approval_gate = ApprovalGate(ado_client=ado_client, jobs_dir=jobs_dir)
        approval_gate.review_and_submit(args.pr_id)
        return

    # Interactive AI Harness Selection
    chosen_harness = None
    if args.harness:
        chosen_harness = get_harness(args.harness)
        if not chosen_harness:
            print(f"Unknown harness: {args.harness}", file=sys.stderr)
            sys.exit(1)
        print(f"🚀 Using specified AI Harness: {chosen_harness.display_name}")
    else:
        default_configured = cfg.get("harness", {}).get("default")
        chosen_harness = prompt_harness_selection(default_choice=default_configured)

    # Resolve Model Tier & Model Identifier (from config, overridden by --tier / --model)
    model_tier = (args.tier or cfg.get("model_tier", "high")).lower()
    custom_models = cfg.get("models", {}).get(chosen_harness.name, {})
    resolved_model = args.model or chosen_harness.resolve_model(model_tier, custom_models)

    worktree_mgr = WorktreeManager(repo_path=workspace_path, worktrees_dir=worktrees_dir)
    job_runner = JobRunner(
        ado_client=ado_client,
        worktree_manager=worktree_mgr,
        harness=chosen_harness,
        jobs_dir=jobs_dir,
        instructions_path=instructions_path,
        model_tier=model_tier,
        model_name=resolved_model,
    )
    approval_gate = ApprovalGate(ado_client=ado_client, jobs_dir=jobs_dir)

    # 3. COMMAND: review
    if args.command == "review":
        if not args.pr_id:
            print("Error: PR ID is required for review command (e.g. 'python main.py review <pr_id>')", file=sys.stderr)
            sys.exit(1)
        print(f"Fetching details for PR #{args.pr_id} from Azure DevOps...")
        try:
            details = ado_client.get_pr_details(repo_name, args.pr_id)
            pr_info = {
                "pr_id": args.pr_id,
                "title": details.get("title"),
                "description": details.get("description", ""),
                "createdBy": details.get("createdBy", {}).get("displayName"),
                "repository": details.get("repository", {}).get("name"),
                "repositoryId": details.get("repository", {}).get("id"),
                "sourceBranch": details.get("sourceRefName"),
                "targetBranch": details.get("targetRefName"),
            }
            job_runner.process_pr(pr_info)
            prompt_appr = (
                input("\nWould you like to open the approval gate now to submit to ADO? (y/N): ").strip().lower()
            )
            if prompt_appr == "y":
                approval_gate.review_and_submit(args.pr_id)
        except Exception as e:
            print(f"❌ Failed to run review on PR #{args.pr_id}: {e}", file=sys.stderr)
        return

    # 4. COMMAND: run (Daemon Mode)
    model_display = f"{resolved_model} ({model_tier.upper()})" if resolved_model else model_tier.upper()
    print("\n" + "=" * 70)
    print("🔍 PRLens: AUTONOMOUS AZURE DEVOPS PR REVIEW AGENT")
    print("=" * 70)
    print(f"  Organization : {org}")
    print(f"  Project      : {project}")
    print(f"  Repository   : {repo_name} ({workspace_path})")
    print(f"  Reviewer     : {user_info.get('displayName')} ({user_info.get('id')})")
    print(f"  AI Harness   : {chosen_harness.display_name} (Zero Direct APIs)")
    print(f"  Model Tier   : {model_display}")
    print("=" * 70)

    srv_cfg = cfg.get("server", {})
    webhook_port = srv_cfg.get("port", 7890)
    webhook_host = srv_cfg.get("host", "127.0.0.1")

    def on_webhook_pr(pr_info):
        pr_id = pr_info.get("pr_id")
        if not job_runner.is_pr_processed(pr_id):
            print(f"\n[WebhookTrigger] Triggering autonomous review for PR #{pr_id}...")
            job_runner.process_pr(pr_info)

    webhook_server = WebhookServer(
        host=webhook_host, port=webhook_port, secret=srv_cfg.get("secret", ""), on_pr_callback=on_webhook_pr
    )
    webhook_server.start(background=True)

    poll_cfg = cfg.get("polling", {})
    poll_interval = poll_cfg.get("interval_seconds", 60)
    poller = PrPoller(ado_client=ado_client, job_runner=job_runner, repo_id=repo_name, interval_seconds=poll_interval)
    poller.start(background=True)

    print("\n[PRLens] Background listeners active.")
    print(f"  - Webhook Listener : http://{webhook_host}:{webhook_port}/webhook")
    print(f"  - Background Poller: Active (checking every {poll_interval}s for '{repo_name}')")
    print("Press Ctrl+C to stop.\n")

    def shutdown_handler(sig, frame):
        print("\n[PRLens] Shutting down agent daemon gracefully...")
        poller.stop()
        webhook_server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown_handler(None, None)


if __name__ == "__main__":
    main()
