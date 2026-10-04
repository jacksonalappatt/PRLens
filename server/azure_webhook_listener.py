#!/usr/bin/env python3
"""Standalone Azure DevOps Webhook Listener."""

import json
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from pathlib import Path

# Setup import path
script_dir = Path(__file__).resolve().parent
agent_root = script_dir.parent
sys.path.insert(0, str(agent_root))

from server.webhook_server import WebhookServer


def main():
    config_file = agent_root / "config.json"
    port = 7890
    host = "0.0.0.0"
    secret = ""

    if config_file.exists():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            srv_cfg = cfg.get("server", {})
            port = srv_cfg.get("port", port)
            host = srv_cfg.get("host", "0.0.0.0")
            secret = srv_cfg.get("secret", secret)
        except Exception:
            pass

    def on_pr_event(pr_info):
        print(f"\n[azure-webhook-listener] Received PR #{pr_info.get('pr_id')}: {pr_info.get('title')}")
        print(f"  Author: {pr_info.get('createdBy')}")
        print(f"  Branches: {pr_info.get('sourceBranch')} -> {pr_info.get('targetBranch')}")

    server = WebhookServer(host=host, port=port, secret=secret, on_pr_callback=on_pr_event)
    print("=" * 65)
    print(f" PRLens: Azure DevOps Webhook Listener running on http://{host}:{port}/webhook")
    print("=" * 65)
    print("To expose this endpoint to Azure DevOps Cloud, run in a separate terminal:")
    print(f"  devtunnel host -p {port} --allow-anonymous")
    print(f"  or: ngrok http {port}")
    print("\nPress Ctrl+C to terminate.\n")
    server.start(background=False)


if __name__ == "__main__":
    main()
