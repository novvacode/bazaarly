import {
  BarChart3,
  Bot,
  ClipboardList,
  HelpCircle,
  LayoutDashboard,
  Settings,
  UtensilsCrossed,
  Users,
  type LucideIcon,
} from "lucide-react";

import type { Role } from "@/lib/types";

export type NavItem = { href: string; label: string; icon: LucideIcon; roles: Role[] };

export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Order board", icon: LayoutDashboard, roles: ["owner", "staff"] },
  { href: "/dashboard/orders", label: "Orders", icon: ClipboardList, roles: ["owner", "staff"] },
  { href: "/dashboard/menu", label: "Menu", icon: UtensilsCrossed, roles: ["owner", "staff"] },
  { href: "/dashboard/faq", label: "FAQ", icon: HelpCircle, roles: ["owner"] },
  { href: "/dashboard/assistant", label: "Assistant", icon: Bot, roles: ["owner"] },
  { href: "/dashboard/analytics", label: "Analytics", icon: BarChart3, roles: ["owner"] },
  { href: "/dashboard/settings", label: "Settings", icon: Settings, roles: ["owner"] },
  { href: "/dashboard/team", label: "Team", icon: Users, roles: ["owner"] },
];
