import socket
import threading
import time

from poker_mccfr.server import PokerSocketServer, handle_command, parse_command, solve_params


def test_parse_command():
    command, params = parse_command("SOLVE board=AhKdQsJc2d oop_range=AA ip_range=KK iterations=10")
    assert command == "SOLVE"
    assert params["board"] == "AhKdQsJc2d"
    assert params["oop_range"] == "AA"
    assert params["ip_range"] == "KK"
    assert params["iterations"] == "10"


def test_health_command():
    assert handle_command("HEALTH") == "OK status=ok\n"


def test_help_command():
    response = handle_command("HELP")
    assert response.startswith("OK")
    assert "SOLVE board=<cards>" in response


def test_solve_params_directly():
    result = solve_params({
        "board": "AhKdQsJc2d",
        "oop_range": "AA,AKs",
        "ip_range": "QQ,AKs",
        "iterations": "10",
    })
    assert result.infosets > 0
    assert result.strategies
    assert result.ev_ip == -result.ev_oop


def test_solve_command_returns_plain_text():
    response = handle_command("SOLVE board=AhKdQsJc2d oop_range=AA,AKs ip_range=QQ,AKs iterations=10")
    assert response.startswith("OK\n")
    assert "iterations=10" in response
    assert "strategies:" in response
    assert response.endswith("END\n")


def test_bad_command_returns_error():
    response = handle_command("SOLVE board=AhKdQsJc2d")
    assert response.startswith("ERROR ")


def test_live_socket_server_health():
    server = PokerSocketServer("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    deadline = time.time() + 5
    while server.address[1] == 0 and time.time() < deadline:
        time.sleep(0.01)

    with socket.create_connection(server.address, timeout=5) as client:
        client.sendall(b"HEALTH\n")
        response = client.recv(4096).decode("utf-8")

    server.stop()
    assert response == "OK status=ok\n"
