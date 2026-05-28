from __future__ import annotations

import random
from dataclasses import dataclass, field
from .cards import Card, hand_combos_from_range
from .game import GameConfig, PokerGame, GameState, Player


@dataclass
class InfoSet:
    actions: tuple[str, ...]
    regrets: dict[str, float] = field(default_factory=dict)
    strategy_sum: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for action in self.actions:
            self.regrets.setdefault(action, 0.0)
            self.strategy_sum.setdefault(action, 0.0)

    def strategy(self) -> dict[str, float]:
        positive_regrets = {action: max(0.0, self.regrets.get(action, 0.0)) for action in self.actions}
        total = sum(positive_regrets.values())
        if total <= 1e-12:
            return {action: 1.0 / len(self.actions) for action in self.actions}
        return {action: positive_regrets[action] / total for action in self.actions}

    def average_strategy(self) -> dict[str, float]:
        total = sum(self.strategy_sum.values())
        if total <= 1e-12:
            return {action: 1.0 / len(self.actions) for action in self.actions}
        return {action: self.strategy_sum[action] / total for action in self.actions}


@dataclass
class SolveResult:
    iterations: int
    ev_oop: float
    ev_ip: float
    exploitability: float
    strategies: dict[str, dict[str, float]]
    infosets: int


class MCCFRSolver:
    def __init__(
        self,
        config: GameConfig,
        board: tuple[Card, ...],
        oop_range: str,
        ip_range: str,
        seed: int | None = 7,
    ):
        self.rng = random.Random(seed)
        self.game = PokerGame(config, board)
        self.oop_hands = hand_combos_from_range(oop_range, board)
        self.ip_hands = hand_combos_from_range(ip_range, board)
        self.compatible = [
            (oop, ip)
            for oop in self.oop_hands
            for ip in self.ip_hands
            if not {str(oop[0]), str(oop[1])} & {str(ip[0]), str(ip[1])}
        ]
        if not self.compatible:
            raise ValueError("ranges have no compatible hand pairs")
        self.nodes: dict[str, InfoSet] = {}

    def _node(self, state: GameState, hand: tuple[Card, Card]) -> InfoSet:
        key = self.game.info_key(state, hand)
        actions = tuple(action.code for action in self.game.legal_actions(state))
        node = self.nodes.get(key)
        if node is None or node.actions != actions:
            node = InfoSet(actions)
            self.nodes[key] = node
        return node

    def train(self, iterations: int = 1000) -> SolveResult:
        for _ in range(iterations):
            oop, ip = self.rng.choice(self.compatible)
            self._cfr(self.game.initial_state(), oop, ip, Player.OOP, 1.0, 1.0)
            self._cfr(self.game.initial_state(), oop, ip, Player.IP, 1.0, 1.0)

        ev = self.evaluate_ev()
        br_oop = self.best_response(Player.OOP)
        br_ip = self.best_response(Player.IP)
        exploitability = max(0.0, (br_oop - ev) + (br_ip + ev)) / 2.0
        return SolveResult(
            iterations=iterations,
            ev_oop=ev,
            ev_ip=-ev,
            exploitability=exploitability,
            strategies=self.average_strategies(),
            infosets=len(self.nodes),
        )

    def _cfr(
        self,
        state: GameState,
        oop: tuple[Card, Card],
        ip: tuple[Card, Card],
        updating: Player,
        p_oop: float,
        p_ip: float,
    ) -> float:
        if state.terminal:
            payoff = self.game.payoff_oop(state, oop, ip)
            return payoff if updating == Player.OOP else -payoff

        hand = oop if state.acting == Player.OOP else ip
        node = self._node(state, hand)
        strategy = node.strategy()
        actions = list(node.actions)
        action_utils: dict[str, float] = {}
        node_util = 0.0

        for action in actions:
            next_state = self.game.apply(state, action)
            if state.acting == Player.OOP:
                util = self._cfr(next_state, oop, ip, updating, p_oop * strategy[action], p_ip)
            else:
                util = self._cfr(next_state, oop, ip, updating, p_oop, p_ip * strategy[action])
            action_utils[action] = util
            node_util += strategy[action] * util

        if state.acting == updating:
            opponent_reach = p_ip if updating == Player.OOP else p_oop
            self_reach = p_oop if updating == Player.OOP else p_ip
            for action in actions:
                node.regrets[action] += opponent_reach * (action_utils[action] - node_util)
                node.strategy_sum[action] += self_reach * strategy[action]

        return node_util

    def average_strategies(self) -> dict[str, dict[str, float]]:
        return {key: node.average_strategy() for key, node in sorted(self.nodes.items())}

    def _avg_strategy_for(self, state: GameState, hand: tuple[Card, Card]) -> dict[str, float]:
        return self._node(state, hand).average_strategy()

    def evaluate_ev(self) -> float:
        return sum(self._eval_state(self.game.initial_state(), oop, ip) for oop, ip in self.compatible) / len(self.compatible)

    def _eval_state(self, state: GameState, oop: tuple[Card, Card], ip: tuple[Card, Card]) -> float:
        if state.terminal:
            return self.game.payoff_oop(state, oop, ip)
        hand = oop if state.acting == Player.OOP else ip
        strategy = self._avg_strategy_for(state, hand)
        return sum(
            probability * self._eval_state(self.game.apply(state, action), oop, ip)
            for action, probability in strategy.items()
        )

    def best_response(self, player: Player) -> float:
        values = [self._br_state(self.game.initial_state(), oop, ip, player) for oop, ip in self.compatible]
        return sum(values) / len(values)

    def _br_state(self, state: GameState, oop: tuple[Card, Card], ip: tuple[Card, Card], player: Player) -> float:
        if state.terminal:
            payoff = self.game.payoff_oop(state, oop, ip)
            return payoff if player == Player.OOP else -payoff

        actions = [action.code for action in self.game.legal_actions(state)]
        if state.acting == player:
            return max(self._br_state(self.game.apply(state, action), oop, ip, player) for action in actions)

        hand = oop if state.acting == Player.OOP else ip
        strategy = self._avg_strategy_for(state, hand)
        return sum(
            strategy[action] * self._br_state(self.game.apply(state, action), oop, ip, player)
            for action in actions
        )
