"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronsUpDown, ExternalLink, LogOut, Menu, Shield } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/auth";
import type { MeOut } from "@/lib/types";
import { cn } from "@/lib/utils";

import { NAV_ITEMS } from "./nav";

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { tenant } = useSession();
  const items = NAV_ITEMS.filter((i) => tenant && i.roles.includes(tenant.role));
  return (
    <nav className="grid gap-1" aria-label="Dashboard">
      {items.map(({ href, label, icon: Icon }) => {
        const active = href === "/dashboard" ? pathname === href : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function TenantSwitcher() {
  const { tenant, user, switchTenant, logout } = useSession();
  const router = useRouter();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<MeOut>("/auth/me") });
  const others = (me.data?.memberships ?? []).filter((m) => m.tenant.id !== tenant?.id);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-auto w-full justify-between px-3 py-2 text-left">
          <span className="min-w-0">
            <span className="block truncate font-semibold">{tenant?.name}</span>
            <span className="text-muted-foreground block truncate text-xs">
              {user?.email} · {tenant?.role}
            </span>
          </span>
          <ChevronsUpDown className="text-muted-foreground size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-64" align="start">
        {others.length > 0 && (
          <>
            <DropdownMenuLabel>Switch business</DropdownMenuLabel>
            {others.map((m) => (
              <DropdownMenuItem
                key={m.tenant.id}
                onSelect={async () => {
                  try {
                    await switchTenant(m.tenant.id);
                    router.push("/dashboard");
                  } catch (err) {
                    toast.error(errorMessage(err));
                  }
                }}
              >
                {m.tenant.name}
                <span className="text-muted-foreground ml-auto text-xs">{m.role}</span>
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
          </>
        )}
        {tenant && (
          <DropdownMenuItem asChild>
            <a href={`/b/${tenant.slug}`} target="_blank" rel="noreferrer">
              <ExternalLink /> View storefront
            </a>
          </DropdownMenuItem>
        )}
        {user?.is_platform_admin && (
          <DropdownMenuItem asChild>
            <Link href="/admin">
              <Shield /> Platform admin
            </Link>
          </DropdownMenuItem>
        )}
        <DropdownMenuItem
          onSelect={async () => {
            await logout();
            router.replace("/login");
          }}
        >
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const { status, tenant, user } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, router, pathname]);

  if (status !== "authenticated") {
    return (
      <div className="mx-auto grid w-full max-w-5xl gap-4 p-6">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!tenant) {
    return (
      <div className="mx-auto max-w-md p-8 text-center">
        <h1 className="text-xl font-semibold">No business yet</h1>
        <p className="text-muted-foreground mt-2 text-sm">
          Your account isn&apos;t a member of any business. Ask an owner for an invite link, or
          create a new store.
        </p>
        <div className="mt-4 flex justify-center gap-2">
          {user?.is_platform_admin && (
            <Button asChild>
              <Link href="/admin">Platform admin</Link>
            </Button>
          )}
          <Button asChild variant={user?.is_platform_admin ? "outline" : "default"}>
            <Link href="/signup">Create a store</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh w-full">
      <aside className="bg-card hidden w-64 shrink-0 flex-col gap-4 border-r p-3 md:flex">
        <Link href="/dashboard" className="text-primary px-3 pt-2 text-lg font-bold">
          Bazaarly
        </Link>
        <TenantSwitcher />
        <NavLinks />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="bg-card sticky top-0 z-30 flex items-center gap-2 border-b px-4 py-2 md:hidden">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Open menu">
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="gap-4 p-3">
              <SheetTitle className="text-primary px-3 pt-2 text-lg font-bold">Bazaarly</SheetTitle>
              <TenantSwitcher />
              <NavLinks onNavigate={() => setOpen(false)} />
            </SheetContent>
          </Sheet>
          <span className="truncate font-semibold">{tenant.name}</span>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {description && <p className="text-muted-foreground mt-1 text-sm">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
