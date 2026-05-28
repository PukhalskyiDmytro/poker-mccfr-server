from __future__ import annotations

import argparse
import json
import socket
import threading
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

from .cards import parse_cards
from .game import ActionSpec, GameConfig, LimitType
from .mccfr import MCCFRSolver

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


class BadRequest(ValueError):
    pass


def _json_default(value: Any) -> Any:
    if isinstance(value, LimitType):
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def action_from_payload(payload: dict[str, Any]) -> ActionSpec:
    if not isinstance(payload, dict):
        raise BadRequest("action must be an object")
    code = payload.get("code")
    kind = payload.get("kind")
    fraction = payload.get("fraction")
    if not isinstance(code, str) or not code:
        raise BadRequest("action.code must be a non-empty string")
    if kind not in {"check", "bet", "fold", "call", "raise"}:
        raise BadRequest("action.kind must be one of check, bet, fold, call, raise")
    if fraction is not None:
        try:
            fraction = float(fraction)
        except (TypeError, ValueError) as exc:
            raise BadRequest("action.fraction must be numeric or null") from exc
        if fraction < 0:
            raise BadRequest("action.fraction cannot be negative")
    return ActionSpec(code=code, kind=kind, fraction=fraction)


def _actions_from_payload(payload: Any, default: tuple[ActionSpec, ...]) -> tuple[ActionSpec, ...]:
    if payload is None:
        return default
    if not isinstance(payload, list) or not payload:
        raise BadRequest("actions must be a non-empty list")
    return tuple(action_from_payload(item) for item in payload)


def _positive_float(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise BadRequest(f"{key} must be numeric") from exc
    if value <= 0:
        raise BadRequest(f"{key} must be positive")
    return value


def _positive_int(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise BadRequest(f"{key} must be an integer") from exc
    if value <= 0:
        raise BadRequest(f"{key} must be positive")
    return value


def build_config(payload: dict[str, Any]) -> GameConfig:
    limit_raw = payload.get("limit_type", LimitType.NO_LIMIT.value)
    try:
        limit_type = LimitType(limit_raw)
    except ValueError as exc:
        raise BadRequest("limit_type must be 'no-limit' or 'pot-limit'") from exc

    return GameConfig(
        initial_pot=_positive_float(payload, "initial_pot", 100.0),
        effective_stack=_positive_float(payload, "effective_stack", 300.0),
        limit_type=limit_type,
        first_actions=_actions_from_payload(payload.get("first_actions"), DEFAULT_FIRST_ACTIONS),
        response_actions=_actions_from_payload(payload.get("response_actions"), DEFAULT_RESPONSE_ACTIONS),
        max_raises_per_round=_positive_int(payload, "max_raises_per_round", 2),
    )


def solve_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BadRequest("request body must be a JSON object")

    board = payload.get("board")
    oop_range = payload.get("oop_range")
    ip_range = payload.get("ip_range")
    if not isinstance(board, str) or not board:
        raise BadRequest("board must be a non-empty string")
    if not isinstance(oop_range, str) or not oop_range:
        raise BadRequest("oop_range must be a non-empty string")
    if not isinstance(ip_range, str) or not ip_range:
        raise BadRequest("ip_range must be a non-empty string")

    iterations = _positive_int(payload, "iterations", 1000)
    if iterations > 200_000:
        raise BadRequest("iterations cannot exceed 200000")

    seed = payload.get("seed", 7)
    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError) as exc:
            raise BadRequest("seed must be an integer or null") from exc

    config = build_config(payload)
    solver = MCCFRSolver(config, parse_cards(board), oop_range, ip_range, seed)
    result = solver.train(iterations)
    return asdict(result)


def json_response(status_code: int, payload: dict[str, Any]) -> bytes:
    reason = {
        200: "OK",
        400: "Bad Request",
        404: "Not Found",
        405: "Method Not Allowed",
        500: "Internal Server Error",
    }.get(status_code, "OK")
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=_json_default).encode("utf-8")
    headers = [
        f"HTTP/1.1 {status_code} {reason}",
        "Content-Type: application/json; charset=utf-8",
        f"Content-Length: {len(body)}",
        "Connection: close",
        "",
        "",
    ]
    return "\r\n".join(headers).encode("ascii") + body


def parse_http_request(raw: bytes) -> tuple[str, str, dict[str, str], bytes]:
    try:
        header_bytes, body = raw.split(b"\r\n\r\n", 1)
        header_text = header_bytes.decode("iso-8859-1")
    except ValueError as exc:
        raise BadRequest("malformed HTTP request") from exc

    lines = header_text.split("\r\n")
    try:
        method, target, _version = lines[0].split(" ", 2)
    except ValueError as exc:
        raise BadRequest("malformed request line") from exc

    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise BadRequest("malformed header")
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return method.upper(), urlparse(target).path, headers, body


def handle_http_request(raw: bytes) -> bytes:
    try:
        method, path, _headers, body = parse_http_request(raw)
        if method == "GET" and path == "/health":
            return json_response(200, {"status": "ok"})
        if method == "GET" and path == "/":
            return json_response(200, {"name": "poker-mccfr-server", "endpoints": ["GET /health", "POST /solve"]})
        if path == "/solve" and method != "POST":
            return json_response(405, {"error": "method not allowed"})
        if method == "POST" and path == "/solve":
            try:
                payload = json.loads(body.decode("utf-8") if body else "{}")
            except json.JSONDecodeError as exc:
                raise BadRequest("request body must be valid JSON") from exc
            return json_response(200, solve_payload(payload))
        return json_response(404, {"error": "not found"})
    except BadRequest as exc:
        return json_response(400, {"error": str(exc)})
    except Exception as exc:  # pragma: no cover - defensive server boundary
        return json_response(500, {"error": str(exc)})


class PokerSocketServer:
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
            print(f"Poker MCCFR socket server listening on http://{self.address[0]}:{self.address[1]}", flush=True)

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
                request = self._read_request(client_socket)
                response = handle_http_request(request)
                client_socket.sendall(response)
            except OSError:
                return

    @staticmethod
    def _read_request(client_socket: socket.socket) -> bytes:
        client_socket.settimeout(5.0)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = client_socket.recv(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > 2_000_000:
                raise BadRequest("request too large")

        if b"\r\n\r\n" not in data:
            return data

        headers, body = data.split(b"\r\n\r\n", 1)
        content_length = 0
        for line in headers.decode("iso-8859-1").split("\r\n")[1:]:
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
                break

        while len(body) < content_length:
            chunk = client_socket.recv(min(4096, content_length - len(body)))
            if not chunk:
                break
            body += chunk
        return headers + b"\r\n\r\n" + body


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local socket-based Poker MCCFR server.")
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
