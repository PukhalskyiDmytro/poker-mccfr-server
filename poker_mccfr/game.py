from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Sequence
from .cards import Card, canonical_hand
from .evaluator import compare_hands


class Player(str, Enum):
    OOP = "OOP"
    IP = "IP"


class LimitType(str, Enum):
    NO_LIMIT = "no-limit"
    POT_LIMIT = "pot-limit"


@dataclass(frozen=True)
class ActionSpec:
    code: str
    kind: str
    fraction: float | None = None


@dataclass(frozen=True)
class GameConfig:
    initial_pot: float = 100.0
    effective_stack: float = 300.0
    limit_type: LimitType = LimitType.NO_LIMIT
    first_actions: tuple[ActionSpec, ...] = (
        ActionSpec("check", "check"),
        ActionSpec("bet_25", "bet", 0.25),
        ActionSpec("bet_100", "bet", 1.0),
    )
    response_actions: tuple[ActionSpec, ...] = (
        ActionSpec("fold", "fold"),
        ActionSpec("call", "call"),
        ActionSpec("raise_50", "raise", 0.5),
        ActionSpec("raise_100", "raise", 1.0),
    )
    max_raises_per_round: int = 2
    rounds: tuple[str, ...] = ("river",)


@dataclass(frozen=True)
class GameState:
    acting: Player = Player.OOP
    street_index: int = 0
    pot: float = 100.0
    committed: tuple[float, float] = (0.0, 0.0)
    current_bet: float = 0.0
    raises_this_round: int = 0
    checked_once: bool = False
    terminal: bool = False
    folded: Player | None = None
    history: tuple[str, ...] = field(default_factory=tuple)

    @property
    def to_call(self) -> float:
        idx = 0 if self.acting == Player.OOP else 1
        return max(0.0, self.current_bet - self.committed[idx])

    @property
    def street(self) -> str:
        return "terminal" if self.terminal else "river"

    @property
    def key_history(self) -> str:
        return "/".join(self.history) if self.history else "root"


class PokerGame:
    def __init__(self, config: GameConfig, board: Sequence[Card]):
        if len(set(map(str, board))) != len(board):
            raise ValueError("board contains duplicate cards")
        if len(board) < 5:
            raise ValueError("this implementation expects river/all-known-board cards")
        self.config = config
        self.board = tuple(board)

    def initial_state(self) -> GameState:
        return GameState(pot=self.config.initial_pot)

    @staticmethod
    def other(player: Player) -> Player:
        return Player.IP if player == Player.OOP else Player.OOP

    def legal_actions(self, state: GameState) -> list[ActionSpec]:
        if state.terminal:
            return []
        if state.to_call <= 1e-9:
            return list(self.config.first_actions)

        actions: list[ActionSpec] = []
        for action in self.config.response_actions:
            if action.kind == "raise" and state.raises_this_round >= self.config.max_raises_per_round:
                continue
            if action.kind == "raise" and self._raise_to_amount(state, action) <= state.current_bet + 1e-9:
                continue
            actions.append(action)
        return actions

    def apply(self, state: GameState, action_code: str) -> GameState:
        action = next((candidate for candidate in self.legal_actions(state) if candidate.code == action_code), None)
        if action is None:
            raise ValueError(f"illegal action {action_code} for {state}")

        idx = 0 if state.acting == Player.OOP else 1
        committed = list(state.committed)
        history = state.history + (f"{state.acting}:{action.code}",)

        if action.kind == "fold":
            return replace(state, terminal=True, folded=state.acting, history=history)

        if action.kind == "check":
            if state.checked_once:
                return replace(state, terminal=True, history=history)
            return replace(state, acting=self.other(state.acting), checked_once=True, history=history)

        if action.kind == "call":
            amount = min(state.to_call, self.config.effective_stack - committed[idx])
            committed[idx] += amount
            return replace(state, pot=state.pot + amount, committed=tuple(committed), terminal=True, history=history)

        if action.kind == "bet":
            amount = self._bet_amount(state, action)
            committed[idx] += amount
            return replace(
                state,
                acting=self.other(state.acting),
                pot=state.pot + amount,
                committed=tuple(committed),
                current_bet=committed[idx],
                checked_once=False,
                history=history,
            )

        if action.kind == "raise":
            target = self._raise_to_amount(state, action)
            amount = target - committed[idx]
            committed[idx] = target
            return replace(
                state,
                acting=self.other(state.acting),
                pot=state.pot + amount,
                committed=tuple(committed),
                current_bet=target,
                raises_this_round=state.raises_this_round + 1,
                checked_once=False,
                history=history,
            )

        raise AssertionError(action.kind)

    def _cap(self, state: GameState, target_extra: float) -> float:
        idx = 0 if state.acting == Player.OOP else 1
        stack_left = self.config.effective_stack - state.committed[idx]
        if self.config.limit_type == LimitType.POT_LIMIT and state.to_call > 0:
            pot_limit_raise_extra = state.to_call + state.pot + state.to_call
            target_extra = min(target_extra, pot_limit_raise_extra)
        return max(0.0, min(stack_left, target_extra))

    def _bet_amount(self, state: GameState, action: ActionSpec) -> float:
        amount = (action.fraction or 0.0) * state.pot
        return self._cap(state, amount)

    def _raise_to_amount(self, state: GameState, action: ActionSpec) -> float:
        idx = 0 if state.acting == Player.OOP else 1
        call = state.to_call
        raise_extra = (action.fraction or 0.0) * (state.pot + call)
        total_extra = call + raise_extra
        return state.committed[idx] + self._cap(state, total_extra)

    def payoff_oop(self, state: GameState, oop_hand: tuple[Card, Card], ip_hand: tuple[Card, Card]) -> float:
        if not state.terminal:
            raise ValueError("payoff requested for non-terminal state")
        if state.folded == Player.OOP:
            return -state.committed[0]
        if state.folded == Player.IP:
            return state.pot - state.committed[0]

        comparison = compare_hands(oop_hand, ip_hand, self.board)
        if comparison > 0:
            return state.pot - state.committed[0]
        if comparison < 0:
            return -state.committed[0]
        return state.pot / 2.0 - state.committed[0]

    def info_key(self, state: GameState, hand: tuple[Card, Card]) -> str:
        return f"{state.acting}|{canonical_hand(hand)}|{state.key_history}"
