"use client";

import { PageHeader } from "@/components/dashboard/shell";
import { CopyButton } from "@/components/copy-button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";
import { storefrontUrl } from "@/lib/site";

export default function DashboardHome() {
  const { tenant } = useAuth();
  if (!tenant) return null;
  const url = storefrontUrl(tenant.slug);
  return (
    <>
      <PageHeader title="Order board" description="New orders appear here as they come in." />
      <Card>
        <CardHeader>
          <CardTitle>Share your storefront</CardTitle>
          <CardDescription>
            Send this link on WhatsApp or add it to your Instagram bio.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <code className="bg-muted rounded px-2 py-1 text-sm break-all">{url}</code>
          <CopyButton value={url} label="Copy link" />
        </CardContent>
      </Card>
    </>
  );
}
