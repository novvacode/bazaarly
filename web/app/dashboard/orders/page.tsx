"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/dashboard/shell";
import { OrderStatusBadge } from "@/components/order-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { formatPaise } from "@/lib/money";
import { formatDateTime, STATUS_LABEL } from "@/lib/orders";
import type { OrderListOut, OrderStatus } from "@/lib/types";

const STATUSES: OrderStatus[] = [
  "placed",
  "confirmed",
  "preparing",
  "ready",
  "out_for_delivery",
  "completed",
  "cancelled",
  "pending_payment",
];

const selectClass =
  "border-input dark:bg-input/30 h-9 rounded-md border bg-transparent px-3 text-sm";

function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function OrdersPage() {
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const query = useDebounced(q);

  const orders = useInfiniteQuery({
    queryKey: ["orders", "list", { status, from, to, query }],
    queryFn: ({ pageParam }) =>
      api<OrderListOut>("/orders", {
        query: { status, from, to, q: query, limit: 25, cursor: pageParam },
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });

  const rows = orders.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <PageHeader title="Orders" description="Search by order number, customer name or phone." />
      <Card className="mb-4 py-4">
        <CardContent className="grid gap-3 px-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="grid gap-1.5">
            <Label htmlFor="q">Search</Label>
            <div className="relative">
              <Search className="text-muted-foreground absolute top-2.5 left-2.5 size-4" />
              <Input
                id="q"
                className="pl-8"
                placeholder="#1042, Priya, 98765…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="status">Status</Label>
            <select
              id="status"
              className={selectClass}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="from">From</Label>
            <Input id="from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="to">To</Label>
            <Input id="to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
        </CardContent>
      </Card>

      <Card className="py-2">
        <CardContent className="px-2">
          {orders.isPending ? (
            <Skeleton className="h-64 w-full" />
          ) : orders.isError ? (
            <p className="text-destructive p-4">{errorMessage(orders.error)}</p>
          ) : rows.length === 0 ? (
            <p className="text-muted-foreground p-8 text-center text-sm">No orders match.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Order</TableHead>
                  <TableHead>Customer</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="hidden md:table-cell">Placed</TableHead>
                  <TableHead className="hidden sm:table-cell">Payment</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((o) => (
                  <TableRow key={o.id} className="relative">
                    <TableCell className="font-medium">
                      <Link
                        href={`/dashboard/orders/${o.id}`}
                        className="after:absolute after:inset-0"
                      >
                        #{o.code}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <div className="max-w-40 truncate">{o.customer_name}</div>
                      <div className="text-muted-foreground text-xs">{o.customer_phone}</div>
                    </TableCell>
                    <TableCell>
                      <OrderStatusBadge status={o.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground hidden md:table-cell">
                      {formatDateTime(o.created_at)}
                    </TableCell>
                    <TableCell className="hidden text-xs sm:table-cell">
                      {o.payment_method === "cod" ? "Cash" : "Online"} · {o.payment_status}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatPaise(o.total_paise)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {orders.hasNextPage && (
            <div className="flex justify-center p-3">
              <Button
                variant="outline"
                onClick={() => orders.fetchNextPage()}
                disabled={orders.isFetchingNextPage}
              >
                {orders.isFetchingNextPage ? "Loading…" : "Load more"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
