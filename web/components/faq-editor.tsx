"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Field } from "@/components/form-field";
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
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { FaqOut } from "@/lib/types";

export type FaqDraft = { id: string | null; question: string; answer: string };

export function FaqEditor({ draft, onClose }: { draft: FaqDraft | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState<FaqDraft | null>(draft);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [lastDraft, setLastDraft] = useState(draft);
  if (draft !== lastDraft) {
    setLastDraft(draft);
    setValue(draft);
    setErrors({});
  }

  const save = useMutation({
    mutationFn: (d: FaqDraft) =>
      d.id
        ? api<FaqOut>(`/faq/${d.id}`, {
            method: "PATCH",
            body: { question: d.question, answer: d.answer },
          })
        : api<FaqOut>("/faq", { body: { question: d.question, answer: d.answer } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["faq"] });
      toast.success("FAQ saved");
      onClose();
    },
    onError: (err) => {
      if (err instanceof ApiError && Object.keys(err.fields).length) setErrors(err.fields);
      else toast.error(errorMessage(err));
    },
  });

  return (
    <Dialog open={!!draft} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{draft?.id ? "Edit FAQ" : "New FAQ"}</DialogTitle>
          <DialogDescription>
            The AI assistant uses these answers word for word, so be specific.
          </DialogDescription>
        </DialogHeader>
        {value && (
          <form
            className="grid gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate(value);
            }}
          >
            <Field label="Question" htmlFor="faq-q" error={errors.question}>
              <Input
                id="faq-q"
                maxLength={300}
                value={value.question}
                onChange={(e) => setValue({ ...value, question: e.target.value })}
              />
            </Field>
            <Field label="Answer" htmlFor="faq-a" error={errors.answer}>
              <Textarea
                id="faq-a"
                rows={5}
                maxLength={2000}
                value={value.answer}
                onChange={(e) => setValue({ ...value, answer: e.target.value })}
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={
                  save.isPending || value.question.trim().length < 3 || !value.answer.trim()
                }
              >
                Save
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
