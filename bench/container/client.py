#!/usr/bin/python3
"""Container-side az client. Contains no fixture data or Azure fallback."""

import json
import socket
import sys
from pathlib import Path


def write_kubeconfig(content, argv):
    destination = str(Path.home() / ".kube" / "config")
    for index, arg in enumerate(argv):
        if arg == "--file":
            destination = argv[index + 1]
        elif arg.startswith("--file="):
            destination = arg.split("=", 1)[1]
    path = Path(destination).expanduser().resolve()
    if not any(path.is_relative_to(root.resolve()) for root in (Path("/work"), Path.home())):
        raise ValueError("mock kubeconfig may only be written under /work or the container home")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o600)


def main(tool="az"):
    try:
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(120)
            connection.connect("/run/bench/az.sock")
            connection.sendall(json.dumps({"argv": sys.argv[1:], "tool": tool}).encode() + b"\n")
            response = json.loads(connection.makefile("rb").readline())
        sys.stdout.write(response["stdout"])
        sys.stderr.write(response["stderr"])
        if response["exit_code"] == 0 and "kubeconfig" in response:
            write_kubeconfig(response["kubeconfig"], sys.argv[1:])
        return response["exit_code"]
    except (OSError, ValueError) as error:
        print(f"mock az unavailable: {error}", file=sys.stderr)
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
