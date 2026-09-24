"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";

import { PageHeader } from "@/components/dashboard/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import type { SalesOut } from "@/lib/types";

const dayFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" });
/** Axis ticks in rupees: ₹800, ₹8k, ₹1.2L (lakh). Input is paise. */
function rupeeTick(paise: number) {
  const r = paise / 100;
  if (r >= 100_000) return `₹${+(r / 100_000).toFixed(1)}L`;
  if (r >= 1_000) return `₹${+(r / 1_000).toFixed(1)}k`;
  return `₹${r}`;
}

type Point = { date: string; label: string; orders: number; revenue: number };

function label(date: string) {
  return dayFmt.format(new Date(`${date}T00:00:00`));
}

function ChartTooltip({
  active,
  payload,
  kind,
}: TooltipContentProps<number, string> & { kind: "revenue" | "orders" }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as Point;
  return (
    <div className="bg-popover text-popover-foreground rounded-md border px-3 py-2 text-xs shadow-md">
      <p className="font-medium">{p.label}</p>
      <p className="text-muted-foreground mt-0.5 flex items-center gap-1.5">
        <span className="bg-chart-1 inline-block size-2 rounded-sm" aria-hidden />
        {kind === "revenue"
          ? formatPaise(p.revenue)
          : `${p.orders} order${p.orders === 1 ? "" : "s"}`}
      </p>
    </div>
  );
}

function ColumnChart({ data, kind }: { data: Point[]; kind: "revenue" | "orders" }) {
  const key = kind === "revenue" ? "revenue" : "orders";
  return (
    <div
      className="h-56 w-full"
      role="img"
      aria-label={`Daily ${kind} for the last ${data.length} days`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 12, right: 4, bottom: 0, left: 4 }} barCategoryGap={2}>
          <CartesianGrid vertical={false} stroke="var(--color-border)" strokeWidth={1} />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={{ stroke: "var(--color-border)" }}
            tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis
            width={kind === "revenue" ? 56 : 32}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
            tick={{ fill: "var(--color-muted-foreground)", fontSize: 11 }}
            tickFormatter={(v: number) => (kind === "revenue" ? rupeeTick(v) : String(v))}
            domain={
              kind === "orders" ? [0, (max: number) => Math.max(4, Math.ceil(max))] : [0, "auto"]
            }
            tickCount={5}
          />
          <Tooltip
            cursor={{ fill: "var(--color-muted)", opacity: 0.6 }}
            content={(props) => (
              <ChartTooltip {...(props as TooltipContentProps<number, string>)} kind={kind} />
            )}
          />
          <Bar dataKey={key} fill="var(--color-chart-1)" radius={[4, 4, 0, 0]} maxBarSize={24} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="gap-1 py-4">
      <CardHeader className="px-4">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl tabular-nums">{value}</CardTitle>
        {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
      </CardHeader>
    </Card>
  );
}

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const [asTable, setAsTable] = useState(false);
  const sales = useQuery({
    queryKey: ["dashboard", "sales", days],
    queryFn: () => api<SalesOut>("/dashboard/sales", { query: { days } }),
  });

  const points: Point[] =
    sales.data?.series.map((p) => ({
      date: p.date,
      label: label(p.date),
      orders: p.orders,
      revenue: p.revenue_paise,
    })) ?? [];
  const revenue = points.reduce((n, p) => n + p.revenue, 0);
  const orders = points.reduce((n, p) => n + p.orders, 0);
  const top = sales.data?.top_items ?? [];
  const maxQty = Math.max(1, ...top.map((t) => t.quantity));

  return (
    <>
      <PageHeader
        title="Analytics"
        description={
          sales.data ? `Times in ${sales.data.timezone}. Cancelled orders excluded.` : undefined
        }
        actions={
          <>
            <div className="bg-muted inline-flex rounded-md p-0.5" role="group" aria-label="Range">
              {[7, 30, 90].map((d) => (
                <Button
                  key={d}
                  size="sm"
                  variant={d === days ? "outline" : "ghost"}
                  aria-pressed={d === days}
                  onClick={() => setDays(d)}
                >
                  {d} days
                </Button>
              ))}
            </div>
            <Button size="sm" variant="ghost" onClick={() => setAsTable((v) => !v)}>
              {asTable ? "Show charts" : "Show table"}
            </Button>
          </>
        }
      />

      {sales.isPending ? (
        <Skeleton className="h-96 w-full" />
      ) : sales.isError ? (
        <p className="text-destructive">{errorMessage(sales.error)}</p>
      ) : (
        <div className="grid gap-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <Stat label="Paid revenue" value={formatPaise(revenue)} hint={`Last ${days} days`} />
            <Stat
              label="Orders"
              value={orders.toLocaleString("en-IN")}
              hint={`Last ${days} days`}
            />
            <Stat
              label="Average order"
              value={orders ? formatPaise(Math.round(revenue / orders)) : "–"}
              hint="Paid revenue ÷ orders"
            />
          </div>

          {asTable ? (
            <Card>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead className="text-right">Orders</TableHead>
                      <TableHead className="text-right">Paid revenue</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {[...points].reverse().map((p) => (
                      <TableRow key={p.date}>
                        <TableCell>{p.label}</TableCell>
                        <TableCell className="text-right tabular-nums">{p.orders}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatPaise(p.revenue)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              <Card className="gap-2">
                <CardHeader>
                  <CardTitle className="text-base">Paid revenue per day</CardTitle>
                </CardHeader>
                <CardContent className="px-3">
                  <ColumnChart data={points} kind="revenue" />
                </CardContent>
              </Card>
              <Card className="gap-2">
                <CardHeader>
                  <CardTitle className="text-base">Orders per day</CardTitle>
                </CardHeader>
                <CardContent className="px-3">
                  <ColumnChart data={points} kind="orders" />
                </CardContent>
              </Card>
            </div>
          )}

          <Card className="gap-3">
            <CardHeader>
              <CardTitle className="text-base">Top items</CardTitle>
              <CardDescription>By quantity sold, last {days} days</CardDescription>
            </CardHeader>
            <CardContent>
              {top.length === 0 ? (
                <p className="text-muted-foreground text-sm">No sales in this period.</p>
              ) : (
                <ol className="grid gap-3">
                  {top.map((t) => (
                    <li key={t.name} className="grid gap-1 text-sm">
                      <div className="flex justify-between gap-3">
                        <span className="truncate">{t.name}</span>
                        <span className="text-muted-foreground shrink-0 tabular-nums">
                          {t.quantity} sold · {formatPaise(t.revenue_paise)}
                        </span>
                      </div>
                      <div className="bg-muted h-2 rounded-full" aria-hidden>
                        <div
                          className="bg-chart-1 h-2 rounded-full"
                          style={{ width: `${(t.quantity / maxQty) * 100}%` }}
                        />
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}
