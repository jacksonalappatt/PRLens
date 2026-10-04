"""Harness registry and interactive selector."""

import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from typing import Dict, Optional

from .antigravity_harness import AntigravityHarness
from .base import BaseHarness
from .claude_harness import ClaudeHarness
from .codex_harness import CodexHarness

HARNESS_REGISTRY: Dict[str, BaseHarness] = {
    "codex": CodexHarness(),
    "antigravity": AntigravityHarness(),
    "claude": ClaudeHarness(),
}


def get_harness(name: str) -> Optional[BaseHarness]:
    return HARNESS_REGISTRY.get(name.lower().strip())


def prompt_harness_selection(default_choice: Optional[str] = None) -> BaseHarness:
    """Interactively prompts the user in terminal to choose which AI harness to use."""
    print("\n" + "=" * 65)
    print("           AI HARNESS SELECTION (Zero Direct APIs)")
    print("=" * 65)
    print("Available AI harnesses on this machine:\n")

    options = list(HARNESS_REGISTRY.items())
    default_idx = 1

    for idx, (key, harness) in enumerate(options, 1):
        avail, status = harness.check_availability()
        status_tag = f"✅ Ready ({status})" if avail else f"❌ Not Available ({status})"
        is_default = (key == default_choice) or (default_choice is None and idx == 1)
        default_tag = " [Default]" if is_default else ""
        if is_default:
            default_idx = idx
        print(f"  [{idx}] {harness.display_name:<35} {status_tag}{default_tag}")

    print("-" * 65)

    while True:
        try:
            prompt_str = f"Select AI Harness to use [1-{len(options)}] (press Enter for [{default_idx}]): "
            user_input = input(prompt_str).strip()
            if not user_input:
                chosen_idx = default_idx
            else:
                chosen_idx = int(user_input)

            if 1 <= chosen_idx <= len(options):
                chosen_key, chosen_harness = options[chosen_idx - 1]
                avail, status = chosen_harness.check_availability()
                if not avail:
                    print(f"⚠️  Warning: {chosen_harness.display_name} is marked as not available ({status}).")
                    proceed = input("Continue anyway? (y/N): ").strip().lower()
                    if proceed != "y":
                        continue
                print(f"\n🚀 Activated AI Harness: {chosen_harness.display_name}\n")
                return chosen_harness
            else:
                print(f"Please enter a number between 1 and {len(options)}.")
        except (ValueError, IndexError):
            print("Invalid input. Please enter a number.")
        except (KeyboardInterrupt, EOFError):
            print("\nSelection aborted.")
            sys.exit(0)
