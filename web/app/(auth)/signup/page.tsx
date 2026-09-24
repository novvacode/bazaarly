"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { applyApiFieldErrors, Field } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/auth";
import { signupSchema, suggestSlug, type SignupValues } from "@/lib/schemas";
import type { AuthOut } from "@/lib/types";

export default function SignupPage() {
  const router = useRouter();
  const { status, setSession } = useSession();
  const [slugTouched, setSlugTouched] = useState(false);
  // Set once this page creates the session, so the "already signed in" redirect doesn't race
  // the post-signup redirect to settings.
  const [created, setCreated] = useState(false);
  const form = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: { name: "", email: "", password: "", business_name: "", slug: "" },
  });

  useEffect(() => {
    if (status === "authenticated" && !created) router.replace("/dashboard");
  }, [status, router, created]);

  const businessName = useWatch({ control: form.control, name: "business_name" });
  useEffect(() => {
    if (!slugTouched) form.setValue("slug", suggestSlug(businessName ?? ""));
  }, [businessName, form, slugTouched]);

  async function onSubmit(values: SignupValues) {
    try {
      const session = await api<AuthOut>("/auth/signup", { body: values, auth: false });
      setCreated(true);
      setSession(session);
      toast.success("Your store is ready!");
      router.replace("/dashboard/settings");
    } catch (err) {
      if (err instanceof ApiError && err.code === "EMAIL_TAKEN") {
        form.setError("email", { message: err.message });
      } else if (err instanceof ApiError && err.code === "SLUG_TAKEN") {
        form.setError("slug", { message: err.message });
      } else if (!applyApiFieldErrors(form, err)) {
        toast.error(errorMessage(err));
      }
    }
  }

  const { errors, isSubmitting } = form.formState;
  const slug = useWatch({ control: form.control, name: "slug" });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Create your store</CardTitle>
        <CardDescription>Free to start. You can change everything later.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4" noValidate>
          <Field label="Your name" htmlFor="name" error={errors.name?.message}>
            <Input id="name" autoComplete="name" {...form.register("name")} />
          </Field>
          <Field label="Email" htmlFor="email" error={errors.email?.message}>
            <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
          </Field>
          <Field
            label="Password"
            htmlFor="password"
            error={errors.password?.message}
            hint="At least 8 characters. Avoid common passwords."
          >
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              {...form.register("password")}
            />
          </Field>
          <Field
            label="Business name"
            htmlFor="business_name"
            error={errors.business_name?.message}
          >
            <Input id="business_name" {...form.register("business_name")} />
          </Field>
          <Field
            label="Store link"
            htmlFor="slug"
            error={errors.slug?.message}
            hint={slug ? `Customers will order at /b/${slug}` : undefined}
          >
            <Input
              id="slug"
              autoCapitalize="none"
              {...form.register("slug", {
                onChange: () => setSlugTouched(true),
              })}
            />
          </Field>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating…" : "Create store"}
          </Button>
          <p className="text-muted-foreground text-center text-sm">
            Already have an account?{" "}
            <Link
              href="/login"
              className="text-primary font-medium underline-offset-4 hover:underline"
            >
              Sign in
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
