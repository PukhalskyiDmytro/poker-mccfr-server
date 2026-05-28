# poker-mccfr-server

Local plain TCP server that models a two-player poker betting abstraction and trains approximate equilibrium strategies with Monte-Carlo Counterfactual Regret Minimization (MCCFR).

The implementation focuses on river/all-known-board subgames. It supports OOP/IP positions, configurable initial pot and stacks, no-limit or pot-limit sizing caps, separate first-action and response-action abstractions, hand ranges, EV calculation, and a best-response based exploitability estimate.

This version intentionally does **not** use FastAPI, Uvicorn, Pydantic, Flask, HTTP routing, HTTP headers, or JSON. The server is implemented directly on top of Python's standard-library `socket` module and speaks a small plain-text command protocol.

## Install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
```

## Run tests

```bash
pytest
```

## Run local TCP server

```bash
python -m poker_mccfr.server --host 127.0.0.1 --port 8000
```

The server accepts one line of text per TCP connection and returns a plain-text response.

## Protocol

### Health check

Send:

```text
HEALTH
```

Response:

```text
OK status=ok
```

### Help

Send:

```text
HELP
```

### Solve

Send one line:

```text
SOLVE board=AhKdQsJc2d oop_range=AA,AKs,AQo ip_range=QQ,AK,AQs initial_pot=100 effective_stack=300 limit_type=no-limit iterations=2000
```

Response format:

```text
OK
iterations=2000
ev_oop=...
ev_ip=...
exploitability=...
infosets=...
strategies:
OOP|AcAd|root check=... bet_25=... bet_100=...
...
END
```

## Simple Python client

```python
import socket

command = "SOLVE board=AhKdQsJc2d oop_range=AA,AKs,AQo ip_range=QQ,AK,AQs iterations=2000\n"

with socket.create_connection(("127.0.0.1", 8000)) as client:
    client.sendall(command.encode("utf-8"))
    response = client.recv(2_000_000).decode("utf-8")

print(response)
```

## Windows PowerShell client

```powershell
$client = [System.Net.Sockets.TcpClient]::new("127.0.0.1", 8000)
$stream = $client.GetStream()
$writer = [System.IO.StreamWriter]::new($stream)
$reader = [System.IO.StreamReader]::new($stream)
$writer.AutoFlush = $true
$writer.WriteLine("HEALTH")
$response = $reader.ReadToEnd()
$response
$client.Close()
```

For solving, replace `HEALTH` with:

```text
SOLVE board=AhKdQsJc2d oop_range=AA,AKs,AQo ip_range=QQ,AK,AQs initial_pot=100 effective_stack=300 limit_type=no-limit iterations=2000
```

## Optional action abstractions

You can override action abstractions with comma-separated `code:kind:fraction` tokens:

```text
first_actions=check:check,bet_25:bet:0.25,bet_100:bet:1.0
response_actions=fold:fold,call:call,raise_50:raise:0.5,raise_100:raise:1.0
```

## Range syntax

Supported compact tokens include:

- `AA`, `QQ`: pocket pairs.
- `AKs`: suited combos.
- `AQo`: offsuit combos.
- `AK`: suited and offsuit rank combos.
- `AhKh`: exact combo.
- `random`, `*`, `any`: every unblocked two-card combo.
