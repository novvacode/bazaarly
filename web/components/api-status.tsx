"use client";

import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";

type Ready = { status: "ok" | "degraded"; checks: Record<string, string> };

async function fetchReady(): Promise<Ready> {
  const res = await fetch("/api/v1/health/ready", { cache: "no-store" });
  if (res.status !== 200 && res.status !== 503) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as Ready;
}

export function ApiStatus() {
  const { data, isError, isPending } = useQuery({
    queryKey: ["health-ready"],
    queryFn: fetchReady,
    refetchInterval: 30_000,
  });

  if (isPending) return <Badge variant="secondary">Checking API…</Badge>;
  if (isError || !data) return <Badge variant="destructive">API unreachable</Badge>;
  return (
    <span className="inline-flex items-center gap-2" data-testid="api-status">
      <Badge variant={data.status === "ok" ? "success" : "destructive"}>
        API {data.status === "ok" ? "ready" : "degraded"}
      </Badge>
      {Object.entries(data.checks).map(([name, value]) => (
        <span key={name} className="text-muted-foreground text-xs">
          {name}: {value}
        </span>
      ))}
    </span>
  );
}
