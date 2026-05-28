# poker-mccfr-server

Local socket-based HTTP server that models a two-player poker betting abstraction and trains approximate equilibrium strategies with Monte-Carlo Counterfactual Regret Minimization (MCCFR).

The implementation focuses on river/all-known-board subgames. It supports OOP/IP positions, configurable initial pot and stacks, no-limit or pot-limit sizing caps, separate first-action and response-action abstractions, hand ranges, EV calculation, and a best-response based exploitability estimate.

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

## Run local socket server

```bash
python -m poker_mccfr.server --host 127.0.0.1 --port 8000
```

The server speaks minimal HTTP over a raw TCP socket.

## Endpoints

### `GET /health`

Returns:

```json
{"status": "ok"}
```

### `POST /solve`

Example:

```bash
curl -X POST http://127.0.0.1:8000/solve \
  -H "Content-Type: application/json" \
  -d '{
    "board": "AhKdQsJc2d",
    "oop_range": "AA,AKs,AQo",
    "ip_range": "QQ,AK,AQs",
    "initial_pot": 100,
    "effective_stack": 300,
    "limit_type": "no-limit",
    "iterations": 2000
  }'
```

## Response fields

- `strategies`: average action probabilities by information set. The key format is `player|private_hand|history`.
- `ev_oop`, `ev_ip`: expected value for OOP and IP in chips. This is zero-sum, so `ev_ip = -ev_oop`.
- `exploitability`: approximate exploitability computed as the average gain from best responses to the learned average strategies.
- `infosets`: number of information sets visited during training.

## Range syntax

Supported compact tokens include:

- `AA`, `QQ`: pocket pairs.
- `AKs`: suited combos.
- `AQo`: offsuit combos.
- `AK`: suited and offsuit rank combos.
- `AhKh`: exact combo.
- `random`, `*`, `any`: every unblocked two-card combo.
