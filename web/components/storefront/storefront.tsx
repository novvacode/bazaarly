"use client";

import { Clock, MapPin, Minus, Phone, Plus, ShoppingBag } from "lucide-react";
import Link from "next/link";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { VegMarker } from "@/components/veg-marker";
import { formatPaise } from "@/lib/money";
import type { PublicBusiness, PublicItem, StorefrontOut } from "@/lib/types";

import { MAX_QTY, useCart } from "./cart";
import { ChatWidget } from "./chat-widget";

export function QtyStepper({
  qty,
  onChange,
  label,
}: {
  qty: number;
  onChange: (qty: number) => void;
  label: string;
}) {
  return (
    <div className="border-primary/40 inline-flex items-center rounded-md border">
      <Button
        variant="ghost"
        size="icon"
        className="size-8"
        aria-label={`Remove one ${label}`}
        onClick={() => onChange(qty - 1)}
      >
        <Minus />
      </Button>
      <span className="w-7 text-center text-sm font-semibold tabular-nums" aria-live="polite">
        {qty}
      </span>
      <Button
        variant="ghost"
        size="icon"
        className="size-8"
        aria-label={`Add one ${label}`}
        disabled={qty >= MAX_QTY}
        onClick={() => onChange(qty + 1)}
      >
        <Plus />
      </Button>
    </div>
  );
}

function ItemCard({ item, canOrder }: { item: PublicItem; canOrder: boolean }) {
  const cart = useCart();
  const qty = cart.qtyOf(item.id);
  return (
    <article className="bg-card flex gap-3 rounded-xl border p-3" data-testid="menu-item">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <VegMarker isVeg={item.is_veg} />
          <h3 className="leading-tight font-semibold">{item.name}</h3>
        </div>
        <p className="mt-1 font-medium">{formatPaise(item.price_paise)}</p>
        {item.description && (
          <p className="text-muted-foreground mt-1 line-clamp-3 text-sm">{item.description}</p>
        )}
        {item.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {item.tags.map((t) => (
              <Badge key={t} variant="secondary" className="font-normal">
                {t}
              </Badge>
            ))}
          </div>
        )}
      </div>
      <div className="flex w-28 shrink-0 flex-col items-center gap-2">
        {item.image_url && (
          // eslint-disable-next-line @next/next/no-img-element -- already resized to ≤1200px WebP
          <img
            src={item.image_url}
            alt={item.name}
            loading="lazy"
            className="aspect-square w-28 rounded-lg object-cover"
          />
        )}
        {canOrder &&
          (qty > 0 ? (
            <QtyStepper qty={qty} label={item.name} onChange={(q) => cart.setQty(item.id, q)} />
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="border-primary/40 text-primary w-24 font-semibold"
              onClick={() =>
                cart.add({
                  id: item.id,
                  name: item.name,
                  price_paise: item.price_paise,
                  is_veg: item.is_veg,
                })
              }
              aria-label={`Add ${item.name}`}
            >
              Add
            </Button>
          ))}
      </div>
    </article>
  );
}

function fulfilmentSummary(b: PublicBusiness): string {
  const parts: string[] = [];
  if (b.fulfillment_modes.includes("pickup")) parts.push("Pickup");
  if (b.fulfillment_modes.includes("delivery")) {
    parts.push(
      b.delivery_fee_paise
        ? `Delivery (${formatPaise(b.delivery_fee_paise)} fee)`
        : "Free delivery",
    );
  }
  if (b.min_order_paise) parts.push(`Min order ${formatPaise(b.min_order_paise)}`);
  return parts.join(" · ");
}

