from __future__ import annotations

import argparse
import shlex
import socket
import threading
from typing import Mapping

from .cards import parse_cards
from .game import ActionSpec, GameConfig, LimitType
from .mccfr import MCCFRSolver, SolveResult

DEFAULT_FIRST_ACTIONS = (
    ActionSpec("check", "check"),
    ActionSpec("bet_25", "bet", 0.25),
    ActionSpec("bet_100", "bet", 1.0),
)
DEFAULT_RESPONSE_ACTIONS = (
    ActionSpec("fold", "fold"),
    ActionSpec("call", "call"),
    ActionSpec("raise_50", "raise", 0.5),
    ActionSpec("raise_100", "raise", 1.0),
)

HELP_TEXT = """OK
Poker MCCFR local TCP protocol

Commands:
  HEALTH
  HELP
  SOLVE board=<cards> oop_range=<range> ip_range=<range> [initial_pot=<float>] [effective_stack=<float>] [limit_type=no-limit|pot-limit] [iterations=<int>] [seed=<int|none>]

Optional action abstractions:
  first_actions=check:check,bet_25:bet:0.25,bet_100:bet:1.0
  response_actions=fold:fold,call:call,raise_50:raise:0.5,raise_100:raise:1.0

Example:
  SOLVE board=AhKdQsJc2d oop_range=AA,AKs,AQo ip_range=QQ,AK,AQs initial_pot=100 effective_stack=300 limit_type=no-limit iterations=2000
END
"""


class ProtocolError(ValueError):
    pass


def parse_command(line: str) -> tuple[str, dict[str, str]]:
    """Parse a one-line plain-text command.

    Format:
        COMMAND key=value key=value

    This is intentionally not HTTP and not JSON. It is a small local protocol
    for sending commands over a raw TCP socket.
    """
    try:
        parts = shlex.split(line.strip())
    except ValueError as exc:
        raise ProtocolError(f"cannot parse command: {exc}") from exc

    if not parts:
        raise ProtocolError("empty command")

    command = parts[0].upper()
    params: dict[str, str] = {}
    for token in parts[1:]:
        if "=" not in token:
            raise ProtocolError(f"expected key=value token, got {token!r}")
        key, value = token.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key:
            raise ProtocolError("empty parameter name")
        params[key] = value
    return command, params


