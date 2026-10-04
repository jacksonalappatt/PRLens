# PRLens 🔍

> **Autonomous Azure DevOps AI Pull Request Reviewer**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Repository](https://img.shields.io/badge/GitHub-jacksonalappatt%2FPRLens-181717?logo=github)](https://github.com/jacksonalappatt/PRLens)

**PRLens** is an autonomous, self-hosted background agent that monitors assigned pull requests in Azure DevOps, provisions isolated Git worktrees per PR branch, and executes thorough Five-Axis architectural and code quality reviews using local AI harnesses (**Antigravity IDE**, **Claude Code CLI**, or **Codex CLI**) with **zero direct LLM API keys or metered API costs**.

---

## 🌟 Highlights

- **Zero Direct LLM APIs**: Leverages your existing authenticated developer CLI sessions (`codex exec`, `antigravity-ide chat`, `claude -p`). Never consumes raw metered API keys or external billing quotas.
- **Interactive Startup Harness Picker**: Scans your system upon startup and lets you choose which AI harness to use.
- **Dynamic Workspace Memory**: Prompts for your repository workspace path and automatically remembers your previous workspace. Simply press **Enter** to reuse it.
- **Automatic ADO Remote Detection**: Detects your Azure DevOps Organization, Project, and Repository automatically from the target workspace's Git remote origin.
- **Strict Static Review (No Pipeline Duplication)**: Explicitly prohibited from running local CLI tests, builds, linting, or pre-commit hooks—all automated execution is preserved for the CI/CD pipeline.
- **Git Worktree Isolation**: Spawns isolated checkouts in `worktrees/pr-<id>` for safe multi-branch inspection without disturbing your active working tree.
- **Dual Trigger Dispatcher**: Receives immediate Azure DevOps Service Hook pushes (`/webhook`) and runs a resilient 60-second background poller as a fallback.
- **Human-in-the-Loop Approval Gate**: Generates structured Five-Axis Markdown review reports and requires explicit developer sign-off before posting comments or submitting reviewer votes to Azure DevOps.

---

## 📁 Repository Structure

```
PRLens/
├── server/
│   ├── azure-webhook-listener.cmd   # Windows batch launcher for standalone listener
│   ├── azure-webhook-listener       # Shell launcher for standalone listener
│   ├── azure_webhook_listener.py    # Standalone webhook runner script
│   ├── webhook_server.py            # HTTP server for Azure DevOps Service Hooks (port 7890)
│   └── poller.py                    # 60s background poller fallback (PAT authenticated)
├── jobs/
│   ├── registry.json                # Job tracking database & review index
│   └── <pr_id>/                     # Generated diffs, review reports, and execution logs
├── worktrees/                       # Isolated Git worktrees created per PR branch
├── instructions/
│   └── AGENTS.md                    # Five-Axis review guidelines and architectural directives
├── harnesses/
│   ├── base.py                      # BaseHarness interface & report markdown parser
│   ├── codex_harness.py             # Headless Codex CLI runner (`codex exec`)
│   ├── antigravity_harness.py       # Antigravity IDE agent runner (`antigravity-ide chat`)
│   ├── claude_harness.py            # Claude Code CLI runner (`claude -p`)
│   └── registry.py                  # Interactive startup harness selector
├── core/
│   ├── ado_client.py                # Azure DevOps REST API client
│   ├── workspace_detector.py        # Workspace prompter, git remote detector & persistence
│   ├── worktree_manager.py          # Git worktree lifecycle manager
│   ├── job_runner.py                # Orchestrator coordinating worktrees and harnesses
│   └── approval_gate.py             # User approval gate for ADO comment and vote submission
├── tests/
│   └── test_agent.py                # Automated unit tests
├── pyproject.toml                   # Project metadata and Ruff linter/formatter configuration
├── config.json                      # System configuration & last_workspace persistence
├── main.py                          # Unified CLI entry point & daemon
├── run.cmd                          # Windows batch quick launcher
├── run.ps1                          # PowerShell quick launcher
└── README.md                        # Documentation
```

---

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/jacksonalappatt/PRLens.git
cd PRLens
```

### 2. Prerequisites

- **Python 3.10+**
- **Git**
- An active **Azure DevOps Personal Access Token (PAT)** with *Code (Read & Write)* permissions.
- At least one local AI harness CLI installed:
  - **Codex CLI**: `npm i -g @openai/codex`
  - **Antigravity IDE**: [Antigravity IDE](https://antigravity.google)
  - **Claude Code CLI**: `npm i -g @anthropic-ai/claude-code`

### 3. Set Up Your Environment Variable

Set your Azure DevOps Personal Access Token (PAT):

```powershell
# Windows PowerShell
$env:AZURE_DEVOPS_PAT = "your-personal-access-token"
```

```bash
# macOS / Linux
export AZURE_DEVOPS_PAT="your-personal-access-token"
```

*(PRLens also recognizes `ADO_PAT` or `AZURE_DEVOPS_EXT_PAT`).*

### 4. Check Available Harnesses

Verify your local harness detection:

```powershell
python main.py --check-harnesses
```

### 5. Start PRLens Daemon

```powershell
python main.py run
# or on Windows:
.\run.cmd
```

On startup, PRLens will:
1. Prompt for your target repository workspace (press **Enter** to accept your previously used workspace).
2. Prompt for your AI harness of choice (**Codex**, **Antigravity**, or **Claude**).
3. Start background listeners and begin monitoring assigned PRs.

```
=================================================================
               TARGET REPOSITORY WORKSPACE
=================================================================
Previous workspace : C:\projects\my-repo
Press Enter to use previous workspace, or enter a new path.
-----------------------------------------------------------------
Enter workspace path [Default: C:\projects\my-repo]: [PRESS ENTER]
✅ Active Workspace: C:\projects\my-repo
   Detected Repo   : my-repo (my-org/my-project)

=================================================================
           AI HARNESS SELECTION (Zero Direct APIs)
=================================================================
Available AI harnesses on this machine:

  [1] Codex CLI (codex-cli)               ✅ Ready (codex-cli 0.144.4) [Default]
  [2] Antigravity IDE / AGY               ✅ Ready (Antigravity IDE 1.107.0)
  [3] Claude Code CLI                     ❌ Not Available (npm i -g @anthropic-ai/claude-code)
-----------------------------------------------------------------
Select AI Harness to use [1-3] (press Enter for [1]): [PRESS ENTER]
```

---

## 🛠️ CLI Commands

| Command | Description |
|---|---|
| `python main.py run` | Start PRLens daemon (Webhook listener + periodic poller). |
| `python main.py review <pr_id>` | Review a specific pull request immediately on-demand. |
| `python main.py approve <pr_id>` | Open interactive gate to inspect findings and submit comments/vote to ADO. |
| `python main.py list` | Display status and recommendations for all tracked review jobs. |
| `python main.py --reasoning <level>` | Override reasoning effort (`high`, `medium`, `low`) for this run (alias: `--tier`). |
| `python main.py --model <name>` | Override with an explicit model identifier (e.g. `gpt-6`, `gpt-6-luna`, `3.8`, `claude-3-7-sonnet`). |
| `python main.py --check-harnesses` | Display diagnostic status of locally installed AI CLIs. |

---

## 🛡️ User Approval Gate

PRLens enforces an **approval-first** model. When a review is generated, you can inspect the findings and choose how to submit feedback:

```powershell
python main.py approve 1001
```

```
======================================================================
📋 PULL REQUEST REVIEW GATE: PR #1001
   Title: feat: add authentication token refresh
   Author: Alice Developer
   Recommended Vote: 5
   Proposed Inline Comments: 2
======================================================================

Proposed Inline Comments:
  1. [src/auth/token.service.ts:42] Missing null safety check on expired refresh token.
  2. [src/auth/guard.ts:88] Subscription stream not cleaned up on component destruction.

Options:
  [A] Approve PR (Vote: +10)
  [S] Approve with Suggestions (Vote: +5, post inline comments)
  [W] Waiting for Author (Vote: -5, post inline comments)
  [R] Reject (Vote: -10, post inline comments)
  [V] View Full Review Report
  [X] Cancel / Do Nothing
```

---

## 🎯 Model & Reasoning Effort Configuration

PRLens cleanly decouples **Model Selection** from **Reasoning Effort** in `config.json` without asking on every startup:

- **Reasoning Effort (`high`, `medium`, `low`)**:
  - **`high`**:
    - **Codex CLI**: `gpt-6` with reasoning effort `high`
    - **Antigravity IDE**: `3.8` with reasoning effort `high`
    - **Claude Code CLI**: `claude-3-7-sonnet` with reasoning effort `high`
  - **`medium`**:
    - **Codex CLI**: `gpt-6-luna` with reasoning effort `medium`
    - **Antigravity IDE**: `3.8` with reasoning effort `medium`
    - **Claude Code CLI**: `claude-3-5-sonnet` with reasoning effort `medium`
  - **`low`**:
    - **Codex CLI**: `gpt-6-luna` with reasoning effort `low`
    - **Antigravity IDE**: `3.8` with reasoning effort `low`
    - **Claude Code CLI**: `claude-3-5-haiku` with reasoning effort `low`

- **Independent Model Toggling**:
  In `config.json`, the model and reasoning are kept separate. You can toggle the model string for any harness (e.g. set `"models": { "codex": "gpt-6-luna" }`) without having to update the `"reasoning"` level, and vice-versa!

Configure in `config.json` or override on demand via CLI:

```powershell
python main.py run --reasoning medium
# or override with an explicit model
python main.py run --reasoning high --model gpt-6-luna
```

---

## 🧹 Code Quality with Ruff

PRLens uses [Ruff](https://github.com/astral-sh/ruff) for lightning-fast linting and code formatting:

```powershell
# Run linter
ruff check .

# Automatically fix lint issues
ruff check --fix .

# Format code
ruff format .
```

To run the automated test suite:

```powershell
python -m unittest tests/test_agent.py
```

---

## 📄 Configuration (`config.json`)

All configuration is environment-driven and workspace-aware:

```json
{
  "last_workspace": "",
  "reasoning": "high",
  "models": {
    "codex": null,
    "antigravity": null,
    "claude": null
  },
  "default_models": {
    "codex": {
      "high": "gpt-6",
      "medium": "gpt-6-luna",
      "low": "gpt-6-luna"
    },
    "antigravity": {
      "high": "3.8",
      "medium": "3.8",
      "low": "3.8"
    },
    "claude": {
      "high": "claude-3-7-sonnet",
      "medium": "claude-3-5-sonnet",
      "low": "claude-3-5-haiku"
    }
  },
  "ado": {
    "organization": "",
    "project": "",
    "pat_env_var": "AZURE_DEVOPS_PAT"
  },
  "server": {
    "host": "127.0.0.1",
    "port": 7890,
    "secret": ""
  },
  "polling": {
    "enabled": true,
    "interval_seconds": 60
  },
  "harness": {
    "default": null,
    "timeout_seconds": 900
  },
  "approval_mode": "manual"
}
```

---

## 🤝 Contributing & License

Contributions are welcome! Please open an issue or pull request.
Distributed under the [MIT License](LICENSE).
