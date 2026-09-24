"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type CartLine = {
  id: string;
  name: string;
  price_paise: number;
  is_veg: boolean;
  qty: number;
};

type CartState = { lines: CartLine[] };

export const MAX_QTY = 50;
export const MAX_LINES = 30;

type CartContextValue = {
  slug: string;
  lines: CartLine[];
  hydrated: boolean;
  count: number;
  subtotal: number;
  qtyOf: (id: string) => number;
  add: (line: Omit<CartLine, "qty">) => void;
  setQty: (id: string, qty: number) => void;
  replace: (lines: CartLine[]) => void;
  clear: () => void;
};

const CartContext = createContext<CartContextValue | null>(null);

const storageKey = (slug: string) => `bz:cart:${slug}`;

function load(slug: string): CartState {
  try {
    const raw = window.localStorage.getItem(storageKey(slug));
    if (!raw) return { lines: [] };
    const parsed = JSON.parse(raw) as CartState;
    if (!Array.isArray(parsed.lines)) return { lines: [] };
    return {
      lines: parsed.lines
        .filter((l) => l && typeof l.id === "string" && Number.isInteger(l.qty) && l.qty > 0)
        .slice(0, MAX_LINES)
        .map((l) => ({ ...l, qty: Math.min(l.qty, MAX_QTY) })),
    };
  } catch {
    return { lines: [] };
  }
}

/** Cart persisted in localStorage, one cart per storefront slug (SPEC §14.2). */
export function CartProvider({ slug, children }: { slug: string; children: React.ReactNode }) {
  const [state, setState] = useState<CartState>({ lines: [] });
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    // Hydrate from localStorage after mount (it is unavailable during server rendering).
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time client-only hydration
    setState(load(slug));
    setHydrated(true);
    const onStorage = (e: StorageEvent) => {
      if (e.key === storageKey(slug)) setState(load(slug));
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [slug]);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(storageKey(slug), JSON.stringify(state));
    } catch {
      // Storage full or disabled: the cart still works for this page view.
    }
  }, [state, slug, hydrated]);

  const add = useCallback((line: Omit<CartLine, "qty">) => {
    setState((s) => {
      const existing = s.lines.find((l) => l.id === line.id);
      if (existing) {
        return {
          lines: s.lines.map((l) =>
            l.id === line.id ? { ...l, qty: Math.min(l.qty + 1, MAX_QTY) } : l,
          ),
        };
      }
      if (s.lines.length >= MAX_LINES) return s;
      return { lines: [...s.lines, { ...line, qty: 1 }] };
    });
  }, []);

  const setQty = useCallback((id: string, qty: number) => {
    setState((s) => ({
      lines:
        qty <= 0
          ? s.lines.filter((l) => l.id !== id)
          : s.lines.map((l) => (l.id === id ? { ...l, qty: Math.min(qty, MAX_QTY) } : l)),
    }));
  }, []);

  const replace = useCallback((lines: CartLine[]) => setState({ lines }), []);
  const clear = useCallback(() => setState({ lines: [] }), []);

  const value = useMemo<CartContextValue>(() => {
    const count = state.lines.reduce((n, l) => n + l.qty, 0);
    const subtotal = state.lines.reduce((n, l) => n + l.qty * l.price_paise, 0);
    return {
      slug,
      lines: state.lines,
      hydrated,
      count,
      subtotal,
      qtyOf: (id) => state.lines.find((l) => l.id === id)?.qty ?? 0,
      add,
      setQty,
      replace,
      clear,
    };
  }, [slug, state, hydrated, add, setQty, replace, clear]);

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used inside <CartProvider>");
  return ctx;
}
