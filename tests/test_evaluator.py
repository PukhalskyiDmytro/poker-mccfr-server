from poker_mccfr.cards import parse_cards
from poker_mccfr.evaluator import compare_hands, evaluate_seven


def test_flush_beats_straight():
    flush = evaluate_seven(parse_cards("AhKhQhJh2h3c4d"))
    straight = evaluate_seven(parse_cards("AcKdQhJsTc2d3s"))
    assert flush > straight


def test_compare_tie():
    board = parse_cards("AhKdQsJcTc")
    assert compare_hands(parse_cards("2d3d"), parse_cards("2s3s"), board) == 0
