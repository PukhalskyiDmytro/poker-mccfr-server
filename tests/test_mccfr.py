from poker_mccfr.cards import parse_cards
from poker_mccfr.game import GameConfig
from poker_mccfr.mccfr import MCCFRSolver


def test_solver_trains_and_returns_probabilities():
    solver = MCCFRSolver(GameConfig(), parse_cards("AhKdQsJc2d"), "AA,AKs", "QQ,AKs", seed=1)
    result = solver.train(20)
    assert result.infosets > 0
    assert result.ev_ip == -result.ev_oop
    assert result.exploitability >= 0
    for probs in result.strategies.values():
        assert abs(sum(probs.values()) - 1.0) < 1e-9


def test_solver_rejects_impossible_ranges():
    try:
        MCCFRSolver(GameConfig(), parse_cards("AhAdAcAsKd"), "AA", "AA")
    except ValueError as error:
        assert "no compatible" in str(error) or "empty" in str(error)
    else:
        raise AssertionError("expected ValueError")
