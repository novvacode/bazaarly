"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { OrderDetailView } from "@/components/orders/order-detail";
import { Card, CardContent } from "@/components/ui/card";

export default function OrderPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <div className="mx-auto max-w-2xl">
      <Link
        href="/dashboard/orders"
        className="text-muted-foreground hover:text-foreground mb-4 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> All orders
      </Link>
      <Card>
        <CardContent>
          <OrderDetailView orderId={id} />
        </CardContent>
      </Card>
    </div>
  );
}
