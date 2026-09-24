"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, MapPin, Phone, StickyNote } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { OrderStatusBadge } from "@/components/order-status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, errorMessage } from "@/lib/api";
import { formatPaise } from "@/lib/money";
import { ACTION_LABEL, formatDateTime, STATUS_LABEL } from "@/lib/orders";
import type { OrderDetail, OrderStatus } from "@/lib/types";

export function useOrder(orderId: string | null) {
  return useQuery({
    queryKey: ["order", orderId],
    queryFn: () => api<OrderDetail>(`/orders/${orderId}`),
    enabled: !!orderId,
  });
}

/** Details, timeline and the actions the API says are allowed (never hardcoded here). */
export function OrderDetailView({ orderId }: { orderId: string }) {
  const queryClient = useQueryClient();
  const order = useOrder(orderId);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState("");

  const onUpdated = (o: OrderDetail) => {
    queryClient.setQueryData(["order", orderId], o);
    void queryClient.invalidateQueries({ queryKey: ["orders"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const move = useMutation({
    mutationFn: ({ to, why }: { to: OrderStatus; why?: string }) =>
      api<OrderDetail>(`/orders/${orderId}/transition`, {
        body: { to_status: to, reason: why || null },
      }),
    onSuccess: (o) => {
      onUpdated(o);
      setCancelOpen(false);
      setReason("");
      toast.success(`#${o.code} → ${STATUS_LABEL[o.status]}`);
    },
    onError: (err) => {
      toast.error(errorMessage(err));
      void order.refetch();
    },
  });

  const markPaid = useMutation({
    mutationFn: () => api<OrderDetail>(`/orders/${orderId}/mark-paid`, { method: "POST" }),
    onSuccess: (o) => {
      onUpdated(o);
      toast.success("Marked as paid");
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  if (order.isPending) return <Skeleton className="h-96 w-full" />;
  if (order.isError) return <p className="text-destructive">{errorMessage(order.error)}</p>;

  const o = order.data;
  const forward = o.allowed_transitions.filter((s) => s !== "cancelled");
  const canCancel = o.allowed_transitions.includes("cancelled");

  return (
    <div className="grid gap-5" data-testid="order-detail">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-xl font-bold">Order #{o.code}</h2>
        <OrderStatusBadge status={o.status} />
        <Badge variant="outline" className="capitalize">
          {o.fulfillment_mode}
        </Badge>
        <Badge variant={o.payment_status === "paid" ? "success" : "outline"}>
          {o.payment_method === "cod" ? "Cash" : "Online"} · {o.payment_status}
        </Badge>
      </div>

      {o.refund_required && (
        <Alert variant="warning">
          <AlertTitle>Refund needed</AlertTitle>
          <AlertDescription>
            This paid order was cancelled. Refund the customer manually from your Razorpay
            dashboard.
          </AlertDescription>
        </Alert>
      )}

      {(forward.length > 0 ||
        canCancel ||
        (o.payment_method === "cod" &&
          o.payment_status !== "paid" &&
          o.status !== "cancelled")) && (
        <div className="flex flex-wrap gap-2">
          {forward.map((to) => (
            <Button key={to} disabled={move.isPending} onClick={() => move.mutate({ to })}>
              {ACTION_LABEL[to]}
            </Button>
          ))}
          {o.payment_method === "cod" &&
            o.payment_status !== "paid" &&
            o.status !== "cancelled" && (
              <Button
                variant="outline"
                disabled={markPaid.isPending}
                onClick={() => markPaid.mutate()}
              >
                Mark paid
              </Button>
            )}
          {canCancel && (
            <Button
              variant="ghost"
              className="text-destructive"
              onClick={() => setCancelOpen(true)}
            >
              Cancel order
            </Button>
          )}
        </div>
      )}

      <section className="grid gap-1 text-sm">
        <p className="font-medium">{o.customer_name}</p>
        <a href={`tel:${o.customer_phone}`} className="flex items-center gap-1.5 hover:underline">
          <Phone className="size-3.5" /> {o.customer_phone}
        </a>
        {o.customer_email && <p className="text-muted-foreground">{o.customer_email}</p>}
        {o.fulfillment_mode === "delivery" && (
          <p className="flex items-start gap-1.5">
            <MapPin className="mt-0.5 size-3.5 shrink-0" />
            <span>
              {o.delivery_address}
              {o.delivery_area && ` · ${o.delivery_area}`}
            </span>
          </p>
        )}
        {o.notes && (
          <p className="bg-muted mt-1 flex items-start gap-1.5 rounded-md p-2">
            <StickyNote className="mt-0.5 size-3.5 shrink-0" /> {o.notes}
          </p>
        )}
      </section>

      <section className="grid gap-2 text-sm">
        <h3 className="font-semibold">Items</h3>
        {o.items.map((i, idx) => (
          <div key={idx} className="flex justify-between gap-3">
            <span>
              {i.quantity} × {i.name}
              <span className="text-muted-foreground"> @ {formatPaise(i.unit_price_paise)}</span>
            </span>
            <span className="tabular-nums">{formatPaise(i.line_total_paise)}</span>
          </div>
        ))}
        <div className="grid gap-1 border-t pt-2">
          <div className="text-muted-foreground flex justify-between">
            <span>Subtotal</span>
            <span className="tabular-nums">{formatPaise(o.totals.subtotal_paise)}</span>
          </div>
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
        </div>
      </section>

      <section className="grid gap-2 text-sm">
        <h3 className="font-semibold">Timeline</h3>
        <ol className="grid gap-1.5">
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
        <a
          href={`/o/${o.public_token}`}
          target="_blank"
          rel="noreferrer"
          className="text-primary inline-flex items-center gap-1 text-xs hover:underline"
        >
          Customer tracking page <ExternalLink className="size-3" />
        </a>
      </section>

      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel order #{o.code}?</DialogTitle>
            <DialogDescription>
              The customer will see this on their tracking page
              {o.customer_email ? " and get an email" : ""}.
            </DialogDescription>
          </DialogHeader>
          <Input
            aria-label="Reason (optional)"
            placeholder="Reason (optional), e.g. out of stock"
            maxLength={300}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelOpen(false)}>
              Keep order
            </Button>
            <Button
              variant="destructive"
              disabled={move.isPending}
              onClick={() => move.mutate({ to: "cancelled", why: reason })}
            >
              Cancel order
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
