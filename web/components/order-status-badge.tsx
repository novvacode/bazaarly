import { STATUS_LABEL, STATUS_TONE } from "@/lib/orders";
import type { OrderStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export function OrderStatusBadge({
  status,
  className,
}: {
  status: OrderStatus;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        STATUS_TONE[status],
        className,
      )}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}
