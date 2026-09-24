from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.core import errors
from app.core.errors import AppError
from app.deps import SessionDep, TenantDep
from app.models.order import OrderStatus
from app.schemas.order import (
    DashboardSummaryOut,
    OrderDetailOut,
    OrderListOut,
    SalesOut,
    TransitionIn,
)
from app.services import dashboard as dashboard_service
from app.services import orders as order_service

router = APIRouter(tags=["orders"])


def _parse_statuses(raw: list[str] | None) -> list[OrderStatus]:
    out: list[OrderStatus] = []
    for chunk in raw or []:
        for value in chunk.split(","):
            value = value.strip()
            if not value:
                continue
            try:
                out.append(OrderStatus(value))
            except ValueError:
                raise AppError(
                    errors.VALIDATION_ERROR,
                    f"Unknown status {value!r}",
                    422,
                    details={"fields": {"status": "unknown status"}},
                ) from None
    return out


@router.get("/orders", response_model=OrderListOut, summary="List orders (cursor pagination)")
async def list_orders(
    ctx: TenantDep,
    session: SessionDep,
    status: Annotated[list[str] | None, Query(description="Status, comma separated")] = None,
    from_: Annotated[date | None, Query(alias="from", description="YYYY-MM-DD (local)")] = None,
    to: Annotated[date | None, Query(description="YYYY-MM-DD inclusive (local)")] = None,
    q: Annotated[str | None, Query(max_length=100, description="Order code, name or phone")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> OrderListOut:
    return await order_service.list_orders(
        session,
        ctx,
        statuses=_parse_statuses(status),
        date_from=from_,
        date_to=to,
        q=q,
        limit=limit,
        cursor=cursor,
    )


@router.get("/orders/{order_id}", response_model=OrderDetailOut, summary="Order detail")
async def get_order(order_id: uuid.UUID, ctx: TenantDep, session: SessionDep) -> OrderDetailOut:
    return await order_service.order_detail(session, ctx, order_id)


@router.post(
    "/orders/{order_id}/transition",
    response_model=OrderDetailOut,
    summary="Move an order to its next status",
)
async def transition(
    order_id: uuid.UUID, data: TransitionIn, ctx: TenantDep, session: SessionDep
) -> OrderDetailOut:
    return await order_service.transition_order(session, ctx, order_id, data.to_status, data.reason)


@router.post(
    "/orders/{order_id}/mark-paid", response_model=OrderDetailOut, summary="Mark a COD order paid"
)
async def mark_paid(order_id: uuid.UUID, ctx: TenantDep, session: SessionDep) -> OrderDetailOut:
    return await order_service.mark_cod_paid(session, ctx, order_id)


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryOut,
    summary="Orders by status, paid revenue and top items for a day",
    tags=["dashboard"],
)
async def dashboard_summary(
    ctx: TenantDep,
    session: SessionDep,
    date_: Annotated[
        date | None, Query(alias="date", description="YYYY-MM-DD, default today")
    ] = None,
) -> DashboardSummaryOut:
    return await dashboard_service.summary(session, ctx, date_)


@router.get(
    "/dashboard/sales", response_model=SalesOut, summary="Daily sales series", tags=["dashboard"]
)
async def dashboard_sales(
    ctx: TenantDep, session: SessionDep, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> SalesOut:
    return await dashboard_service.sales(session, ctx, days)
