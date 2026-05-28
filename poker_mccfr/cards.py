from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

RANKS = "23456789TJQKA"
SUITS = "cdhs"
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}
VALUE_RANK = {v: r for r, v in RANK_VALUE.items()}


@dataclass(frozen=True, order=True)
class Card:
    rank: str
    suit: str

    def __post_init__(self) -> None:
        if self.rank not in RANKS or self.suit not in SUITS:
            raise ValueError(f"invalid card: {self.rank}{self.suit}")

    @property
    def value(self) -> int:
        return RANK_VALUE[self.rank]

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


def parse_card(text: str) -> Card:
    text = text.strip()
    if len(text) != 2:
        raise ValueError(f"card must have two chars: {text!r}")
    return Card(text[0].upper(), text[1].lower())


def parse_cards(text: str | Iterable[str]) -> tuple[Card, ...]:
    if isinstance(text, str):
        compact = text.replace(" ", "").replace(",", "")
        if len(compact) % 2 != 0:
            raise ValueError("cards string must contain two-character cards")
        return tuple(parse_card(compact[i:i + 2]) for i in range(0, len(compact), 2))
    return tuple(parse_card(x) for x in text)


def full_deck() -> tuple[Card, ...]:
    return tuple(Card(rank, suit) for rank in RANKS for suit in SUITS)


def card_set(cards: Iterable[Card]) -> set[str]:
    return {str(card) for card in cards}


def canonical_hand(hand: Iterable[Card]) -> str:
    first, second = sorted(tuple(hand), key=lambda c: (c.value, c.suit), reverse=True)
    return f"{first}{second}"


def hand_combos_from_range(range_text: str, blocked: Iterable[Card] = ()) -> list[tuple[Card, Card]]:
    """Parse compact Hold'em ranges such as 'AA,AKs,AQo,72o,random'."""
    blocked_names = card_set(blocked)
    deck = [card for card in full_deck() if str(card) not in blocked_names]
    tokens = [token.strip() for token in range_text.replace(";", ",").split(",") if token.strip()]
    if not tokens:
        raise ValueError("empty range")
    if any(token.lower() in {"random", "*", "any"} for token in tokens):
        return list(combinations(deck, 2))

    result: dict[str, tuple[Card, Card]] = {}
    for raw_token in tokens:
        token = raw_token.upper()
        if len(token) == 4 and token[1].lower() in SUITS and token[3].lower() in SUITS:
            hand = (parse_card(token[:2]), parse_card(token[2:]))
            if str(hand[0]) not in blocked_names and str(hand[1]) not in blocked_names and hand[0] != hand[1]:
                result[canonical_hand(hand)] = hand
            continue

        if len(token) not in {2, 3}:
            raise ValueError(f"unsupported range token: {raw_token}")

        rank_one, rank_two = token[0], token[1]
        suitedness = token[2].lower() if len(token) == 3 else None
        if rank_one not in RANKS or rank_two not in RANKS:
            raise ValueError(f"unsupported range token: {raw_token}")
        if suitedness not in {None, "s", "o"}:
            raise ValueError(f"unsupported suitedness in range token: {raw_token}")

        for first, second in combinations(deck, 2):
            ranks = {first.rank, second.rank}
            if rank_one == rank_two:
                ok = first.rank == rank_one and second.rank == rank_one
            else:
                ok = ranks == {rank_one, rank_two}
                if suitedness == "s":
                    ok = ok and first.suit == second.suit
                elif suitedness == "o":
                    ok = ok and first.suit != second.suit
            if ok:
                result[canonical_hand((first, second))] = (first, second)
    return list(result.values())
