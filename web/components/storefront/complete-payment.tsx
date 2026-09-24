"use client";

import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { api, errorMessage } from "@/lib/api";
import { formatPaise } from "@/lib/money";
import type { PaymentParams, PublicOrderOut } from "@/lib/types";

import { openCheckout } from "./razorpay";

/** Shown on the tracking page while an online order still awaits payment. */
export function CompletePayment({
  token,
  order,
  onPaid,
}: {
  token: string;
  order: PublicOrderOut;
  onPaid: () => void;
}) {
  const pay = useMutation({
    mutationFn: async () => {
      const params = await api<PaymentParams>(`/public/orders/${token}/payment`, { auth: false });
      return openCheckout(token, params);
    },
    onSuccess: (outcome) => {
      if (outcome === "paid") toast.success("Payment received — thank you!");
      if (outcome === "failed") toast.error("Payment didn't go through. You can try again.");
      onPaid();
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  return (
    <Alert variant="warning">
      <AlertTitle>Payment pending</AlertTitle>
      <AlertDescription>
        <p>
          Complete the payment of {formatPaise(order.totals.total_paise)} within 30 minutes of
          ordering, or the order is cancelled automatically.
        </p>
        <Button className="mt-2" onClick={() => pay.mutate()} disabled={pay.isPending}>
          {pay.isPending ? "Opening…" : "Pay now"}
        </Button>
      </AlertDescription>
    </Alert>
  );
}
