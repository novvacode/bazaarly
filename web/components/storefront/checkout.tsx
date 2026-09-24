"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Field } from "@/components/form-field";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { VegMarker } from "@/components/veg-marker";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatPaise } from "@/lib/money";
import { newIdempotencyKey } from "@/lib/orders";
import type {
  FulfillmentMode,
  OrderCreatedOut,
  PaymentMethod,
  PublicItem,
  StorefrontOut,
} from "@/lib/types";
import { cn } from "@/lib/utils";

import { useCart, type CartLine } from "./cart";
import { payOnline } from "./razorpay";
import { QtyStepper } from "./storefront";

type Details = {
  customer_name: string;
  customer_phone: string;
  customer_email: string;
  delivery_address: string;
  delivery_area: string;
  notes: string;
};

const DETAILS_KEY = "bz:customer";

function loadDetails(): Partial<Details> {
  try {
    return JSON.parse(window.localStorage.getItem(DETAILS_KEY) ?? "{}") as Partial<Details>;
  } catch {
    return {};
  }
}

function Choice<T extends string>({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: T;
  options: { value: T; label: string; hint?: string; disabled?: boolean }[];
  onChange: (v: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={name} className="grid gap-2 sm:grid-cols-2">
      {options.map((o) => (
        <label
          key={o.value}
          className={cn(
            "flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm",
            value === o.value && "border-primary bg-primary/5",
            o.disabled && "cursor-not-allowed opacity-50",
          )}
        >
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={value === o.value}
            disabled={o.disabled}
            onChange={() => onChange(o.value)}
            className="accent-primary mt-0.5"
          />
          <span>
            <span className="font-medium">{o.label}</span>
            {o.hint && <span className="text-muted-foreground block text-xs">{o.hint}</span>}
          </span>
        </label>
      ))}
    </div>
  );
}

/** Drop items that disappeared and refresh prices/names from the live menu. */
function reconcile(lines: CartLine[], store: StorefrontOut) {
  const live = new Map<string, PublicItem>();
  for (const c of store.categories) for (const i of c.items) live.set(i.id, i);
  const removed: string[] = [];
  let repriced = false;
  const next: CartLine[] = [];
  for (const line of lines) {
    const item = live.get(line.id);
    if (!item) {
      removed.push(line.name);
      continue;
    }
    if (item.price_paise !== line.price_paise) repriced = true;
    next.push({ ...line, name: item.name, price_paise: item.price_paise, is_veg: item.is_veg });
  }
  return { next, removed, repriced };
}

export function Checkout({ slug }: { slug: string }) {
  const router = useRouter();
  const cart = useCart();
  const [idempotencyKey] = useState(newIdempotencyKey);
  const [details, setDetails] = useState<Details>({
    customer_name: "",
    customer_phone: "",
    customer_email: "",
    delivery_address: "",
    delivery_area: "",
    notes: "",
  });
  const [mode, setMode] = useState<FulfillmentMode>("pickup");
  const [payment, setPayment] = useState<PaymentMethod>("cod");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const reconciled = useRef(false);

  const store = useQuery({
    queryKey: ["storefront", slug],
    queryFn: () => api<StorefrontOut>(`/public/b/${slug}`, { auth: false }),
  });

  useEffect(() => {
    // Restore saved contact details once on the client.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time client-only restore
    setDetails((d) => ({ ...d, ...loadDetails(), notes: "" }));
  }, []);

  useEffect(() => {
    const data = store.data;
    if (!data) return;
    if (!data.business.fulfillment_modes.includes(mode)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- default to what the store offers
      setMode(data.business.fulfillment_modes[0] ?? "pickup");
    }
    if (!cart.hydrated || reconciled.current) return;
    reconciled.current = true;
    const { next, removed, repriced } = reconcile(cart.lines, data);
    if (removed.length || repriced) {
      cart.replace(next);
      if (removed.length) toast.warning(`No longer available: ${removed.join(", ")}`);
      if (repriced) toast.info("Some prices changed. Please review your order.");
    }
  }, [store.data, cart, mode]);

  const place = useMutation({
    mutationFn: () => {
      const b = store.data!.business;
      return api<OrderCreatedOut>(`/public/b/${slug}/orders`, {
        auth: false,
        body: {
          idempotency_key: idempotencyKey,
          items: cart.lines.map((l) => ({ menu_item_id: l.id, quantity: l.qty })),
          customer_name: details.customer_name,
          customer_phone: details.customer_phone,
          customer_email: details.customer_email || null,
          fulfillment_mode: mode,
          delivery_address: mode === "delivery" ? details.delivery_address : null,
          delivery_area:
            mode === "delivery" && b.delivery_areas.length ? details.delivery_area : null,
          notes: details.notes || null,
          payment_method: payment,
        },
      });
    },
    onSuccess: async (out) => {
      try {
        const { notes: _notes, ...keep } = details;
        window.localStorage.setItem(DETAILS_KEY, JSON.stringify(keep));
      } catch {
        // Not critical.
      }
      cart.clear();
      if (out.payment) {
        const outcome = await payOnline(out).catch((e: unknown) => {
          toast.error(errorMessage(e));
          return "failed" as const;
        });
        if (outcome === "paid") toast.success("Payment received — thank you!");
      }
      router.replace(`/o/${out.order.public_token}`);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.code === "ORDER_ITEMS_INVALID") {
          const bad = new Set((err.details.item_ids as string[]) ?? []);
          const names = cart.lines.filter((l) => bad.has(l.id)).map((l) => l.name);
          cart.replace(cart.lines.filter((l) => !bad.has(l.id)));
          toast.error(
            names.length ? `Removed unavailable items: ${names.join(", ")}` : err.message,
          );
          return;
        }
        if (Object.keys(err.fields).length) {
          setFieldErrors(err.fields);
          toast.error(err.message);
          return;
        }
      }
      toast.error(errorMessage(err));
    },
  });

  if (store.isPending || !cart.hydrated) {
    return (
      <div className="mx-auto grid max-w-xl gap-4 p-4">
        <Skeleton className="h-10 w-40" />
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }
  if (store.isError) {
    return <p className="text-destructive p-6">{errorMessage(store.error)}</p>;
  }

  const b = store.data.business;
  const fee = mode === "delivery" ? b.delivery_fee_paise : 0;
  const total = cart.subtotal + fee;
  const belowMin = cart.subtotal < b.min_order_paise;
  const set =
    (k: keyof Details) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setDetails((d) => ({ ...d, [k]: e.target.value }));

  if (cart.lines.length === 0) {
    return (
      <div className="mx-auto max-w-xl p-6 text-center">
        <p className="font-medium">Your cart is empty.</p>
        <Button asChild className="mt-4">
          <Link href={`/b/${slug}`}>Back to menu</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-xl px-4 pt-4 pb-16">
      <Link
        href={`/b/${slug}`}
        className="text-muted-foreground hover:text-foreground mb-4 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> {b.name}
      </Link>
      <h1 className="mb-4 text-2xl font-bold">Checkout</h1>

      {!b.accepts_orders && (
        <Alert variant="warning" className="mb-4">
          <AlertTitle>Not taking orders right now</AlertTitle>
          <AlertDescription>Please try again later.</AlertDescription>
        </Alert>
      )}

      <form
        className="grid gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          setFieldErrors({});
          place.mutate();
        }}
      >
        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="text-base">Your order</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            {cart.lines.map((line) => (
              <div key={line.id} className="flex min-w-0 items-center gap-3">
                <VegMarker isVeg={line.is_veg} />
                <span className="min-w-0 flex-1 truncate text-sm">{line.name}</span>
                <QtyStepper
                  qty={line.qty}
                  label={line.name}
                  onChange={(q) => cart.setQty(line.id, q)}
                />
                <span className="w-20 text-right text-sm tabular-nums">
                  {formatPaise(line.qty * line.price_paise)}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="text-base">Contact</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <Field label="Name" htmlFor="customer_name" error={fieldErrors.customer_name}>
              <Input
                id="customer_name"
                required
                maxLength={100}
                autoComplete="name"
                value={details.customer_name}
                onChange={set("customer_name")}
              />
            </Field>
            <Field
              label="Mobile number"
              htmlFor="customer_phone"
              error={fieldErrors.customer_phone}
              hint="The store will call this number if needed."
            >
              <Input
                id="customer_phone"
                type="tel"
                required
                inputMode="tel"
                autoComplete="tel"
                maxLength={20}
                value={details.customer_phone}
                onChange={set("customer_phone")}
              />
            </Field>
            <Field
              label="Email (optional)"
              htmlFor="customer_email"
              error={fieldErrors.customer_email}
              hint="Get order updates by email."
            >
              <Input
                id="customer_email"
                type="email"
                autoComplete="email"
                value={details.customer_email}
                onChange={set("customer_email")}
              />
            </Field>
          </CardContent>
        </Card>

        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="text-base">Pickup or delivery</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            {b.fulfillment_modes.length > 1 && (
              <Choice
                name="Fulfilment"
                value={mode}
                onChange={setMode}
                options={[
                  { value: "pickup", label: "Pickup", hint: b.address ?? undefined },
                  {
                    value: "delivery",
                    label: "Delivery",
                    hint: b.delivery_fee_paise
                      ? `${formatPaise(b.delivery_fee_paise)} fee`
                      : "Free",
                  },
                ]}
              />
            )}
            {b.fulfillment_modes.length === 1 && (
              <p className="text-sm">
                {mode === "pickup" ? `Pickup from ${b.address ?? "the store"}` : "Delivery only"}
              </p>
            )}
            {mode === "delivery" && (
              <>
                <Field
                  label="Delivery address"
                  htmlFor="delivery_address"
                  error={fieldErrors.delivery_address}
                >
                  <Textarea
                    id="delivery_address"
                    required
                    rows={2}
                    maxLength={300}
                    autoComplete="street-address"
                    value={details.delivery_address}
                    onChange={set("delivery_address")}
                  />
                </Field>
                {b.delivery_areas.length > 0 && (
                  <Field label="Area" htmlFor="delivery_area" error={fieldErrors.delivery_area}>
                    <select
                      id="delivery_area"
                      required
                      className="border-input dark:bg-input/30 h-9 rounded-md border bg-transparent px-3 text-sm"
                      value={details.delivery_area}
                      onChange={set("delivery_area")}
                    >
                      <option value="">Choose your area</option>
                      {b.delivery_areas.map((a) => (
                        <option key={a} value={a}>
                          {a}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
              </>
            )}
            <Field label="Notes (optional)" htmlFor="notes" error={fieldErrors.notes}>
              <Textarea
                id="notes"
                rows={2}
                maxLength={500}
                placeholder="e.g. message on the cake, less spicy"
                value={details.notes}
                onChange={set("notes")}
              />
            </Field>
          </CardContent>
        </Card>

        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="text-base">Payment</CardTitle>
          </CardHeader>
          <CardContent>
            <Choice
              name="Payment"
              value={payment}
              onChange={setPayment}
              options={[
                {
                  value: "cod",
                  label: mode === "delivery" ? "Cash on delivery" : "Pay at pickup",
                  hint: "Cash or UPI to the store",
                },
                {
                  value: "online",
                  label: "Pay online",
                  hint: b.accepts_online_payments ? "UPI, cards, netbanking" : "Not available",
                  disabled: !b.accepts_online_payments,
                },
              ]}
            />
          </CardContent>
        </Card>

        <div className="grid gap-1 text-sm">
          <div className="flex justify-between">
            <span>Subtotal</span>
            <span className="tabular-nums">{formatPaise(cart.subtotal)}</span>
          </div>
          {mode === "delivery" && (
            <div className="flex justify-between">
              <span>Delivery</span>
              <span className="tabular-nums">{fee ? formatPaise(fee) : "Free"}</span>
            </div>
          )}
          <div className="flex justify-between text-base font-semibold">
            <span>Total</span>
            <span className="tabular-nums">{formatPaise(total)}</span>
          </div>
          {belowMin && (
            <p className="text-destructive">
              Minimum order is {formatPaise(b.min_order_paise)}. Add{" "}
              {formatPaise(b.min_order_paise - cart.subtotal)} more.
            </p>
          )}
        </div>

        <Button type="submit" size="lg" disabled={place.isPending || belowMin || !b.accepts_orders}>
          {place.isPending
            ? "Placing order…"
            : payment === "online"
              ? `Pay ${formatPaise(total)}`
              : `Place order · ${formatPaise(total)}`}
        </Button>
      </form>
    </div>
  );
}