export function CartSheet({ business }: { business: PublicBusiness }) {
  const cart = useCart();
  if (!cart.hydrated || cart.count === 0) return null;
  const belowMin = cart.subtotal < business.min_order_paise;
  return (
    <Sheet>
      <div className="fixed inset-x-0 bottom-0 z-40 p-3 sm:p-4">
        <SheetTrigger asChild>
          <Button
            size="lg"
            className="mx-auto flex h-12 w-full max-w-2xl justify-between shadow-lg"
          >
            <span className="flex items-center gap-2">
              <ShoppingBag />
              {cart.count} item{cart.count > 1 ? "s" : ""}
            </span>
            <span>{formatPaise(cart.subtotal)} · View cart</span>
          </Button>
        </SheetTrigger>
      </div>
      <SheetContent side="bottom" className="mx-auto max-w-2xl">
        <SheetHeader>
          <SheetTitle>Your cart</SheetTitle>
          <SheetDescription>{business.name}</SheetDescription>
        </SheetHeader>
        <ul className="flex flex-col gap-3 overflow-y-auto px-4">
          {cart.lines.map((line) => (
            <li key={line.id} className="flex min-w-0 items-center gap-3">
              <VegMarker isVeg={line.is_veg} />
              <span className="min-w-0 flex-1 truncate">{line.name}</span>
              <QtyStepper
                qty={line.qty}
                label={line.name}
                onChange={(q) => cart.setQty(line.id, q)}
              />
              <span className="w-20 text-right tabular-nums">
                {formatPaise(line.price_paise * line.qty)}
              </span>
            </li>
          ))}
        </ul>
        <SheetFooter className="border-t">
          <div className="flex justify-between font-semibold">
            <span>Subtotal</span>
            <span>{formatPaise(cart.subtotal)}</span>
          </div>
          {belowMin && (
            <p className="text-muted-foreground text-sm">
              Add {formatPaise(business.min_order_paise - cart.subtotal)} more to reach the minimum
              order of {formatPaise(business.min_order_paise)}.
            </p>
          )}
          {business.accepts_orders && !belowMin ? (
            <Button asChild size="lg">
              <Link href={`/b/${business.slug}/checkout`}>Checkout</Link>
            </Button>
          ) : (
            <Button size="lg" disabled>
              {business.accepts_orders ? "Checkout" : "Not taking orders right now"}
            </Button>
          )}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

export function Storefront({ data }: { data: StorefrontOut }) {
  const { business, categories } = data;
  const canOrder = business.accepts_orders;
  return (
    <div className="mx-auto w-full max-w-2xl px-4 pb-28">
      <header className="flex gap-4 py-6">
        {business.logo_url && (
          // eslint-disable-next-line @next/next/no-img-element -- already resized server-side
          <img
            src={business.logo_url}
            alt={`${business.name} logo`}
            className="size-16 shrink-0 rounded-xl border object-cover"
          />
        )}
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight">{business.name}</h1>
          {business.description && (
            <p className="text-muted-foreground mt-1 text-sm">{business.description}</p>
          )}
          <div className="text-muted-foreground mt-2 grid gap-1 text-sm">
            {business.hours_text && (
              <span className="flex items-center gap-1.5">
                <Clock className="size-3.5" aria-hidden /> {business.hours_text}
              </span>
            )}
            {business.address && (
              <span className="flex items-center gap-1.5">
                <MapPin className="size-3.5 shrink-0" aria-hidden /> {business.address}
              </span>
            )}
            {business.phone && (
              <a
                href={`tel:${business.phone}`}
                className="flex items-center gap-1.5 hover:underline"
              >
                <Phone className="size-3.5" aria-hidden /> {business.phone}
              </a>
            )}
          </div>
          <p className="mt-2 text-sm font-medium">{fulfilmentSummary(business)}</p>
        </div>
      </header>

      {!canOrder && (
        <Alert variant="warning" className="mb-4">
          <AlertTitle>Not taking orders right now</AlertTitle>
          <AlertDescription>
            You can still browse the menu. Please check back later.
          </AlertDescription>
        </Alert>
      )}

      {categories.length > 1 && (
        <nav
          aria-label="Menu categories"
          className="bg-background/95 sticky top-0 z-30 -mx-4 flex gap-2 overflow-x-auto border-b px-4 py-2 backdrop-blur"
        >
          {categories.map((c) => (
            <a
              key={c.id ?? "other"}
              href={`#cat-${c.id ?? "other"}`}
              className="bg-secondary hover:bg-accent rounded-full px-3 py-1 text-sm whitespace-nowrap"
            >
              {c.name}
            </a>
          ))}
        </nav>
      )}

      {categories.length === 0 ? (
        <p className="text-muted-foreground py-16 text-center">The menu is being prepared.</p>
      ) : (
        categories.map((c) => (
          <section
            key={c.id ?? "other"}
            id={`cat-${c.id ?? "other"}`}
            className="scroll-mt-14 pt-6"
          >
            <h2 className="mb-3 text-lg font-semibold">{c.name}</h2>
            <div className="grid gap-3">
              {c.items.map((item) => (
                <ItemCard key={item.id} item={item} canOrder={canOrder} />
              ))}
            </div>
          </section>
        ))
      )}

      <CartSheet business={business} />
      <ChatWidget slug={business.slug} businessName={business.name} />
    </div>
  );
}
