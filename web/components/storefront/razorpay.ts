/** Razorpay Checkout integration (SPEC §11): open the modal, then verify on the server. */
import { api } from "@/lib/api";
import type { OrderCreatedOut, PaymentParams, PublicOrderOut } from "@/lib/types";

type RazorpayResponse = {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
};

type RazorpayInstance = { open: () => void; on: (event: string, cb: (e: unknown) => void) => void };
type RazorpayCtor = new (options: Record<string, unknown>) => RazorpayInstance;

declare global {
  interface Window {
    Razorpay?: RazorpayCtor;
  }
}

const SCRIPT_SRC = "https://checkout.razorpay.com/v1/checkout.js";
let scriptPromise: Promise<RazorpayCtor> | null = null;

function loadCheckout(): Promise<RazorpayCtor> {
  if (window.Razorpay) return Promise.resolve(window.Razorpay);
  scriptPromise ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT_SRC;
    script.async = true;
    script.onload = () =>
      window.Razorpay ? resolve(window.Razorpay) : reject(new Error("Checkout failed to load"));
    script.onerror = () => {
      scriptPromise = null;
      reject(new Error("Couldn't load the payment window. Check your connection."));
    };
    document.body.appendChild(script);
  });
  return scriptPromise;
}

export type PaymentOutcome = "paid" | "dismissed" | "failed";

/** Open Razorpay Checkout for `params`; on success verify with the API. */
export async function openCheckout(
  publicToken: string,
  params: PaymentParams,
): Promise<PaymentOutcome> {
  const Razorpay = await loadCheckout();
  return new Promise<PaymentOutcome>((resolve) => {
    const rzp = new Razorpay({
      key: params.key_id,
      amount: params.amount_paise,
      currency: params.currency,
      name: params.name,
      order_id: params.razorpay_order_id,
      prefill: params.prefill,
      theme: { color: "#c2410c" },
      handler: async (response: RazorpayResponse) => {
        try {
          await api<PublicOrderOut>(`/public/orders/${publicToken}/payment/verify`, {
            auth: false,
            body: response,
          });
          resolve("paid");
        } catch {
          // The webhook will still confirm it; the tracking page polls.
          resolve("failed");
        }
      },
      modal: { ondismiss: () => resolve("dismissed") },
    });
    rzp.on("payment.failed", () => resolve("failed"));
    rzp.open();
  });
}

export async function payOnline(created: OrderCreatedOut): Promise<PaymentOutcome | null> {
  if (!created.payment) return null;
  return openCheckout(created.order.public_token, created.payment);
}
