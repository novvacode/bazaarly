"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImageUp } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { CopyButton } from "@/components/copy-button";
import { PageHeader } from "@/components/dashboard/shell";
import { applyApiFieldErrors, Field } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { paiseToRupeesInput, rupeesToPaise } from "@/lib/money";
import { settingsSchema, type SettingsValues } from "@/lib/schemas";
import { storefrontUrl } from "@/lib/site";
import type { FulfillmentMode, TenantOut } from "@/lib/types";

function toForm(t: TenantOut): SettingsValues {
  return {
    name: t.name,
    description: t.description ?? "",
    phone: t.phone ?? "",
    email: t.email ?? "",
    address: t.address ?? "",
    hours_text: t.hours_text ?? "",
    accepts_orders: t.accepts_orders,
    pickup: t.fulfillment_modes.includes("pickup"),
    delivery: t.fulfillment_modes.includes("delivery"),
    delivery_areas: t.delivery_areas.join("\n"),
    min_order: paiseToRupeesInput(t.min_order_paise),
    delivery_fee: paiseToRupeesInput(t.delivery_fee_paise),
    timezone: t.timezone,
  };
}

function toPatch(v: SettingsValues) {
  const modes: FulfillmentMode[] = [];
  if (v.pickup) modes.push("pickup");
  if (v.delivery) modes.push("delivery");
  return {
    name: v.name,
    description: v.description || null,
    phone: v.phone || null,
    email: v.email || null,
    address: v.address || null,
    hours_text: v.hours_text || null,
    accepts_orders: v.accepts_orders,
    fulfillment_modes: modes,
    delivery_areas: v.delivery_areas
      .split(/[\n,]/)
      .map((a) => a.trim())
      .filter(Boolean),
    min_order_paise: rupeesToPaise(v.min_order) ?? 0,
    delivery_fee_paise: rupeesToPaise(v.delivery_fee) ?? 0,
    timezone: v.timezone,
  };
}

