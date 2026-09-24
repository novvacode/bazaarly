import "server-only";

import type { StorefrontOut } from "./types";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** Storefront payload for server rendering, revalidated every 60 s (SPEC §14.2). */
export async function getStorefront(slug: string): Promise<StorefrontOut | null> {
  const res = await fetch(`${API}/api/v1/public/b/${encodeURIComponent(slug)}`, {
    next: { revalidate: 60, tags: [`storefront:${slug}`] },
    headers: { Accept: "application/json" },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Storefront request failed: ${res.status}`);
  return (await res.json()) as StorefrontOut;
}
