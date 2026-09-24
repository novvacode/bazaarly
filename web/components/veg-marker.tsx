import { cn } from "@/lib/utils";

/** The standard Indian veg (green) / non-veg (red) square marker. */
export function VegMarker({ isVeg, className }: { isVeg: boolean; className?: string }) {
  return (
    <span
      role="img"
      aria-label={isVeg ? "Vegetarian" : "Non-vegetarian"}
      title={isVeg ? "Vegetarian" : "Non-vegetarian"}
      className={cn(
        "inline-flex size-3.5 shrink-0 items-center justify-center rounded-[2px] border-[1.5px] bg-white",
        isVeg ? "border-green-700" : "border-red-700",
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", isVeg ? "bg-green-700" : "bg-red-700")} />
    </span>
  );
}
