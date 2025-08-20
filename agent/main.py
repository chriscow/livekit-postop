#!/usr/bin/env python3
"""
PostOp AI Main Entry Point

Simplified startup for the LiveKit agent with an embedded health endpoint.

Usage:
    python main.py discharge console   # Discharge workflow in console mode
    python main.py discharge dev       # Discharge workflow in production/dev mode
    python main.py followup console    # Followup workflow in console mode
    python main.py followup dev        # Followup workflow in production/dev mode
"""
import sys
import os
import json
import time
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from dotenv import load_dotenv


logger = logging.getLogger("postop-main")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


class SimpleHealthHandler(BaseHTTPRequestHandler):
    """Minimal handler for Fly.io health checks."""

    def do_GET(self):  # noqa: N802 (http.server API)
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            payload = {
                "status": "healthy",
                "service": "postop-ai-agent",
                "timestamp": int(time.time()),
            }
            self.wfile.write(json.dumps(payload).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A003 (shadow builtins)
        # Quiet default server logging; route to our logger at DEBUG
        try:
            logger.debug(format % args)
        except Exception:
            pass


class BackgroundHTTPServer:
    """Run a simple HTTPServer in a background thread."""

    def __init__(self, port: int = 8081):
        self._port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        if self._running:
            return

        def _run():
            try:
                self._server = HTTPServer(("0.0.0.0", self._port), SimpleHealthHandler)
                logger.info(f"Health endpoint listening on 0.0.0.0:{self._port} at /health")
                self._running = True
                self._server.serve_forever()
            except Exception as exc:
                logger.error(f"Health server failed to start: {exc}")
                self._running = False

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        time.sleep(0.05)

    def stop(self):
        try:
            if self._server:
                logger.info("Stopping health server")
                self._server.shutdown()
        finally:
            self._running = False
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1.0)


health_server = BackgroundHTTPServer(port=int(os.getenv("HEALTH_PORT", "8081")))


def _run_workflow(workflow: str, mode: str):
    """Invoke the selected workflow's main() while preserving console mode behavior."""
    original_argv = sys.argv.copy()

    try:
        # Ensure LiveKit CLI sees only the mode token (console/dev)
        sys.argv = [sys.argv[0], ("console" if mode == "console" else "dev")]

        if workflow == "discharge":
            from discharge.agents import main as discharge_main
            discharge_main()
        elif workflow == "followup":
            from followup.agents import main as followup_main
            followup_main()
        else:
            print(f"Unknown workflow: {workflow}")
            print("Available workflows: discharge, followup")
            sys.exit(1)
    finally:
        sys.argv = original_argv


def main():
    """Main entry point router with embedded health endpoint for Fly.io."""
    load_dotenv()

    # Arguments: <workflow> <mode>
    if len(sys.argv) < 3:
        print("Usage: python main.py <workflow> <mode>")
        print("Workflows: discharge, followup")
        print("Modes: console, dev")
        sys.exit(1)

    workflow = sys.argv[1].lower()
    mode = sys.argv[2].lower()

    if mode not in ["console", "dev"]:
        print(f"Unknown mode: {mode}")
        print("Available modes: console, dev")
        sys.exit(1)

    # Start health endpoint for non-console runs (Fly.io healthcheck on /health)
    started_health = False
    if mode != "console":
        try:
            health_server.start()
            started_health = True
        except Exception as exc:
            logger.error(f"Failed to start health endpoint: {exc}")

    try:
        _run_workflow(workflow, mode)
    finally:
        if started_health:
            health_server.stop()


if __name__ == "__main__":
    main()