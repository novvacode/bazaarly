import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Storefront } from "@/components/storefront/storefront";
import { getStorefront } from "@/lib/server-api";

// Server-rendered, revalidated every 60 s (SPEC §14.2).
export const revalidate = 60;

export async function generateMetadata({ params }: PageProps<"/b/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const data = await getStorefront(slug);
  if (!data) return { title: "Store not found" };
  return {
    title: data.business.name,
    description: data.business.description ?? `Order from ${data.business.name}`,
    openGraph: {
      title: data.business.name,
      description: data.business.description ?? undefined,
      images: data.business.logo_url ? [data.business.logo_url] : undefined,
    },
  };
}

export default async function StorePage({ params }: PageProps<"/b/[slug]">) {
  const { slug } = await params;
  const data = await getStorefront(slug);
  if (!data) notFound();
  return <Storefront data={data} />;
}
