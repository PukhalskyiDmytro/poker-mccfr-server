from __future__ import annotations

from collections import Counter
from itertools import combinations
from .cards import Card

CATEGORY = {
    8: "straight_flush",
    7: "quads",
    6: "full_house",
    5: "flush",
    4: "straight",
    3: "trips",
    2: "two_pair",
    1: "pair",
    0: "high_card",
}


def _straight_high(values: list[int]) -> int | None:
    unique = sorted(set(values), reverse=True)
    if 14 in unique:
        unique.append(1)
    for window in zip(*(unique[i:] for i in range(5))):
        if window[0] - window[4] == 4 and len(set(window)) == 5:
            return window[0]
    return None


def evaluate_five(cards: tuple[Card, ...]) -> tuple[int, tuple[int, ...]]:
    if len(cards) != 5:
        raise ValueError("exactly five cards required")

    values = sorted((card.value for card in cards), reverse=True)
    counts = Counter(values)
    groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    flush = len({card.suit for card in cards}) == 1
    straight = _straight_high(values)

    if flush and straight:
        return 8, (straight,)
    if groups[0][1] == 4:
        quad = groups[0][0]
        kicker = max(value for value in values if value != quad)
        return 7, (quad, kicker)
    if groups[0][1] == 3 and groups[1][1] == 2:
        return 6, (groups[0][0], groups[1][0])
    if flush:
        return 5, tuple(values)
    if straight:
        return 4, (straight,)
    if groups[0][1] == 3:
        trips = groups[0][0]
        kickers = tuple(value for value in values if value != trips)
        return 3, (trips, *kickers)
    if groups[0][1] == 2 and groups[1][1] == 2:
        pairs = sorted([groups[0][0], groups[1][0]], reverse=True)
        kicker = max(value for value in values if value not in pairs)
        return 2, (*pairs, kicker)
    if groups[0][1] == 2:
        pair = groups[0][0]
        kickers = tuple(value for value in values if value != pair)
        return 1, (pair, *kickers)
    return 0, tuple(values)


def evaluate_seven(cards: tuple[Card, ...]) -> tuple[int, tuple[int, ...]]:
    if len(cards) < 5:
        raise ValueError("at least five cards required")
    return max(evaluate_five(tuple(combo)) for combo in combinations(cards, 5))


def compare_hands(hero: tuple[Card, Card], villain: tuple[Card, Card], board: tuple[Card, ...]) -> int:
    hero_value = evaluate_seven(tuple(hero) + tuple(board))
    villain_value = evaluate_seven(tuple(villain) + tuple(board))
    return (hero_value > villain_value) - (hero_value < villain_value)
