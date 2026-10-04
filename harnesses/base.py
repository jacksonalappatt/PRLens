"""Base classes and utilities for local AI review harnesses."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class HarnessResult:
    success: bool
    report_markdown: str = ""
    recommended_vote: int = 0
    comments: List[Dict[str, Any]] = field(default_factory=list)
    raw_log: str = ""
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    model_name: Optional[str] = None
    model_tier: str = "high"


def parse_review_report(report_text: str) -> Tuple[int, List[Dict[str, Any]]]:
    """Extracts recommended ADO vote and proposed inline comments from a review report markdown."""
    vote = 0
    comments = []

    # 1. Parse Vote
    vote_patterns = [
        r"(?:Proposed Reviewer Vote|Recommended Vote|Vote):\s*[`\*]*([+\-]?\d{1,2})",
        r"(?:Proposed Reviewer Vote|Recommended Vote|Vote):[^\n]*\(([+\-]?\d{1,2})\)",
        r"(?:Approved \((\+?10)\)|Approved with Suggestions \((\+?5)\)|Waiting for Author \((\-5)\)|Rejected \((\-10)\))",
    ]
    for pattern in vote_patterns:
        match = re.search(pattern, report_text, re.IGNORECASE)
        if match:
            for g in match.groups():
                if g:
                    try:
                        vote = int(g.replace("+", ""))
                        break
                    except ValueError:
                        pass
            if vote != 0:
                break

    if vote == 0:
        if "### 🔴 Critical" in report_text and "None" not in report_text.split("### 🔴 Critical")[1][:50]:
            vote = -5
        elif "### 🟡 Major" in report_text and "None" not in report_text.split("### 🟡 Major")[1][:50]:
            vote = 5
        else:
            vote = 10

    # 2. Parse inline comments / findings: `[path/to/file.ts#L45]` or `[path/to/file.ts:45]`
    finding_pattern = re.compile(r"[-*]\s+\*?\*?`\[?([^\]#:\n]+?)(?:#L|:)(\d+)(?:-L?\d+)?\]?`\*?\*?:\s*(.+)")
    for line in report_text.splitlines():
        m = finding_pattern.match(line.strip())
        if m:
            file_path = m.group(1).strip("`[] ")
            line_num = int(m.group(2))
            comment_text = m.group(3).strip()
            comments.append(
                {
                    "filePath": file_path,
                    "line": line_num,
                    "comment": comment_text,
                }
            )

    return vote, comments


class BaseHarness(ABC):
    name: str = "base"
    display_name: str = "Base Harness"
    DEFAULT_TIER_MODELS: Dict[str, str] = {
        "high": "",
        "medium": "",
        "low": "",
    }

    def resolve_model(self, tier: str = "high", custom_models: Optional[Dict[str, str]] = None) -> Optional[str]:
        """Resolves the concrete model identifier for a given tier (high, medium, low)."""
        tier_key = tier.lower().strip()
        if custom_models and tier_key in custom_models:
            return custom_models[tier_key]
        return self.DEFAULT_TIER_MODELS.get(tier_key)

    @abstractmethod
    def check_availability(self) -> Tuple[bool, str]:
        """Checks if the CLI harness is installed and available. Returns (is_available, version_or_reason)."""
        pass

    @abstractmethod
    def run_review(
        self,
        worktree_path: Path,
        pr_info: dict,
        diff_text: str,
        instructions_path: Path,
        output_file: Path,
        model_tier: str = "high",
        model_name: Optional[str] = None,
    ) -> HarnessResult:
        """Executes the review within the worktree and writes the report to output_file."""
        pass

    def build_prompt(
        self,
        pr_info: dict,
        instructions_path: Path,
        output_file: Path,
        model_tier: str = "high",
        model_name: Optional[str] = None,
    ) -> str:
        """Constructs the prompt given to the AI harness."""
        instructions_text = instructions_path.read_text(encoding="utf-8", errors="replace")
        pr_id = pr_info.get("pr_id")
        title = pr_info.get("title")
        description = pr_info.get("description", "")
        author = pr_info.get("createdBy", "Author")
        source = pr_info.get("sourceBranch", "")
        target = pr_info.get("targetBranch", "")

        model_note = f"\nActive Model: {model_name} (Tier: {model_tier.upper()})" if model_name else ""

        return f"""You are reviewing Azure DevOps Pull Request #{pr_id}: "{title}".
Author: {author}
Source Branch: {source}
Target Branch: {target}{model_note}

PR Description:
{description}

A git diff is available in the current working directory at `pr_diff.patch`.
Also inspect all actual source files in this worktree as needed.

================================================================================
STRICT PROHIBITION: DO NOT RUN CLI TESTS, LINT, BUILD, OR PRECOMMIT HOOKS
The CI/CD pipeline enforces all automated tests, builds, and linting.
DO NOT execute test runners (jest, karma, npm test, dotnet test), build commands
(ng build, npm run build), or lint tools (eslint, prettier).
Perform 100% static architectural, logic, and code standards analysis only.
================================================================================

INSTRUCTIONS AND STANDARDS:
Follow all guidelines and review criteria below strictly:
{instructions_text}

TASK:
1. Carefully analyze the changes in `pr_diff.patch` and the checked-out codebase statically.
2. Adhere to the Five-Axis Review Framework and project coding guidelines.
3. Write your complete, detailed Markdown review report to the following path:
`{output_file.resolve()}`
Ensure the report includes:
- System & Architecture Impact Summary
- Five-Axis Quality Evaluation Matrix
- Findings & Named Structural Remedies (Critical, Major, Minor, Praise)
- Proposed ADO Actions (Recommended Vote: +10, +5, -5, or -10, plus specific inline comments in format `[file#Lline]: comment`)
"""
