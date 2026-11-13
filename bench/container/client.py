#!/usr/bin/python3
"""Container-side az client. Contains no fixture data or Azure fallback."""

import json
import socket
import sys


def main(tool="az"):
    try:
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(120)
            connection.connect("/run/bench/az.sock")
            connection.sendall(json.dumps({"argv": sys.argv[1:], "tool": tool}).encode() + b"\n")
            response = json.loads(connection.makefile("rb").readline())
        sys.stdout.write(response["stdout"])
        sys.stderr.write(response["stderr"])
        return response["exit_code"]
    except (OSError, ValueError) as error:
        print(f"mock az unavailable: {error}", file=sys.stderr)
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
