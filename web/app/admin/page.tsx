"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RotateCcw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
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
import { useSession } from "@/lib/auth";
import { formatDateTime } from "@/lib/orders";
import type { AdminTenant, DeadJob, JobStats } from "@/lib/types";

function Stat({ label, value, tone }: { label: string; value: number; tone?: "bad" }) {
  return (
    <Card className="gap-1 py-4">
      <CardHeader className="px-4">
        <CardDescription>{label}</CardDescription>
        <CardTitle
          className={tone === "bad" && value > 0 ? "text-destructive text-2xl" : "text-2xl"}
        >
          {value.toLocaleString("en-IN")}
        </CardTitle>
      </CardHeader>
    </Card>
  );
}

function DeadJobRow({ job }: { job: DeadJob }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["admin"] });
  };
  const retry = useMutation({
    mutationFn: () => api<void>(`/admin/jobs/dead/${job.entry_id}/retry`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Re-enqueued");
      refresh();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: () => api<void>(`/admin/jobs/dead/${job.entry_id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Deleted");
      refresh();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <li className="rounded-lg border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <code className="font-medium">{job.type}</code>
        <Badge variant="outline">attempt {job.attempt + 1}</Badge>
        <span className="text-destructive">
          {job.error_type}: {job.error}
        </span>
        <span className="text-muted-foreground ml-auto text-xs">
          {job.failed_at ? formatDateTime(job.failed_at) : ""}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => retry.mutate()}
          disabled={retry.isPending}
        >
          <RotateCcw /> Retry
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => remove.mutate()}
          disabled={remove.isPending}
        >
          <Trash2 /> Delete
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen((o) => !o)}>
          {open ? "Hide details" : "Details"}
        </Button>
      </div>
      {open && (
        <pre className="bg-muted mt-2 max-h-64 overflow-auto rounded p-2 text-xs whitespace-pre-wrap">
          {JSON.stringify(job.payload, null, 2)}
          {"\n\n"}
          {job.traceback}
        </pre>
      )}
    </li>
  );
}

export default function AdminPage() {
  const { status, user } = useSession();
  const router = useRouter();
  const isAdmin = status === "authenticated" && user?.is_platform_admin;

  useEffect(() => {
    if (status === "anonymous") router.replace("/login?next=/admin");
  }, [status, router]);

  const stats = useQuery({
    queryKey: ["admin", "stats"],
    queryFn: () => api<JobStats>("/admin/jobs/stats"),
    enabled: !!isAdmin,
    refetchInterval: 10_000,
  });
  const dead = useQuery({
    queryKey: ["admin", "dead"],
    queryFn: () => api<DeadJob[]>("/admin/jobs/dead"),
    enabled: !!isAdmin,
    refetchInterval: 30_000,
  });
  const tenants = useQuery({
    queryKey: ["admin", "tenants"],
    queryFn: () => api<AdminTenant[]>("/admin/tenants"),
    enabled: !!isAdmin,
  });

  if (status !== "authenticated") return <Skeleton className="h-64 w-full" />;
  if (!isAdmin) {
    return (
      <div className="py-20 text-center">
        <h1 className="text-xl font-semibold">Page not found</h1>
        <Button asChild variant="link">
          <Link href="/dashboard">Go to dashboard</Link>
        </Button>
      </div>
    );
  }

  const s = stats.data;
  return (
    <div className="grid gap-6">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="icon" aria-label="Back to dashboard">
          <Link href="/dashboard">
            <ArrowLeft />
          </Link>
        </Button>
        <h1 className="text-2xl font-bold">Platform admin</h1>
      </div>

      <section className="grid gap-3">
        <h2 className="text-lg font-semibold">Job queue</h2>
        {!s ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="In stream" value={s.stream_length} />
              <Stat label="Pending (claimed)" value={s.pending} />
              <Stat label="Delayed / retrying" value={s.delayed} />
              <Stat label="Dead-lettered" value={s.dead} tone="bad" />
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <Card className="gap-2">
                <CardHeader>
                  <CardTitle className="text-base">Consumers</CardTitle>
                </CardHeader>
                <CardContent className="text-sm">
                  {s.consumers.length === 0 ? (
                    <p className="text-muted-foreground">No consumers have connected yet.</p>
                  ) : (
                    <ul className="grid gap-1">
                      {s.consumers.map((c) => (
                        <li key={c.name} className="flex justify-between gap-2">
                          <code className="truncate">{c.name}</code>
                          <span className="text-muted-foreground tabular-nums">
                            {c.pending} pending · idle {Math.round(c.idle_ms / 1000)} s
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
              <Card className="gap-2">
                <CardHeader>
                  <CardTitle className="text-base">Outcomes</CardTitle>
                </CardHeader>
                <CardContent className="text-sm">
                  {Object.keys(s.counters).length === 0 ? (
                    <p className="text-muted-foreground">No jobs processed yet.</p>
                  ) : (
                    <ul className="grid gap-1">
                      {Object.entries(s.counters).map(([k, v]) => (
                        <li key={k} className="flex justify-between gap-2">
                          <code className="truncate">{k}</code>
                          <span className="tabular-nums">{v}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </div>
          </>
        )}
      </section>

      <section className="grid gap-3">
        <h2 className="text-lg font-semibold">Dead-letter queue</h2>
        {dead.isPending ? (
          <Skeleton className="h-20 w-full" />
        ) : dead.data?.length ? (
          <ul className="grid gap-2">
            {dead.data.map((job) => (
              <DeadJobRow key={job.entry_id} job={job} />
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">Empty. Nothing has failed permanently.</p>
        )}
      </section>

      <section className="grid gap-3">
        <h2 className="text-lg font-semibold">Tenants</h2>
        <Card className="py-2">
          <CardContent className="px-2">
            {tenants.isPending ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Business</TableHead>
                    <TableHead>Members</TableHead>
                    <TableHead>Orders (7 days)</TableHead>
                    <TableHead>Orders (all)</TableHead>
                    <TableHead>Open</TableHead>
                    <TableHead>Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tenants.data?.map((t) => (
                    <TableRow key={t.id}>
                      <TableCell>
                        <a
                          href={`/b/${t.slug}`}
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium hover:underline"
                        >
                          {t.name}
                        </a>
                        <div className="text-muted-foreground text-xs">{t.email}</div>
                      </TableCell>
                      <TableCell className="tabular-nums">{t.members}</TableCell>
                      <TableCell className="tabular-nums">{t.orders_last_7_days}</TableCell>
                      <TableCell className="tabular-nums">{t.orders}</TableCell>
                      <TableCell>{t.accepts_orders ? "Yes" : "Closed"}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDateTime(t.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
