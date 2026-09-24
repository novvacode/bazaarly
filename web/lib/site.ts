/** Absolute storefront URL for sharing (falls back to the current origin in the browser). */
export function storefrontUrl(slug: string): string {
  const origin =
    typeof window !== "undefined"
      ? window.location.origin
      : (process.env.NEXT_PUBLIC_SITE_URL ?? "");
  return `${origin}/b/${slug}`;
}
