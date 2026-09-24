"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/dashboard/shell";
import { FaqEditor, type FaqDraft } from "@/components/faq-editor";
import { SortableList } from "@/components/sortable-list";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, errorMessage } from "@/lib/api";
import type { FaqOut } from "@/lib/types";

export default function FaqPage() {
  const queryClient = useQueryClient();
  const faq = useQuery({ queryKey: ["faq"], queryFn: () => api<FaqOut[]>("/faq") });
  const [draft, setDraft] = useState<FaqDraft | null>(null);

  const reorder = useMutation({
    mutationFn: (ids: string[]) => api<void>("/faq/reorder", { body: { ids } }),
    onError: (err) => {
      toast.error(errorMessage(err));
      void queryClient.invalidateQueries({ queryKey: ["faq"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/faq/${id}`, { method: "DELETE" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["faq"] }),
    onError: (err) => toast.error(errorMessage(err)),
  });

  return (
    <>
      <PageHeader
        title="FAQ"
        description="Answers to common questions. The storefront assistant answers from these."
        actions={
          <Button onClick={() => setDraft({ id: null, question: "", answer: "" })}>
            <Plus /> Add question
          </Button>
        }
      />
      {faq.isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : faq.isError ? (
        <p className="text-destructive">{errorMessage(faq.error)}</p>
      ) : faq.data.length === 0 ? (
        <Card>
          <CardContent className="text-muted-foreground py-10 text-center text-sm">
            No questions yet. Add things customers often ask: delivery areas, eggless options,
            advance notice for custom orders.
          </CardContent>
        </Card>
      ) : (
        <SortableList
          items={faq.data}
          className="grid gap-3"
          onReorder={(ordered) => {
            queryClient.setQueryData(["faq"], ordered);
            reorder.mutate(ordered.map((f) => f.id));
          }}
          renderItem={(entry, handle) => (
            <Card className="gap-2 py-3">
              <CardContent className="flex items-start gap-2 px-3">
                {handle}
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{entry.question}</p>
                  <p className="text-muted-foreground mt-1 text-sm whitespace-pre-line">
                    {entry.answer}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Edit"
                  onClick={() => setDraft({ ...entry })}
                >
                  <Pencil />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Delete"
                  onClick={() => remove.mutate(entry.id)}
                >
                  <Trash2 />
                </Button>
              </CardContent>
            </Card>
          )}
        />
      )}
      <FaqEditor draft={draft} onClose={() => setDraft(null)} />
    </>
  );
}
