"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Field } from "@/components/form-field";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/auth";
import type { AuthOut, InvitePreviewOut } from "@/lib/types";

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { status, user, setSession } = useSession();
  const [fields, setFields] = useState({ name: "", email: "", password: "" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const preview = useQuery({
    queryKey: ["invite", token],
    queryFn: () => api<InvitePreviewOut>(`/auth/invites/${token}`, { auth: false }),
    retry: false,
  });

  const accept = useMutation({
    mutationFn: (body: Record<string, string>) =>
      api<AuthOut>(`/auth/invites/${token}/accept`, {
        body,
        auth: status === "authenticated",
      }),
    onSuccess: (session) => {
      setSession(session);
      toast.success(`You've joined ${session.tenant?.name ?? "the team"}`);
      router.replace("/dashboard");
    },
    onError: (err) => {
      if (err instanceof ApiError && Object.keys(err.fields).length) setFieldErrors(err.fields);
      else toast.error(errorMessage(err));
    },
  });

  if (preview.isPending) {
    return <Skeleton className="h-64 w-full" />;
  }
  if (preview.isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Invite not valid</AlertTitle>
        <AlertDescription>
          This invite link is invalid, already used, or expired. Ask the business owner for a new
          one.
        </AlertDescription>
      </Alert>
    );
  }

  const set = (k: keyof typeof fields) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setFields((f) => ({ ...f, [k]: e.target.value }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Join {preview.data.business_name}</CardTitle>
        <CardDescription>
          You&apos;ve been invited as <strong>{preview.data.role}</strong>. Staff can view the menu
          and manage orders.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {status === "authenticated" && user ? (
          <div className="grid gap-3">
            <p className="text-sm">
              Signed in as <strong>{user.email}</strong>.
            </p>
            <Button onClick={() => accept.mutate({})} disabled={accept.isPending}>
              {accept.isPending ? "Joining…" : `Join ${preview.data.business_name}`}
            </Button>
          </div>
        ) : (
          <Tabs defaultValue="new">
            <TabsList className="w-full">
              <TabsTrigger value="new">New account</TabsTrigger>
              <TabsTrigger value="existing">I have an account</TabsTrigger>
            </TabsList>
            <TabsContent value="new">
              <form
                className="grid gap-4 pt-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  accept.mutate(fields);
                }}
              >
                <Field label="Your name" htmlFor="inv-name" error={fieldErrors.name}>
                  <Input id="inv-name" required value={fields.name} onChange={set("name")} />
                </Field>
                <Field label="Email" htmlFor="inv-email" error={fieldErrors.email}>
                  <Input
                    id="inv-email"
                    type="email"
                    required
                    autoComplete="email"
                    value={fields.email}
                    onChange={set("email")}
                  />
                </Field>
                <Field
                  label="Password"
                  htmlFor="inv-password"
                  error={fieldErrors.password}
                  hint="At least 8 characters."
                >
                  <Input
                    id="inv-password"
                    type="password"
                    required
                    autoComplete="new-password"
                    value={fields.password}
                    onChange={set("password")}
                  />
                </Field>
                <Button type="submit" disabled={accept.isPending}>
                  Create account and join
                </Button>
              </form>
            </TabsContent>
            <TabsContent value="existing">
              <form
                className="grid gap-4 pt-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  accept.mutate({ email: fields.email, password: fields.password });
                }}
              >
                <Field label="Email" htmlFor="inv-email2" error={fieldErrors.email}>
                  <Input
                    id="inv-email2"
                    type="email"
                    required
                    autoComplete="email"
                    value={fields.email}
                    onChange={set("email")}
                  />
                </Field>
                <Field label="Password" htmlFor="inv-password2" error={fieldErrors.password}>
                  <Input
                    id="inv-password2"
                    type="password"
                    required
                    autoComplete="current-password"
                    value={fields.password}
                    onChange={set("password")}
                  />
                </Field>
                <Button type="submit" disabled={accept.isPending}>
                  Sign in and join
                </Button>
              </form>
            </TabsContent>
          </Tabs>
        )}
      </CardContent>
    </Card>
  );
}
