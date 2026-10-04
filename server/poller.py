"""Periodic background poller for Azure DevOps assigned PRs."""

import sys
import threading
import time
from typing import Optional

from core.ado_client import AdoClient
from core.job_runner import JobRunner


class PrPoller:
    def __init__(
        self, ado_client: AdoClient, job_runner: JobRunner, repo_id: Optional[str] = None, interval_seconds: int = 60
    ):
        self.ado_client = ado_client
        self.job_runner = job_runner
        self.repo_id = repo_id
        self.interval_seconds = interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def poll_once(self):
        """Executes a single polling check for newly assigned unreviewed PRs."""
        try:
            repo_filter = f" for repository '{self.repo_id}'" if self.repo_id else ""
            print(
                f"[Poller] Checking for unreviewed assigned PRs in {self.ado_client.org}/{self.ado_client.project}{repo_filter}..."
            )
            unreviewed = self.ado_client.get_assigned_unreviewed_prs(repo_id=self.repo_id)
            print(f"[Poller] Found {len(unreviewed)} active unreviewed PRs assigned to you or your teams.")

            for pr in unreviewed:
                pr_id = pr["pr_id"]
                if self.job_runner.is_pr_processed(pr_id):
                    continue
                print(f"[Poller] New unreviewed PR detected: #{pr_id} - {pr.get('title')}")
                self.job_runner.process_pr(pr)
        except Exception as e:
            print(f"[Poller] Error during PR poll cycle: {e}", file=sys.stderr)

    def _loop(self):
        while self._running:
            self.poll_once()
            for _ in range(self.interval_seconds):
                if not self._running:
                    break
                time.sleep(1)

    def start(self, background: bool = True):
        self._running = True
        print(f"[Poller] Starting PR polling loop (interval: {self.interval_seconds}s)...")
        if background:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        else:
            try:
                self._loop()
            except KeyboardInterrupt:
                self.stop()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        print("[Poller] Polling stopped.")
