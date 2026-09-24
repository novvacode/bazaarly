"use client";

import type { PublicOrderOut } from "@/lib/types";

/** Retry an online payment from the tracking page. Filled in with online payments (Phase 5). */
export function CompletePayment(_props: {
  token: string;
  order: PublicOrderOut;
  onPaid: () => void;
}) {
  return null;
}
