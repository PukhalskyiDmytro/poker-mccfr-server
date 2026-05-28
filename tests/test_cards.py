from poker_mccfr.cards import hand_combos_from_range, parse_cards


def test_parse_cards_compact():
    cards = parse_cards("AhKdQs")
    assert [str(card) for card in cards] == ["Ah", "Kd", "Qs"]


def test_range_pair_has_six_combos_when_unblocked():
    assert len(hand_combos_from_range("AA")) == 6


def test_range_suited_has_four_combos_when_unblocked():
    assert len(hand_combos_from_range("AKs")) == 4


def test_range_respects_blockers():
    board = parse_cards("AhKdQsJc2d")
    combos = hand_combos_from_range("AA", board)
    assert all("Ah" not in {str(first), str(second)} for first, second in combos)
