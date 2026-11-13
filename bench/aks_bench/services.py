"""Host-owned Unix-socket services: mock API and allowlisted HTTPS CONNECT proxy."""

import ipaddress
import json
from pathlib import Path
import select
import socket
import socketserver
import threading
import time


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class MockHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(30)
        try:
            data = self.rfile.readline(65537)
            if len(data) > 65536:
                raise ValueError("request too large")
            request = json.loads(data)
            args = request["argv"]
            if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                raise ValueError("argv must be strings")
            tool = request.get("tool", "az")
            if tool not in ("az", "kubectl", "curl"):
                raise ValueError("unsupported tool")
            response = self.server.simulator.call(args, tool=tool)
        except (ValueError, KeyError) as error:
            response = {"stdout": "", "stderr": f"invalid mock request: {error}\n", "exit_code": 2}
        self.wfile.write(json.dumps(response).encode() + b"\n")


def relay(left, right):
    counts = [0, 0]
    while True:
        readable, _, _ = select.select([left, right], [], [], 180)
        if not readable:
            break
        for source in readable:
            data = source.recv(65536)
            if not data:
                return counts
            target = right if source is left else left
            target.sendall(data)
            counts[0 if source is left else 1] += len(data)
    return counts


def allowed_authority(authority, allowed_hosts):
    host, sep, port = authority.rpartition(":")
    return bool(sep and port == "443" and host.lower() in allowed_hosts
                and host.lower() not in {"management.azure.com", "management.core.windows.net", "169.254.169.254"})


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self):
        started = time.monotonic()
        event = {"started_at": time.time(), "authority": None, "allowed": False,
                 "bytes_up": 0, "bytes_down": 0}
        try:
            self.request.settimeout(180)
            header = bytearray()
            while not header.endswith(b"\r\n\r\n"):
                chunk = self.request.recv(1)
                if not chunk or len(header) > 16384:
                    raise ValueError("invalid proxy request")
                header.extend(chunk)
            method, authority, _ = header.decode("ascii").split("\r\n", 1)[0].split()
            event["authority"] = authority
            if method != "CONNECT" or not allowed_authority(authority, self.server.allowed_hosts):
                self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            host = authority.rsplit(":", 1)[0]
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            # Pin the validated address; don't resolve again between validation and connect.
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise ValueError("provider must resolve to public addresses")
            family, socktype, proto, _, address = addresses[0]
            with socket.socket(family, socktype, proto) as upstream:
                upstream.settimeout(180)
                upstream.connect(address)
                event["allowed"] = True
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                event["bytes_up"], event["bytes_down"] = relay(self.request, upstream)
        except (OSError, ValueError) as error:
            event["error"] = str(error)
            try:
                self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
        finally:
            event["duration_s"] = time.monotonic() - started
            with self.server.log_lock:
                with self.server.log_path.open("a") as stream:
                    stream.write(json.dumps(event) + "\n")


class Services:
    def __init__(self, directory, simulator, allowed_hosts, proxy_log):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.mock = UnixServer(str(self.directory / "az.sock"), MockHandler)
        self.mock.simulator = simulator
        self.proxy = UnixServer(str(self.directory / "proxy.sock"), ProxyHandler)
        self.proxy.allowed_hosts = set(allowed_hosts)
        self.proxy.log_path = Path(proxy_log)
        self.proxy.log_lock = threading.Lock()
        for path in self.directory.iterdir():
            path.chmod(0o600)

    def __enter__(self):
        for server in (self.mock, self.proxy):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *args):
        for server in (self.mock, self.proxy):
            server.shutdown()
            server.server_close()
