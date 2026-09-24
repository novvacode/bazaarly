import Link from "next/link";

import { ApiStatus } from "@/components/api-status";
import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-8 px-4 py-16">
      <div className="space-y-4">
        <p className="text-primary text-sm font-semibold tracking-wide uppercase">Bazaarly</p>
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          Take orders online. Keep the WhatsApp link.
        </h1>
        <p className="text-muted-foreground text-lg">
          A storefront for your home bakery, tiffin service, or craft shop. Customers order without
          an account, pay online or on delivery, and you run everything from one dashboard.
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        <Button asChild size="lg">
          <Link href="/signup">Create your store</Link>
        </Button>
        <Button asChild size="lg" variant="outline">
          <Link href="/b/demo-bakery">See a demo store</Link>
        </Button>
      </div>
      <ApiStatus />
    </main>
  );
}
