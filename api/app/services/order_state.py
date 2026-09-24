"""Order lifecycle as a pure function (SPEC §10.1). No I/O here: callers apply the effects.

pending_payment → placed → confirmed → preparing → ready | out_for_delivery → completed
placed / confirmed / preparing → cancelled (merchant); pending_payment → cancelled (system)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Protocol

from app.models.order import FulfillmentMode, OrderStatus, PaymentMethod, PaymentStatus

S = OrderStatus


class Actor(enum.StrEnum):
    system = "system"  # payment confirmation, expiry jobs
    merchant = "merchant"  # owner or staff


class OrderLike(Protocol):
    @property
    def status(self) -> OrderStatus: ...

    @property
    def fulfillment_mode(self) -> FulfillmentMode: ...

    @property
    def payment_status(self) -> PaymentStatus: ...


# from -> to -> actors allowed to make that move
_TRANSITIONS: dict[OrderStatus, dict[OrderStatus, frozenset[Actor]]] = {
    S.pending_payment: {
        S.placed: frozenset({Actor.system}),
        S.cancelled: frozenset({Actor.system}),
    },
    S.placed: {
        S.confirmed: frozenset({Actor.merchant}),
        S.cancelled: frozenset({Actor.merchant}),
    },
    S.confirmed: {
        S.preparing: frozenset({Actor.merchant}),
        S.cancelled: frozenset({Actor.merchant}),
    },
    S.preparing: {
        S.ready: frozenset({Actor.merchant}),
        S.out_for_delivery: frozenset({Actor.merchant}),
        S.cancelled: frozenset({Actor.merchant}),
    },
    S.ready: {S.completed: frozenset({Actor.merchant})},
    S.out_for_delivery: {S.completed: frozenset({Actor.merchant})},
    S.completed: {},
    S.cancelled: {},
}

# Some moves only make sense for one fulfilment mode.
_MODE_ONLY: dict[OrderStatus, FulfillmentMode] = {
    S.ready: FulfillmentMode.pickup,
    S.out_for_delivery: FulfillmentMode.delivery,
}

TERMINAL = frozenset({S.completed, S.cancelled})
ACTIVE = frozenset({S.placed, S.confirmed, S.preparing, S.ready, S.out_for_delivery})


# --- Effects -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NotifyOwnerNewOrder:
    pass


@dataclass(frozen=True, slots=True)
class NotifyCustomerStatus:
    status: OrderStatus


@dataclass(frozen=True, slots=True)
class RefundRequired:
    """A paid online order was cancelled: refunds are manual in the MVP (SPEC §10.1)."""


Effect = NotifyOwnerNewOrder | NotifyCustomerStatus | RefundRequired


class InvalidTransition(Exception):
    def __init__(self, current: OrderStatus, target: OrderStatus) -> None:
        super().__init__(f"Cannot move an order from {current} to {target}")
        self.current = current
        self.target = target


def initial_status(payment_method: PaymentMethod) -> OrderStatus:
    return S.pending_payment if payment_method == PaymentMethod.online else S.placed


def creation_effects(status: OrderStatus) -> list[Effect]:
    if status == S.placed:
        return [NotifyOwnerNewOrder(), NotifyCustomerStatus(S.placed)]
    return []


def allowed_transitions(order: OrderLike, actor: Actor) -> set[OrderStatus]:
    if _MODE_ONLY.get(order.status, order.fulfillment_mode) != order.fulfillment_mode:
        return set()  # inconsistent state (e.g. a delivery order marked "ready"): no moves
    moves = _TRANSITIONS[order.status]
    return {
        to
        for to, actors in moves.items()
        if actor in actors and _MODE_ONLY.get(to, order.fulfillment_mode) == order.fulfillment_mode
    }


def transition(order: OrderLike, to: OrderStatus, actor: Actor) -> list[Effect]:
    """Validate a move and return its side effects. Raises `InvalidTransition`."""
    if to not in allowed_transitions(order, actor):
        raise InvalidTransition(order.status, to)
    effects: list[Effect] = []
    if order.status == S.pending_payment and to == S.placed:
        effects.append(NotifyOwnerNewOrder())
    effects.append(NotifyCustomerStatus(to))
    if to == S.cancelled and order.payment_status == PaymentStatus.paid:
        effects.append(RefundRequired())
    return effects
