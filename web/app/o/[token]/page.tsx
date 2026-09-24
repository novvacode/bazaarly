import type { Metadata } from "next";

import { OrderTracking } from "@/components/storefront/tracking";

export const metadata: Metadata = { title: "Your order", robots: { index: false } };

export default async function TrackingPage({ params }: PageProps<"/o/[token]">) {
  const { token } = await params;
  return <OrderTracking token={token} />;
}
