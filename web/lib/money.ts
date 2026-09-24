/** Money is integer paise everywhere; format only at the UI edge (SPEC §4, §14.2). */

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

export function formatPaise(paise: number): string {
  return inr.format(paise / 100);
}

/** Parse a rupee amount typed by a user ("650", "650.50") into paise, or null if invalid. */
export function rupeesToPaise(input: string): number | null {
  const trimmed = input.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  const [whole, frac = ""] = trimmed.split(".");
  return Number(whole) * 100 + Number(frac.padEnd(2, "0"));
}

export function paiseToRupeesInput(paise: number): string {
  const whole = Math.floor(paise / 100);
  const frac = paise % 100;
  return frac ? `${whole}.${String(frac).padStart(2, "0")}` : String(whole);
}
