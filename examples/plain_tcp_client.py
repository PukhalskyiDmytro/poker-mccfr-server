from __future__ import annotations

import argparse
import socket

DEFAULT_SOLVE_COMMAND = (
    "SOLVE "
    "board=AhKdQsJc2d "
    "oop_range=AA,AKs,AQo "
    "ip_range=QQ,AK,AQs "
    "initial_pot=100 "
    "effective_stack=300 "
    "limit_type=no-limit "
    "iterations=2000"
)


def send_command(host: str, port: int, command: str, buffer_size: int = 2_000_000) -> str:
    """Send one plain-text command to the local poker server and return its response."""
    if not command.endswith("\n"):
        command += "\n"

    with socket.create_connection((host, port), timeout=30) as client:
        client.sendall(command.encode("utf-8"))
        chunks: list[bytes] = []
        while True:
            chunk = client.recv(buffer_size)
            if not chunk:
                break
            chunks.append(chunk)

    return b"".join(chunks).decode("utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description="Example client for the plain TCP Poker MCCFR server.")
    parser.add_argument("--host", default="127.0.0.1", help="Server host. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="Server port. Default: 8000")
    parser.add_argument(
        "--command",
        default=DEFAULT_SOLVE_COMMAND,
        help="Command to send. Examples: HEALTH, HELP, or SOLVE board=... oop_range=... ip_range=...",
    )
    args = parser.parse_args()

    response = send_command(args.host, args.port, args.command)
    print(response, end="")


if __name__ == "__main__":
    main()
