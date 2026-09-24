import type { Metadata } from "next";

import { Checkout } from "@/components/storefront/checkout";

export const metadata: Metadata = { title: "Checkout", robots: { index: false } };

export default async function CheckoutPage({ params }: PageProps<"/b/[slug]/checkout">) {
  const { slug } = await params;
  return <Checkout slug={slug.toLowerCase()} />;
}
