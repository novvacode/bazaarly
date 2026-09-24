"use client";

import { useMutation } from "@tanstack/react-query";
import { MessageCircle, SendHorizontal, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { api, ApiError } from "@/lib/api";
import type { AssistantReply } from "@/lib/types";
import { cn } from "@/lib/utils";

import { useCart } from "./cart";

type Message =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; answered: boolean; sources: AssistantReply["sources"] };

const SUGGESTIONS = ["What's eggless?", "Do you deliver to my area?", "What are your timings?"];

function sessionId(slug: string): string {
  const key = `bz:chat-session:${slug}`;
  try {
    const existing = window.sessionStorage.getItem(key);
    if (existing) return existing;
    const id = crypto.randomUUID().replace(/-/g, "");
    window.sessionStorage.setItem(key, id);
    return id;
  } catch {
    return crypto.randomUUID().replace(/-/g, "");
  }
}

/** Storefront assistant (SPEC §14.1): answers only from this store's menu, FAQ and details. */
export function ChatWidget({ slug, businessName }: { slug: string; businessName: string }) {
  const cart = useCart();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, open]);

  const send = useMutation({
    mutationFn: (message: string) =>
      api<AssistantReply>(`/public/b/${slug}/assistant`, {
        auth: false,
        body: { session_id: sessionId(slug), message },
      }),
    onMutate: (message) => setMessages((m) => [...m, { role: "user", text: message }]),
    onSuccess: (reply) =>
      setMessages((m) => [
        ...m,
        { role: "assistant", text: reply.answer, answered: reply.answered, sources: reply.sources },
      ]),
    onError: (err) =>
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text:
            err instanceof ApiError && err.status === 429
              ? "You're asking quickly! Please wait a minute and try again."
              : "Sorry, I couldn't answer just now. Please try again.",
          answered: false,
          sources: [],
        },
      ]),
  });

  function submit(text: string) {
    const message = text.trim().slice(0, 500);
    if (!message || send.isPending) return;
    setInput("");
    send.mutate(message);
  }

  const lifted = cart.hydrated && cart.count > 0;
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          size="lg"
          variant="secondary"
          className={cn(
            "fixed right-4 z-40 h-12 rounded-full border shadow-lg",
            lifted ? "bottom-20 sm:bottom-24" : "bottom-4",
          )}
          aria-label="Ask a question"
        >
          <MessageCircle /> Ask
        </Button>
      </SheetTrigger>
      <SheetContent side="bottom" className="mx-auto h-[80dvh] max-w-2xl gap-0 sm:h-[70dvh]">
        <SheetHeader className="border-b">
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="text-primary size-4" /> Ask {businessName}
          </SheetTitle>
          <SheetDescription>
            Answers come only from this store&apos;s menu and FAQ. For allergies, please confirm
            with the store.
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-4 py-3" aria-live="polite" data-testid="chat-log">
          {messages.length === 0 && (
            <div className="flex flex-wrap gap-2 pt-2">
              {SUGGESTIONS.map((s) => (
                <Button key={s} variant="outline" size="sm" onClick={() => submit(s)}>
                  {s}
                </Button>
              ))}
            </div>
          )}
          <div className="grid gap-3">
            {messages.map((m, i) => (
              <div
                key={i}
                className={cn(
                  "max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-line",
                  m.role === "user"
                    ? "bg-primary text-primary-foreground justify-self-end rounded-br-sm"
                    : "bg-muted justify-self-start rounded-bl-sm",
                )}
              >
                {m.text}
                {m.role === "assistant" && m.sources.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1" aria-label="Sources">
                    {m.sources.map((s) => (
                      <Badge
                        key={`${s.type}:${s.title}`}
                        variant="outline"
                        className="bg-background font-normal"
                      >
                        {s.title}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {send.isPending && (
              <div className="bg-muted text-muted-foreground w-fit rounded-2xl px-3 py-2 text-sm">
                Thinking…
              </div>
            )}
          </div>
          <div ref={endRef} />
        </div>
        <form
          className="flex gap-2 border-t p-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit(input);
          }}
        >
          <Input
            aria-label="Your question"
            placeholder="Ask about the menu, delivery, timings…"
            value={input}
            maxLength={500}
            onChange={(e) => setInput(e.target.value)}
          />
          <Button
            type="submit"
            size="icon"
            aria-label="Send"
            disabled={!input.trim() || send.isPending}
          >
            <SendHorizontal />
          </Button>
        </form>
      </SheetContent>
    </Sheet>
  );
}
