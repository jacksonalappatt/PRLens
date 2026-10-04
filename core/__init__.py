"""Core module for azure-pr-agent."""

from .ado_client import AdoClient
from .approval_gate import ApprovalGate
from .job_runner import JobRunner
from .workspace_detector import resolve_workspace
from .worktree_manager import WorktreeManager

__all__ = [
    "AdoClient",
    "ApprovalGate",
    "JobRunner",
    "WorktreeManager",
    "resolve_workspace",
]