function LogoCard({ tenant }: { tenant: TenantOut }) {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api<TenantOut>("/tenant/logo", { method: "POST", formData: fd });
    },
    onSuccess: (t) => {
      queryClient.setQueryData(["tenant"], t);
      toast.success("Logo updated");
    },
    onError: (err) => toast.error(errorMessage(err)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Logo</CardTitle>
        <CardDescription>JPEG, PNG or WebP up to 2 MB. Shown on your storefront.</CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-4">
        <div className="bg-muted flex size-20 items-center justify-center overflow-hidden rounded-lg border">
          {tenant.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- user-uploaded, already resized
            <img
              src={tenant.logo_url}
              alt={`${tenant.name} logo`}
              className="size-full object-cover"
            />
          ) : (
            <ImageUp className="text-muted-foreground size-6" aria-hidden />
          )}
        </div>
        <input
          ref={input}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload.mutate(file);
            e.target.value = "";
          }}
        />
        <Button
          variant="outline"
          onClick={() => input.current?.click()}
          disabled={upload.isPending}
        >
          {upload.isPending ? "Uploading…" : "Upload logo"}
        </Button>
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const tenant = useQuery({ queryKey: ["tenant"], queryFn: () => api<TenantOut>("/tenant") });
  const form = useForm<SettingsValues>({ resolver: zodResolver(settingsSchema) });
  const delivery = useWatch({ control: form.control, name: "delivery" });
  const currentTz = tenant.data?.timezone;
  const timezones = useMemo(() => {
    let zones: string[] = [];
    try {
      zones = Intl.supportedValuesOf("timeZone");
    } catch {
      // Older browsers: fall back to the current value only.
    }
    // Browsers list CLDR canonical names (e.g. Asia/Calcutta); keep the IANA names we store.
    return Array.from(new Set(["Asia/Kolkata", ...(currentTz ? [currentTz] : []), ...zones]));
  }, [currentTz]);

  useEffect(() => {
    if (tenant.data) form.reset(toForm(tenant.data));
  }, [tenant.data, form]);

  const save = useMutation({
    mutationFn: (v: SettingsValues) =>
      api<TenantOut>("/tenant", { method: "PATCH", body: toPatch(v) }),
    onSuccess: (t) => {
      queryClient.setQueryData(["tenant"], t);
      form.reset(toForm(t));
      toast.success("Settings saved");
    },
    onError: (err) => {
      if (
        !applyApiFieldErrors(form, err, {
          min_order_paise: "min_order",
          delivery_fee_paise: "delivery_fee",
        })
      )
        toast.error(errorMessage(err));
    },
  });

  if (tenant.isPending) return <Skeleton className="h-96 w-full" />;
  if (tenant.isError) return <p className="text-destructive">{errorMessage(tenant.error)}</p>;

  const t = tenant.data;
  const url = storefrontUrl(t.slug);
  const { errors, isDirty } = form.formState;

  return (
    <>
      <PageHeader title="Settings" description="Your business profile and how you take orders." />
      <div className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Storefront link</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3">
            <code className="bg-muted rounded px-2 py-1 text-sm break-all">{url}</code>
            <CopyButton value={url} label="Copy link" />
          </CardContent>
        </Card>

        <LogoCard tenant={t} />

        <form onSubmit={form.handleSubmit((v) => save.mutate(v))} className="grid gap-6" noValidate>
          <Card>
            <CardHeader>
              <CardTitle>Taking orders</CardTitle>
              <CardDescription>Turn this off to close the shop temporarily.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-5">
              <div className="flex items-center gap-3">
                <Controller
                  control={form.control}
                  name="accepts_orders"
                  render={({ field }) => (
                    <Switch
                      id="accepts_orders"
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  )}
                />
                <Label htmlFor="accepts_orders">Accepting orders</Label>
              </div>
              <fieldset className="grid gap-2">
                <legend className="mb-2 text-sm font-medium">Fulfilment</legend>
                {(["pickup", "delivery"] as const).map((mode) => (
                  <div key={mode} className="flex items-center gap-2">
                    <Controller
                      control={form.control}
                      name={mode}
                      render={({ field }) => (
                        <Checkbox
                          id={`mode-${mode}`}
                          checked={field.value}
                          onCheckedChange={(v) => field.onChange(v === true)}
                        />
                      )}
                    />
                    <Label htmlFor={`mode-${mode}`}>
                      {mode === "pickup" ? "Pickup" : "Delivery"}
                    </Label>
                  </div>
                ))}
                {errors.pickup && (
                  <p className="text-destructive text-sm">{errors.pickup.message}</p>
                )}
              </fieldset>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  label="Minimum order (₹)"
                  htmlFor="min_order"
                  error={errors.min_order?.message}
                >
                  <Input id="min_order" inputMode="decimal" {...form.register("min_order")} />
                </Field>
                {delivery && (
                  <Field
                    label="Delivery fee (₹)"
                    htmlFor="delivery_fee"
                    error={errors.delivery_fee?.message}
                  >
                    <Input
                      id="delivery_fee"
                      inputMode="decimal"
                      {...form.register("delivery_fee")}
                    />
                  </Field>
                )}
              </div>
              {delivery && (
                <Field
                  label="Delivery areas"
                  htmlFor="delivery_areas"
                  error={errors.delivery_areas?.message}
                  hint="One per line. Leave empty to deliver anywhere."
                >
                  <Textarea id="delivery_areas" rows={4} {...form.register("delivery_areas")} />
                </Field>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Business profile</CardTitle>
              <CardDescription>
                Shown on your storefront and used by the AI assistant to answer questions.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field label="Business name" htmlFor="name" error={errors.name?.message}>
                <Input id="name" {...form.register("name")} />
              </Field>
              <Field label="Phone" htmlFor="phone" error={errors.phone?.message}>
                <Input id="phone" type="tel" autoComplete="tel" {...form.register("phone")} />
              </Field>
              <Field
                label="Notification email"
                htmlFor="email"
                error={errors.email?.message}
                hint="New-order emails go here."
              >
                <Input id="email" type="email" {...form.register("email")} />
              </Field>
              <Field label="Hours" htmlFor="hours_text" error={errors.hours_text?.message}>
                <Input
                  id="hours_text"
                  placeholder="Tue–Sun, 10am–8pm"
                  {...form.register("hours_text")}
                />
              </Field>
              <Field
                label="Address"
                htmlFor="address"
                error={errors.address?.message}
                className="sm:col-span-2"
              >
                <Input id="address" {...form.register("address")} />
              </Field>
              <Field
                label="About"
                htmlFor="description"
                error={errors.description?.message}
                className="sm:col-span-2"
              >
                <Textarea id="description" rows={4} {...form.register("description")} />
              </Field>
              <Field label="Timezone" htmlFor="timezone" error={errors.timezone?.message}>
                <select
                  id="timezone"
                  className="border-input dark:bg-input/30 h-9 rounded-md border bg-transparent px-3 text-sm"
                  {...form.register("timezone")}
                >
                  {timezones.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz}
                    </option>
                  ))}
                </select>
              </Field>
            </CardContent>
          </Card>

          <div className="bg-background/95 sticky bottom-0 flex justify-end gap-2 border-t py-3">
            <Button
              type="button"
              variant="ghost"
              disabled={!isDirty}
              onClick={() => form.reset(toForm(t))}
            >
              Discard
            </Button>
            <Button type="submit" disabled={!isDirty || save.isPending}>
              {save.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </form>
      </div>
    </>
  );
}
