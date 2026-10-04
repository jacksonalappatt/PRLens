"""Azure DevOps Webhook listener HTTP server."""

import http.server
import json
import threading
from typing import Any, Callable, Dict, Optional


class WebhookRequestHandler(http.server.BaseHTTPRequestHandler):
    on_pr_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    secret: str = ""

    def log_message(self, format, *args):
        print(f"[WebhookListener] {self.address_string()} - {format % args}")

    def do_GET(self):
        if self.path in ["/", "/health"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "prlens-webhook-listener"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if not self.path.startswith("/webhook"):
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Empty body")
            return

        body = self.rfile.read(content_length).decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return

        event_type = payload.get("eventType", "")
        print(f"[WebhookListener] Received ADO Service Hook event: {event_type}")

        resource = payload.get("resource", {})
        pr_id = resource.get("pullRequestId")

        if not pr_id:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status": "ignored", "reason": "No pullRequestId in resource"}')
            return

        pr_info = {
            "pr_id": pr_id,
            "title": resource.get("title", ""),
            "description": resource.get("description", ""),
            "createdBy": resource.get("createdBy", {}).get("displayName", "Unknown"),
            "repository": resource.get("repository", {}).get("name", ""),
            "repositoryId": resource.get("repository", {}).get("id", ""),
            "project": resource.get("repository", {}).get("project", {}).get("name", ""),
            "sourceBranch": resource.get("sourceRefName", ""),
            "targetBranch": resource.get("targetRefName", ""),
            "mergeStatus": resource.get("mergeStatus", "succeeded"),
            "isDraft": resource.get("isDraft", False),
            "url": resource.get("url", ""),
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "accepted", "prId": pr_id}).encode("utf-8"))

        if WebhookRequestHandler.on_pr_callback:
            threading.Thread(target=WebhookRequestHandler.on_pr_callback, args=(pr_info,), daemon=True).start()


class WebhookServer:
    def __init__(
        self, host: str = "127.0.0.1", port: int = 7890, secret: str = "", on_pr_callback: Optional[Callable] = None
    ):
        self.host = host
        self.port = port
        self.secret = secret
        self.on_pr_callback = on_pr_callback
        self.httpd: Optional[http.server.HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self, background: bool = True):
        WebhookRequestHandler.on_pr_callback = self.on_pr_callback
        WebhookRequestHandler.secret = self.secret
        self.httpd = http.server.HTTPServer((self.host, self.port), WebhookRequestHandler)
        print(f"[WebhookServer] Listening on http://{self.host}:{self.port}/webhook")

        if background:
            self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self._thread.start()
        else:
            try:
                self.httpd.serve_forever()
            except KeyboardInterrupt:
                self.stop()

    def stop(self):
        if self.httpd:
            print("[WebhookServer] Stopping webhook server...")
            self.httpd.shutdown()
            self.httpd.server_close()
