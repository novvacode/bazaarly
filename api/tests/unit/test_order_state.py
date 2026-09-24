"""Exhaustive tests of the order state machine over every (from, to, mode, actor)."""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import pytest

from app.models.order import FulfillmentMode, OrderStatus, PaymentMethod, PaymentStatus
from app.services.order_state import (
    Actor,
    InvalidTransition,
    NotifyCustomerStatus,
    NotifyOwnerNewOrder,
    RefundRequired,
    allowed_transitions,
    creation_effects,
    initial_status,
    transition,
)

S = OrderStatus
P, D = FulfillmentMode.pickup, FulfillmentMode.delivery
M, SYS = Actor.merchant, Actor.system


@dataclass
class FakeOrder:
    status: OrderStatus
    fulfillment_mode: FulfillmentMode
    payment_status: PaymentStatus = PaymentStatus.pending


# The spec's table (SPEC §10.1), written out independently of the implementation.
EXPECTED: set[tuple[OrderStatus, OrderStatus, FulfillmentMode, Actor]] = set()
for mode in (P, D):
    EXPECTED |= {
        (S.pending_payment, S.placed, mode, SYS),
        (S.pending_payment, S.cancelled, mode, SYS),
        (S.placed, S.confirmed, mode, M),
        (S.placed, S.cancelled, mode, M),
        (S.confirmed, S.preparing, mode, M),
        (S.confirmed, S.cancelled, mode, M),
        (S.preparing, S.cancelled, mode, M),
    }
EXPECTED |= {
    (S.preparing, S.ready, P, M),
    (S.preparing, S.out_for_delivery, D, M),
    (S.ready, S.completed, P, M),
    (S.out_for_delivery, S.completed, D, M),
}

ALL = list(itertools.product(list(S), list(S), [P, D], [M, SYS]))


@pytest.mark.parametrize(("frm", "to", "mode", "actor"), ALL)
def test_every_combination(
    frm: OrderStatus, to: OrderStatus, mode: FulfillmentMode, actor: Actor
) -> None:
    order = FakeOrder(frm, mode)
    allowed = (frm, to, mode, actor) in EXPECTED
    assert (to in allowed_transitions(order, actor)) is allowed
    if allowed:
        effects = transition(order, to, actor)
        assert NotifyCustomerStatus(to) in effects
    else:
        with pytest.raises(InvalidTransition):
            transition(order, to, actor)


@pytest.mark.parametrize("status", [S.completed, S.cancelled])
def test_terminal_states_have_no_moves(status: OrderStatus) -> None:
    for mode, actor in itertools.product([P, D], [M, SYS]):
        assert allowed_transitions(FakeOrder(status, mode), actor) == set()


def test_ready_and_out_for_delivery_cannot_be_cancelled() -> None:
    assert S.cancelled not in allowed_transitions(FakeOrder(S.ready, P), M)
    assert S.cancelled not in allowed_transitions(FakeOrder(S.out_for_delivery, D), M)


def test_payment_confirmation_notifies_owner() -> None:
    effects = transition(FakeOrder(S.pending_payment, P), S.placed, SYS)
    assert effects == [NotifyOwnerNewOrder(), NotifyCustomerStatus(S.placed)]


def test_cancelling_paid_order_requires_manual_refund() -> None:
    paid = FakeOrder(S.confirmed, D, PaymentStatus.paid)
    assert RefundRequired() in transition(paid, S.cancelled, M)
    unpaid = FakeOrder(S.confirmed, D, PaymentStatus.pending)
    assert RefundRequired() not in transition(unpaid, S.cancelled, M)


def test_initial_status_and_creation_effects() -> None:
    assert initial_status(PaymentMethod.cod) == S.placed
    assert initial_status(PaymentMethod.online) == S.pending_payment
    assert creation_effects(S.placed) == [NotifyOwnerNewOrder(), NotifyCustomerStatus(S.placed)]
    assert creation_effects(S.pending_payment) == []
