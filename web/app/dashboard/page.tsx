"use client";

import { useQuery } from "@tanstack/react-query";
import { Bell, BellOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { CopyButton } from "@/components/copy-button";
import { PageHeader } from "@/components/dashboard/shell";
import { OrderDetailView } from "@/components/orders/order-detail";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatPaise } from "@/lib/money";
import { minutesAgo } from "@/lib/orders";
import { storefrontUrl } from "@/lib/site";
import type { DashboardSummary, OrderListOut, OrderStatus, OrderSummary } from "@/lib/types";

const COLUMNS: { title: string; statuses: OrderStatus[] }[] = [
  { title: "New", statuses: ["placed"] },
  { title: "Confirmed", statuses: ["confirmed"] },
  { title: "Preparing", statuses: ["preparing"] },
  { title: "Ready / on the way", statuses: ["ready", "out_for_delivery"] },
];
const OPEN = COLUMNS.flatMap((c) => c.statuses).join(",");
const SOUND_KEY = "bz:board-sound";

function beep() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.4);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.4);
  } catch {
    // Audio blocked until the user interacts with the page; the toast still shows.
  }
}

function OrderCard({ order, onOpen }: { order: OrderSummary; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="bg-card hover:border-primary/50 focus-visible:ring-ring/50 w-full rounded-lg border p-3 text-left shadow-xs transition-colors outline-none focus-visible:ring-[3px]"
      data-testid="board-card"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold">#{order.code}</span>
        <span className="text-muted-foreground text-xs">{minutesAgo(order.created_at)}</span>
      </div>
      <p className="mt-1 truncate text-sm">{order.customer_name}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
        <Badge variant="outline" className="capitalize">
          {order.fulfillment_mode}
        </Badge>
        <span className="text-muted-foreground">
          {order.item_count} item{order.item_count === 1 ? "" : "s"}
        </span>
        <span className="ml-auto font-medium tabular-nums">{formatPaise(order.total_paise)}</span>
      </div>
    </button>
  );
}

function Stat({ label, value, text }: { label: string; value: string; text?: boolean }) {
  return (
    <Card className="gap-1 py-4">
      <CardHeader className="px-4">
        <CardDescription>{label}</CardDescription>
        <CardTitle className={text ? "line-clamp-2 text-base" : "text-2xl tabular-nums"}>
          {value}
        </CardTitle>
      </CardHeader>
    </Card>
  );
}

export default function OrderBoard() {
  const { tenant } = useAuth();
  const [openId, setOpenId] = useState<string | null>(null);
  const [sound, setSound] = useState(false);
  const seen = useRef<Set<string> | null>(null);

  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- restore a per-device preference
      setSound(window.localStorage.getItem(SOUND_KEY) === "on");
    } catch {
      // ignore
    }
  }, []);

  // Near-real-time board: refetch every 10 s (SPEC §14.2).
  const board = useQuery({
    queryKey: ["orders", "board"],
    queryFn: () => api<OrderListOut>("/orders", { query: { status: OPEN, limit: 100 } }),
    refetchInterval: 10_000,
    refetchIntervalInBackground: true,
  });
  const summary = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: () => api<DashboardSummary>("/dashboard/summary"),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    if (!board.data) return;
    const placed = board.data.items.filter((o) => o.status === "placed");
    if (seen.current === null) {
      seen.current = new Set(placed.map((o) => o.id));
      return;
    }
    const fresh = placed.filter((o) => !seen.current!.has(o.id));
    fresh.forEach((o) => seen.current!.add(o.id));
    if (fresh.length) {
      toast.success(
        fresh.length === 1
          ? `New order #${fresh[0].code} from ${fresh[0].customer_name}`
          : `${fresh.length} new orders`,
        { action: { label: "Open", onClick: () => setOpenId(fresh[0].id) } },
      );
      if (sound) beep();
    }
  }, [board.data, sound]);

  if (!tenant) return null;
  const orders = board.data?.items ?? [];
  const open = orders.length;
  const s = summary.data;

  return (
    <>
      <PageHeader
        title="Order board"
        description="Updates every 10 seconds. Tap an order to move it along."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const next = !sound;
              setSound(next);
              try {
                window.localStorage.setItem(SOUND_KEY, next ? "on" : "off");
              } catch {
                // ignore
              }
              if (next) beep();
            }}
          >
            {sound ? <Bell /> : <BellOff />} Sound {sound ? "on" : "off"}
          </Button>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Orders today" value={s ? String(s.orders_total) : "–"} />
        <Stat label="Paid revenue today" value={s ? formatPaise(s.revenue_paise) : "–"} />
        <Stat label="Open orders" value={board.data ? String(open) : "–"} />
        <Stat label="Top item today" value={s?.top_items[0]?.name ?? "–"} text />
      </div>

      {board.isPending ? (
        <Skeleton className="h-72 w-full" />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {COLUMNS.map((col) => {
            const list = orders
              .filter((o) => col.statuses.includes(o.status))
              .sort((a, b) => a.created_at.localeCompare(b.created_at));
            return (
              <section
                key={col.title}
                className="bg-muted/40 rounded-xl border p-3"
                aria-label={col.title}
              >
                <h2 className="mb-3 flex items-center justify-between text-sm font-semibold">
                  {col.title}
                  <span className="text-muted-foreground">{list.length}</span>
                </h2>
                <div className="grid gap-2">
                  {list.length === 0 && (
                    <p className="text-muted-foreground py-4 text-center text-xs">Nothing here</p>
                  )}
                  {list.map((o) => (
                    <OrderCard key={o.id} order={o} onOpen={() => setOpenId(o.id)} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}

      {board.data && open === 0 && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>No open orders</CardTitle>
            <CardDescription>Share your storefront to get orders flowing.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3">
            <code className="bg-muted rounded px-2 py-1 text-sm break-all">
              {storefrontUrl(tenant.slug)}
            </code>
            <CopyButton value={storefrontUrl(tenant.slug)} label="Copy link" />
          </CardContent>
        </Card>
      )}

      <Sheet open={!!openId} onOpenChange={(o) => !o && setOpenId(null)}>
        <SheetContent className="overflow-y-auto p-5">
          <SheetTitle className="sr-only">Order details</SheetTitle>
          {openId && <OrderDetailView orderId={openId} />}
        </SheetContent>
      </Sheet>
    </>
  );
}
