"""Workspace detection, validation, and persistence."""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple


def inspect_git_remote(repo_path: Path) -> Dict[str, str]:
    """Inspects git remote URL to extract ADO org, project, and repository name."""
    info = {"organization": "", "project": "", "repository": repo_path.name}
    try:
        res = subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=str(repo_path), capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            url = res.stdout.strip()
            # Standard Azure DevOps: https://dev.azure.com/{org}/{project}/_git/{repo}
            m = re.search(r"dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+?)(?:\.git)?$", url)
            if m:
                info["organization"] = m.group(1)
                info["project"] = m.group(2)
                info["repository"] = m.group(3)
            else:
                # Legacy Visual Studio format: https://{org}.visualstudio.com/{project}/_git/{repo}
                m2 = re.search(r"([^/]+)\.visualstudio\.com/([^/]+)/_git/([^/]+?)(?:\.git)?$", url)
                if m2:
                    info["organization"] = m2.group(1)
                    info["project"] = m2.group(2)
                    info["repository"] = m2.group(3)
    except Exception:
        pass
    return info


def is_git_repo(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=str(path), capture_output=True, text=True, timeout=5
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:
        return False


def resolve_workspace(config_file: Path, cli_override: Optional[str] = None) -> Tuple[Path, Dict[str, str]]:
    """Prompt user for workspace, defaulting to previously saved workspace."""
    cfg = {}
    if config_file.exists():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    last_workspace = cfg.get("last_workspace") or ""

    if cli_override:
        candidate_path = Path(cli_override).resolve()
        if not is_git_repo(candidate_path):
            print(f"❌ Error: Specified workspace '{cli_override}' is not a valid git repository.", file=sys.stderr)
            sys.exit(1)
        cfg["last_workspace"] = str(candidate_path)
        config_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        ado_info = inspect_git_remote(candidate_path)
        return candidate_path, ado_info

    print("\n" + "=" * 65)
    print("               TARGET REPOSITORY WORKSPACE")
    print("=" * 65)
    if last_workspace:
        print(f"Previous workspace : {last_workspace}")
        print("Press Enter to use previous workspace, or enter a new path.")
    else:
        print("Enter the absolute or relative path to your Git repository workspace.")
    print("-" * 65)

    while True:
        try:
            if last_workspace:
                user_input = input(f"Enter workspace path [Default: {last_workspace}]: ").strip()
                chosen_str = user_input if user_input else last_workspace
            else:
                user_input = input("Enter workspace path: ").strip()
                if not user_input:
                    print("❌ Workspace path cannot be empty.")
                    continue
                chosen_str = user_input

            candidate_path = Path(chosen_str).resolve()

            if not candidate_path.exists():
                print(f"❌ Directory does not exist: {candidate_path}. Please try again.")
                continue

            if not is_git_repo(candidate_path):
                print(f"❌ '{candidate_path}' is not a Git repository. Please provide a valid Git root.")
                continue

            cfg["last_workspace"] = str(candidate_path)
            config_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            ado_info = inspect_git_remote(candidate_path)
            print(f"✅ Active Workspace: {candidate_path}")
            repo_desc = ado_info["repository"]
            if ado_info["organization"] and ado_info["project"]:
                repo_desc += f" ({ado_info['organization']}/{ado_info['project']})"
            print(f"   Detected Repo   : {repo_desc}\n")
            return candidate_path, ado_info

        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
