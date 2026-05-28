from poker_mccfr.cards import parse_cards
from poker_mccfr.game import GameConfig, LimitType, PokerGame


def test_initial_legal_actions_are_first_actions():
    game = PokerGame(GameConfig(), parse_cards("AhKdQsJc2d"))
    assert [action.code for action in game.legal_actions(game.initial_state())] == ["check", "bet_25", "bet_100"]


def test_check_check_is_terminal():
    game = PokerGame(GameConfig(), parse_cards("AhKdQsJc2d"))
    state = game.apply(game.initial_state(), "check")
    state = game.apply(state, "check")
    assert state.terminal


def test_bet_fold_payoff():
    game = PokerGame(GameConfig(initial_pot=100, effective_stack=300), parse_cards("AhKdQsJc2d"))
    state = game.apply(game.initial_state(), "bet_100")
    state = game.apply(state, "fold")
    payoff = game.payoff_oop(state, parse_cards("AcAd"), parse_cards("KcKh"))
    assert payoff == 100


def test_pot_limit_raise_is_legal():
    game = PokerGame(GameConfig(limit_type=LimitType.POT_LIMIT), parse_cards("AhKdQsJc2d"))
    state = game.apply(game.initial_state(), "bet_25")
    assert "raise_50" in [action.code for action in game.legal_actions(state)]
