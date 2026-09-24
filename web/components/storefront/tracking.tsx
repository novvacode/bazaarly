"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Phone } from "lucide-react";
import Link from "next/link";

import { OrderStatusBadge } from "@/components/order-status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { formatPaise } from "@/lib/money";
import { formatDateTime, STATUS_LABEL } from "@/lib/orders";
import type { OrderStatus, PublicOrderOut } from "@/lib/types";
import { cn } from "@/lib/utils";

import { CompletePayment } from "./complete-payment";

const STEPS: Record<"pickup" | "delivery", OrderStatus[]> = {
  pickup: ["placed", "confirmed", "preparing", "ready", "completed"],
  delivery: ["placed", "confirmed", "preparing", "out_for_delivery", "completed"],
};

const HEADLINE: Partial<Record<OrderStatus, string>> = {
  pending_payment: "Waiting for your payment",
  placed: "Order received — waiting for the store to confirm",
  confirmed: "Confirmed by the store",
  preparing: "Being prepared",
  ready: "Ready for pickup",
  out_for_delivery: "On the way",
  completed: "Completed — enjoy!",
  cancelled: "This order was cancelled",
};

function Progress({ order }: { order: PublicOrderOut }) {
  const steps = STEPS[order.fulfillment_mode];
  const current = steps.indexOf(order.status);
  return (
    <ol className="grid gap-3" aria-label="Order progress">
      {steps.map((step, i) => {
        const done = current >= i;
        return (
          <li key={step} className="flex items-center gap-3">
            <span
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-full border text-xs",
                done
                  ? "bg-primary border-primary text-primary-foreground"
                  : "text-muted-foreground",
              )}
              aria-hidden
            >
              {done ? <Check className="size-3.5" /> : i + 1}
            </span>
            <span className={cn("text-sm", done ? "font-medium" : "text-muted-foreground")}>
              {STATUS_LABEL[step]}
            </span>
            <span className="sr-only">{done ? "done" : "pending"}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function OrderTracking({ token }: { token: string }) {
  const order = useQuery({
    queryKey: ["tracking", token],
    queryFn: () => api<PublicOrderOut>(`/public/orders/${token}`, { auth: false }),
    // Poll every 15 s until the order reaches a terminal state (SPEC §14.1).
    refetchInterval: (q) => (q.state.data?.is_terminal ? false : 15_000),
    refetchOnWindowFocus: true,
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });

  if (order.isPending) {
    return (
      <div className="mx-auto grid max-w-xl gap-4 p-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (order.isError) {
    return (
      <div className="mx-auto max-w-xl p-6">
        <Alert variant="destructive">
          <AlertTitle>Order not found</AlertTitle>
          <AlertDescription>Check the link you were sent.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const o = order.data;
  return (
    <div className="mx-auto grid w-full max-w-xl gap-4 px-4 py-6">
      <div>
        <p className="text-muted-foreground text-sm">
          {o.business.name} · Order #{o.code}
        </p>
        <h1 className="mt-1 text-2xl font-bold" data-testid="tracking-headline">
          {HEADLINE[o.status]}
        </h1>
        <div className="mt-2 flex items-center gap-2">
          <OrderStatusBadge status={o.status} />
          {!o.is_terminal && (
            <span className="text-muted-foreground text-xs">Updates automatically</span>
          )}
        </div>
      </div>

      {o.can_pay && <CompletePayment token={token} order={o} onPaid={() => order.refetch()} />}

      {o.status !== "cancelled" && o.status !== "pending_payment" && (
        <Card>
          <CardContent>
            <Progress order={o} />
          </CardContent>
        </Card>
      )}

      <Card className="gap-3">
        <CardHeader>
          <CardTitle className="text-base">Items</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm">
          {o.items.map((i, idx) => (
            <div key={idx} className="flex justify-between gap-3">
              <span>
                {i.quantity} × {i.name}
              </span>
              <span className="tabular-nums">{formatPaise(i.line_total_paise)}</span>
            </div>
          ))}
          <div className="mt-2 grid gap-1 border-t pt-2">
            {o.totals.delivery_fee_paise > 0 && (
              <div className="text-muted-foreground flex justify-between">
                <span>Delivery</span>
                <span className="tabular-nums">{formatPaise(o.totals.delivery_fee_paise)}</span>
              </div>
            )}
            <div className="flex justify-between font-semibold">
              <span>Total</span>
              <span className="tabular-nums">{formatPaise(o.totals.total_paise)}</span>
            </div>
            <p className="text-muted-foreground text-xs">
              {o.payment_method === "cod"
                ? o.payment_status === "paid"
                  ? "Paid"
                  : o.fulfillment_mode === "delivery"
                    ? "Pay on delivery"
                    : "Pay at pickup"
                : o.payment_status === "paid"
                  ? "Paid online"
                  : "Online payment pending"}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card className="gap-3">
        <CardHeader>
          <CardTitle className="text-base">Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="grid gap-2 text-sm">
            {o.timeline.map((e, idx) => (
              <li key={idx} className="flex justify-between gap-3">
                <span>
                  {STATUS_LABEL[e.to_status]}
                  {e.note && <span className="text-muted-foreground"> — {e.note}</span>}
                </span>
                <span className="text-muted-foreground tabular-nums">{formatDateTime(e.at)}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        {o.business.phone && (
          <Button asChild variant="outline">
            <a href={`tel:${o.business.phone}`}>
              <Phone /> Call {o.business.name}
            </a>
          </Button>
        )}
        <Button asChild variant="ghost">
          <Link href={`/b/${o.business.slug}`}>Order again</Link>
        </Button>
      </div>
    </div>
  );
}
