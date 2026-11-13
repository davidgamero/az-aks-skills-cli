#!/usr/bin/python3
"""Loopback-to-Unix proxy bridge and Copilot launcher in a networkless container."""

import json
import os
from pathlib import Path
import select
import socket
import socketserver
import subprocess
import shutil
import sys
import threading
import time


class Bridge(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_UNIX) as remote:
            remote.connect("/run/bench/proxy.sock")
            streams = [self.request, remote]
            while True:
                readable, _, _ = select.select(streams, [], [], 180)
                if not readable:
                    return
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    (remote if source is self.request else self.request).sendall(data)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def isolation_check():
    direct_blocked = False
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=1):
            pass
    except OSError:
        direct_blocked = True
    with socket.socket(socket.AF_UNIX) as proxy:
        proxy.connect("/run/bench/proxy.sock")
        proxy.sendall(b"CONNECT management.azure.com:443 HTTP/1.1\r\n\r\n")
        arm_blocked = b"403" in proxy.recv(1024)
    checks = {
        "external_network_blocked": direct_blocked,
        "arm_proxy_blocked": arm_blocked,
        "azure_credentials_absent": not Path("/home/agent/.azure").exists(),
        "host_home_absent": not Path("/home/david").exists(),
        "real_azure_cli_absent": not Path("/opt/az").exists(),
        "fixture_files_absent": not Path("/opt/client/commands.json").exists(),
        "mock_kubectl_selected": shutil.which("kubectl") == "/opt/client/kubectl",
        "logged_docs_client_selected": shutil.which("curl") == "/opt/client/curl",
    }
    Path("/results/isolation.json").write_text(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise RuntimeError(f"isolation check failed: {checks}")


def main():
    os.chdir("/work")
    Path("/home/agent").mkdir(exist_ok=True)
    isolation_check()
    with Server(("127.0.0.1", 18080), Bridge) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        if sys.argv[1:] == ["--check"]:
            return 0
        if sys.argv[1:2] == ["--replay"]:
            for args in json.loads(sys.argv[2]):
                tool, arguments = (args["tool"], args["argv"]) if isinstance(args, dict) else ("az", args)
                if tool not in ("az", "kubectl", "curl"):
                    raise ValueError("unsupported replay tool")
                result = subprocess.run([tool, *arguments], input=args.get("stdin") if isinstance(args, dict) else None, text=True)
                expected_exit = args.get("expect_exit", 0) if isinstance(args, dict) else 0
                if result.returncode != expected_exit:
                    return result.returncode or 1
            return 0
        env = os.environ.copy()
        env.update(HTTPS_PROXY="http://127.0.0.1:18080", HTTP_PROXY="http://127.0.0.1:18080",
                   NO_PROXY="127.0.0.1,localhost", COPILOT_HOME="/home/agent/.copilot",
                   COPILOT_AUTO_UPDATE="false", COPILOT_OTEL_FILE_EXPORTER_PATH="/results/otel.jsonl",
                   COPILOT_OTEL_EXPORTER_TYPE="file", OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT="false")
        command = ["/opt/copilot", "--model", sys.argv[1], "--prompt", sys.argv[2],
                   "--allow-all-tools", "--allow-all-paths", "--no-ask-user",
                   "--no-auto-update", "--no-custom-instructions", "--disable-builtin-mcps",
                   "--no-bash-env", "--no-remote", "--no-remote-export",
                   "--output-format", "json", "--usage-output-file", "/results/usage.json",
                   "--log-dir", "/results/logs",
                   "--secret-env-vars=COPILOT_GITHUB_TOKEN,COPILOT_PROVIDER_API_KEY,COPILOT_PROVIDER_BEARER_TOKEN"]
        if env.get("AKS_BENCH_DOCS_MODE") == "live":
            command.append("--allow-url=https://learn.microsoft.com")
            command.append("--allow-url=https://kubernetes.io")
        else:
            command.append("--excluded-tools=web_fetch")
        Path("/results/agent-start.json").write_text(json.dumps({"time": time.time()}))
        return subprocess.call(command, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
