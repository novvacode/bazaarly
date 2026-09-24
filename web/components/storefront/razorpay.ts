/** Razorpay Checkout integration. Filled in with online payments (Phase 5). */
import type { OrderCreatedOut } from "@/lib/types";

export function onlinePaymentsEnabled(): boolean {
  return false;
}

export async function payOnline(
  _created: OrderCreatedOut,
  _customer: { customer_name: string; customer_phone: string; customer_email: string },
): Promise<void> {
  return;
}
