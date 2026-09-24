"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ImageUp } from "lucide-react";
import { useEffect, useRef } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { applyApiFieldErrors, Field } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { paiseToRupeesInput, rupeesToPaise } from "@/lib/money";
import { rupeesField } from "@/lib/schemas";
import type { CategoryOut, ItemOut } from "@/lib/types";

const NONE = "__none__";

const itemSchema = z.object({
  name: z.string().trim().min(1, "Required").max(100),
  description: z.string().max(1000),
  price: rupeesField.refine((v) => (rupeesToPaise(v) ?? 0) > 0, "Price must be more than ₹0"),
  category_id: z.string(),
  is_veg: z.boolean(),
  is_available: z.boolean(),
  tags: z
    .string()
    .max(400)
    .refine(
      (v) =>
        v
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean).length <= 10,
      "At most 10 tags",
    ),
});
type ItemValues = z.infer<typeof itemSchema>;

function defaults(item: ItemOut | null, categoryId: string | null): ItemValues {
  return {
    name: item?.name ?? "",
    description: item?.description ?? "",
    price: item ? paiseToRupeesInput(item.price_paise) : "",
    category_id: item?.category_id ?? categoryId ?? NONE,
    is_veg: item?.is_veg ?? true,
    is_available: item?.is_available ?? true,
    tags: item?.tags.join(", ") ?? "",
  };
}

export function ItemDialog({
  open,
  onOpenChange,
  item,
  defaultCategoryId,
  categories,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: ItemOut | null;
  defaultCategoryId: string | null;
  categories: CategoryOut[];
}) {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const form = useForm<ItemValues>({
    resolver: zodResolver(itemSchema),
    defaultValues: defaults(item, defaultCategoryId),
  });

  useEffect(() => {
    if (open) form.reset(defaults(item, defaultCategoryId));
  }, [open, item, defaultCategoryId, form]);

  const save = useMutation({
    mutationFn: (v: ItemValues) => {
      const body = {
        name: v.name,
        description: v.description || null,
        price_paise: rupeesToPaise(v.price),
        category_id: v.category_id === NONE ? null : v.category_id,
        is_veg: v.is_veg,
        is_available: v.is_available,
        tags: v.tags
          .split(",")
          .map((t) => t.trim().toLowerCase())
          .filter(Boolean),
      };
      return item
        ? api<ItemOut>(`/menu/items/${item.id}`, { method: "PATCH", body })
        : api<ItemOut>("/menu/items", { body });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["menu"] });
      toast.success(item ? "Item updated" : "Item added");
      onOpenChange(false);
    },
    onError: (err) => {
      if (!applyApiFieldErrors(form, err, { price_paise: "price" })) toast.error(errorMessage(err));
    },
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api<ItemOut>(`/menu/items/${item!.id}/image`, { method: "POST", formData: fd });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["menu"] });
      toast.success("Photo updated");
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  const { errors, isSubmitting } = form.formState;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{item ? "Edit item" : "Add item"}</DialogTitle>
          <DialogDescription>
            Prices are in rupees. Customers see only available items.
          </DialogDescription>
        </DialogHeader>
        <form
          id="item-form"
          onSubmit={form.handleSubmit((v) => save.mutate(v))}
          className="grid gap-4"
          noValidate
        >
          <Field label="Name" htmlFor="item-name" error={errors.name?.message}>
            <Input id="item-name" {...form.register("name")} />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Price (₹)" htmlFor="item-price" error={errors.price?.message}>
              <Input id="item-price" inputMode="decimal" {...form.register("price")} />
            </Field>
            <Field label="Category" htmlFor="item-category">
              <select
                id="item-category"
                className="border-input dark:bg-input/30 h-9 rounded-md border bg-transparent px-3 text-sm"
                {...form.register("category_id")}
              >
                <option value={NONE}>Uncategorized</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Description" htmlFor="item-description" error={errors.description?.message}>
            <Textarea id="item-description" rows={3} {...form.register("description")} />
          </Field>
          <Field
            label="Tags"
            htmlFor="item-tags"
            error={errors.tags?.message}
            hint="Comma separated, e.g. eggless, gluten-free, bestseller"
          >
            <Input id="item-tags" {...form.register("tags")} />
          </Field>
          <div className="flex flex-wrap gap-6">
            <div className="flex items-center gap-2">
              <Controller
                control={form.control}
                name="is_veg"
                render={({ field }) => (
                  <Checkbox
                    id="item-veg"
                    checked={field.value}
                    onCheckedChange={(v) => field.onChange(v === true)}
                  />
                )}
              />
              <Label htmlFor="item-veg">Vegetarian</Label>
            </div>
            <div className="flex items-center gap-2">
              <Controller
                control={form.control}
                name="is_available"
                render={({ field }) => (
                  <Switch
                    id="item-available"
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                )}
              />
              <Label htmlFor="item-available">Available</Label>
            </div>
          </div>
        </form>
        {item && (
          <div className="flex items-center gap-3 border-t pt-4">
            <div className="bg-muted flex size-16 items-center justify-center overflow-hidden rounded-md border">
              {item.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element -- already resized server-side
                <img src={item.image_url} alt={item.name} className="size-full object-cover" />
              ) : (
                <ImageUp className="text-muted-foreground size-5" aria-hidden />
              )}
            </div>
            <input
              ref={fileInput}
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
              type="button"
              variant="outline"
              size="sm"
              disabled={upload.isPending}
              onClick={() => fileInput.current?.click()}
            >
              {upload.isPending ? "Uploading…" : item.image_url ? "Change photo" : "Add photo"}
            </Button>
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="item-form" disabled={isSubmitting || save.isPending}>
            {save.isPending ? "Saving…" : item ? "Save" : "Add item"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
