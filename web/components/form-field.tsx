"use client";

import type { FieldValues, Path, UseFormReturn } from "react-hook-form";

import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export function Field({
  label,
  htmlFor,
  error,
  hint,
  className,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("grid gap-2", className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {error ? (
        <p id={`${htmlFor}-error`} className="text-destructive text-sm" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-muted-foreground text-xs">{hint}</p>
      ) : null}
    </div>
  );
}

/**
 * Copy API field errors (`details.fields`) onto a react-hook-form instance.
 * Returns true if at least one field error was applied.
 */
export function applyApiFieldErrors<T extends FieldValues>(
  form: UseFormReturn<T>,
  err: unknown,
  rename: Record<string, Path<T>> = {},
): boolean {
  if (!(err instanceof ApiError)) return false;
  let applied = false;
  for (const [field, message] of Object.entries(err.fields)) {
    const name = (rename[field] ?? field) as Path<T>;
    if (name in form.getValues()) {
      form.setError(name, { message });
      applied = true;
    }
  }
  return applied;
}
