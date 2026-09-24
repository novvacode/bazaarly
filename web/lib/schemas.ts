/** zod schemas mirroring backend validation (SPEC §14.2). */
import { z } from "zod";

import { rupeesToPaise } from "./money";

export const SLUG_RE = /^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$/;

export const passwordSchema = z
  .string()
  .min(8, "At least 8 characters")
  .max(128, "At most 128 characters");

export const loginSchema = z.object({
  email: z.email("Enter a valid email"),
  password: z.string().min(1, "Enter your password"),
});
export type LoginValues = z.infer<typeof loginSchema>;

export const signupSchema = z.object({
  name: z.string().trim().min(1, "Enter your name").max(100),
  email: z.email("Enter a valid email"),
  password: passwordSchema,
  business_name: z.string().trim().min(1, "Enter your business name").max(100),
  slug: z
    .string()
    .trim()
    .toLowerCase()
    .regex(SLUG_RE, "3–40 lowercase letters, digits or hyphens")
    .refine((s) => !s.includes("--"), "No consecutive hyphens"),
});
export type SignupValues = z.infer<typeof signupSchema>;

export const rupeesField = z
  .string()
  .trim()
  .refine((v) => rupeesToPaise(v) !== null, "Enter an amount like 650 or 650.50");

export const settingsSchema = z
  .object({
    name: z.string().trim().min(1, "Required").max(100),
    description: z.string().max(2000),
    phone: z.string().max(20),
    email: z.union([z.literal(""), z.email("Enter a valid email")]),
    address: z.string().max(200),
    hours_text: z.string().max(200),
    accepts_orders: z.boolean(),
    pickup: z.boolean(),
    delivery: z.boolean(),
    delivery_areas: z.string().max(3000),
    min_order: rupeesField,
    delivery_fee: rupeesField,
    timezone: z.string().min(1),
  })
  .refine((v) => v.pickup || v.delivery, {
    message: "Offer at least one of pickup or delivery",
    path: ["pickup"],
  });
export type SettingsValues = z.infer<typeof settingsSchema>;

/** Turn a free-text slug suggestion from a business name. */
export function suggestSlug(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-")
    .slice(0, 40)
    .replace(/-+$/g, "");
}