def _positive_float(params: Mapping[str, str], key: str, default: float) -> float:
    raw = params.get(key, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ProtocolError(f"{key} must be numeric") from exc
    if value <= 0:
        raise ProtocolError(f"{key} must be positive")
    return value


def _positive_int(params: Mapping[str, str], key: str, default: int) -> int:
    raw = params.get(key, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ProtocolError(f"{key} must be an integer") from exc
    if value <= 0:
        raise ProtocolError(f"{key} must be positive")
    return value


def action_from_text(text: str) -> ActionSpec:
    """Parse one action token: code:kind or code:kind:fraction."""
    parts = text.split(":")
    if len(parts) not in {2, 3}:
        raise ProtocolError(f"invalid action {text!r}; expected code:kind or code:kind:fraction")

    code, kind = parts[0].strip(), parts[1].strip()
    if not code:
        raise ProtocolError("action code cannot be empty")
    if kind not in {"check", "bet", "fold", "call", "raise"}:
        raise ProtocolError("action kind must be one of check, bet, fold, call, raise")

    fraction: float | None = None
    if len(parts) == 3:
        try:
            fraction = float(parts[2])
        except ValueError as exc:
            raise ProtocolError(f"action fraction must be numeric in {text!r}") from exc
        if fraction < 0:
            raise ProtocolError("action fraction cannot be negative")

    return ActionSpec(code=code, kind=kind, fraction=fraction)


def actions_from_text(text: str | None, default: tuple[ActionSpec, ...]) -> tuple[ActionSpec, ...]:
    if text is None or text == "":
        return default
    actions = tuple(action_from_text(item.strip()) for item in text.split(",") if item.strip())
    if not actions:
        raise ProtocolError("actions list cannot be empty")
    return actions


def build_config(params: Mapping[str, str]) -> GameConfig:
    raw_limit = params.get("limit_type", LimitType.NO_LIMIT.value)
    try:
        limit_type = LimitType(raw_limit)
    except ValueError as exc:
        raise ProtocolError("limit_type must be no-limit or pot-limit") from exc

    return GameConfig(
        initial_pot=_positive_float(params, "initial_pot", 100.0),
        effective_stack=_positive_float(params, "effective_stack", 300.0),
        limit_type=limit_type,
        first_actions=actions_from_text(params.get("first_actions"), DEFAULT_FIRST_ACTIONS),
        response_actions=actions_from_text(params.get("response_actions"), DEFAULT_RESPONSE_ACTIONS),
        max_raises_per_round=_positive_int(params, "max_raises_per_round", 2),
    )


def solve_params(params: Mapping[str, str]) -> SolveResult:
    board = params.get("board")
    oop_range = params.get("oop_range")
    ip_range = params.get("ip_range")

    if not board:
        raise ProtocolError("missing required parameter board")
    if not oop_range:
        raise ProtocolError("missing required parameter oop_range")
    if not ip_range:
        raise ProtocolError("missing required parameter ip_range")

    iterations = _positive_int(params, "iterations", 1000)
    if iterations > 200_000:
        raise ProtocolError("iterations cannot exceed 200000")

    raw_seed = params.get("seed", "7")
    if raw_seed.lower() in {"none", "null", "random"}:
        seed: int | None = None
    else:
        try:
            seed = int(raw_seed)
        except ValueError as exc:
            raise ProtocolError("seed must be an integer or none") from exc

    solver = MCCFRSolver(build_config(params), parse_cards(board), oop_range, ip_range, seed)
    return solver.train(iterations)


def format_result(result: SolveResult) -> str:
    lines = [
        "OK",
        f"iterations={result.iterations}",
        f"ev_oop={result.ev_oop:.10f}",
        f"ev_ip={result.ev_ip:.10f}",
        f"exploitability={result.exploitability:.10f}",
        f"infosets={result.infosets}",
        "strategies:",
    ]

    for infoset_key, probabilities in result.strategies.items():
        action_text = " ".join(f"{action}={probability:.10f}" for action, probability in probabilities.items())
        lines.append(f"{infoset_key} {action_text}")

    lines.append("END")
    return "\n".join(lines) + "\n"


def handle_command(line: str) -> str:
    try:
        command, params = parse_command(line)
        if command == "HEALTH":
            if params:
                raise ProtocolError("HEALTH does not accept parameters")
            return "OK status=ok\n"
        if command == "HELP":
            return HELP_TEXT
        if command == "SOLVE":
            return format_result(solve_params(params))
        raise ProtocolError(f"unknown command {command!r}; use HELP")
    except ProtocolError as exc:
        return f"ERROR {exc}\n"
    except Exception as exc:  # pragma: no cover - defensive server boundary
        return f"ERROR internal error: {exc}\n"


class PokerSocketServer:
    """Small local TCP server for the plain-text poker protocol."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8000, backlog: int = 16):
        self.host = host
        self.port = port
        self.backlog = backlog
        self._stop_event = threading.Event()
        self._socket: socket.socket | None = None

    @property
    def address(self) -> tuple[str, int]:
        if self._socket is None:
            return self.host, self.port
        host, port = self._socket.getsockname()[:2]
        return str(host), int(port)

    def serve_forever(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.host, self.port))
            server_socket.listen(self.backlog)
            server_socket.settimeout(0.25)
            self._socket = server_socket
            print(f"Poker MCCFR TCP server listening on {self.address[0]}:{self.address[1]}", flush=True)

            while not self._stop_event.is_set():
                try:
                    client_socket, _client_address = server_socket.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._handle_client, args=(client_socket,), daemon=True).start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass

    def _handle_client(self, client_socket: socket.socket) -> None:
        with client_socket:
            try:
                request = self._read_line(client_socket)
                response = handle_command(request.decode("utf-8", errors="replace"))
                client_socket.sendall(response.encode("utf-8"))
            except OSError:
                return

    @staticmethod
    def _read_line(client_socket: socket.socket) -> bytes:
        client_socket.settimeout(5.0)
        data = b""
        while b"\n" not in data:
            chunk = client_socket.recv(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > 2_000_000:
                raise ProtocolError("request too large")
        return data.split(b"\n", 1)[0].rstrip(b"\r")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local plain TCP Poker MCCFR server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = PokerSocketServer(args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...", flush=True)
    finally:
        server.stop()


if __name__ == "__main__":
    main()
