import json
import socket
import threading
import time

from poker_mccfr.server import PokerSocketServer, handle_http_request, solve_payload


def _body(response: bytes) -> dict:
    return json.loads(response.split(b"\r\n\r\n", 1)[1].decode("utf-8"))


def test_health_handler():
    response = handle_http_request(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
    assert response.startswith(b"HTTP/1.1 200 OK")
    assert _body(response) == {"status": "ok"}


def test_solve_payload_directly():
    result = solve_payload({
        "board": "AhKdQsJc2d",
        "oop_range": "AA,AKs",
        "ip_range": "QQ,AKs",
        "iterations": 10,
    })
    assert result["infosets"] > 0
    assert "strategies" in result
    assert result["ev_ip"] == -result["ev_oop"]


def test_solve_handler_rejects_bad_json():
    response = handle_http_request(b"POST /solve HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1\r\n\r\nx")
    assert response.startswith(b"HTTP/1.1 400 Bad Request")


def test_live_socket_server_health():
    server = PokerSocketServer("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    deadline = time.time() + 5
    while server.address[1] == 0 and time.time() < deadline:
        time.sleep(0.01)

    with socket.create_connection(server.address, timeout=5) as client:
        client.sendall(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
        response = client.recv(4096)

    server.stop()
    assert response.startswith(b"HTTP/1.1 200 OK")
    assert _body(response) == {"status": "ok"}
