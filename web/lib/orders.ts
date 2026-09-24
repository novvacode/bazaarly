import type { OrderStatus } from "./types";

/** Customer/merchant-facing labels. The state machine itself lives only in the API. */
export const STATUS_LABEL: Record<OrderStatus, string> = {
  pending_payment: "Awaiting payment",
  placed: "New",
  confirmed: "Confirmed",
  preparing: "Preparing",
  ready: "Ready for pickup",
  out_for_delivery: "Out for delivery",
  completed: "Completed",
  cancelled: "Cancelled",
};

/** Button text for moving an order *to* a status. */
export const ACTION_LABEL: Record<OrderStatus, string> = {
  pending_payment: "Awaiting payment",
  placed: "Mark placed",
  confirmed: "Confirm",
  preparing: "Start preparing",
  ready: "Ready for pickup",
  out_for_delivery: "Out for delivery",
  completed: "Complete",
  cancelled: "Cancel order",
};

export const STATUS_TONE: Record<OrderStatus, string> = {
  pending_payment: "bg-muted text-muted-foreground",
  placed: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100",
  confirmed: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-100",
  preparing: "bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-100",
  ready: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
  out_for_delivery: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
  completed: "bg-secondary text-secondary-foreground",
  cancelled: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-100",
};

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID().replace(/-/g, "");
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
}

const timeFmt = new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit" });
const dateTimeFmt = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
});

export function formatTime(iso: string) {
  return timeFmt.format(new Date(iso));
}

export function formatDateTime(iso: string) {
  return dateTimeFmt.format(new Date(iso));
}

export function minutesAgo(iso: string, now = Date.now()) {
  const mins = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  return hours < 24 ? `${hours} h ago` : `${Math.floor(hours / 24)} d ago`;
}
