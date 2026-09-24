"use client";

import { useInfiniteQuery, useMutation } from "@tanstack/react-query";
import { MessageSquarePlus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/dashboard/shell";
import { FaqEditor, type FaqDraft } from "@/components/faq-editor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/orders";
import type { AssistantLogList, FaqOut } from "@/lib/types";

export default function AssistantPage() {
  const [filter, setFilter] = useState<"all" | "unanswered">("unanswered");
  const [draft, setDraft] = useState<FaqDraft | null>(null);

  const logs = useInfiniteQuery({
    queryKey: ["assistant", "logs", filter],
    queryFn: ({ pageParam }) =>
      api<AssistantLogList>("/assistant/logs", {
        query: {
          answered: filter === "unanswered" ? false : undefined,
          cursor: pageParam,
          limit: 30,
        },
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });

  const reindex = useMutation({
    mutationFn: () => api<void>("/assistant/reindex", { method: "POST" }),
    onSuccess: () => toast.success("Rebuilding the assistant's knowledge. This takes a minute."),
    onError: (err) => toast.error(errorMessage(err)),
  });

  const toFaq = useMutation({
    mutationFn: (logId: string) =>
      api<Pick<FaqOut, "question" | "answer">>(`/assistant/logs/${logId}/to-faq`, {
        method: "POST",
      }),
    onSuccess: (d) => setDraft({ id: null, question: d.question, answer: d.answer }),
    onError: (err) => toast.error(errorMessage(err)),
  });

  const rows = logs.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <PageHeader
        title="Assistant"
        description="What customers asked your storefront assistant. Turn unanswered questions into FAQs so it can answer next time."
        actions={
          <Button variant="outline" onClick={() => reindex.mutate()} disabled={reindex.isPending}>
            <RefreshCw /> Rebuild knowledge
          </Button>
        }
      />
      <Tabs value={filter} onValueChange={(v) => setFilter(v as typeof filter)} className="mb-4">
        <TabsList>
          <TabsTrigger value="unanswered">Unanswered</TabsTrigger>
          <TabsTrigger value="all">All questions</TabsTrigger>
        </TabsList>
      </Tabs>

      {logs.isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : logs.isError ? (
        <p className="text-destructive">{errorMessage(logs.error)}</p>
      ) : rows.length === 0 ? (
        <Card>
          <CardContent className="text-muted-foreground py-10 text-center text-sm">
            {filter === "unanswered"
              ? "Nothing unanswered. Nice!"
              : "No questions yet. Customers can ask from the chat button on your storefront."}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {rows.map((log) => (
            <Card key={log.id} className="gap-2 py-4">
              <CardContent className="grid gap-2 px-4">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">&ldquo;{log.question}&rdquo;</p>
                  <Badge variant={log.answered ? "success" : "outline"}>
                    {log.answered ? "Answered" : "Not answered"}
                  </Badge>
                  <span className="text-muted-foreground ml-auto text-xs">
                    {formatDateTime(log.created_at)}
                  </span>
                </div>
                <p className="text-muted-foreground text-sm">{log.answer}</p>
                {!log.answered && (
                  <div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => toFaq.mutate(log.id)}
                      disabled={toFaq.isPending}
                    >
                      <MessageSquarePlus /> Turn into FAQ
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
          {logs.hasNextPage && (
            <Button
              variant="outline"
              className="justify-self-center"
              onClick={() => logs.fetchNextPage()}
              disabled={logs.isFetchingNextPage}
            >
              Load more
            </Button>
          )}
        </div>
      )}
      <FaqEditor draft={draft} onClose={() => setDraft(null)} />
    </>
  );
}
