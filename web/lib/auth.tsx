"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { api, onSessionChange, refreshSession, setAccessToken } from "./api";
import type { ActiveTenant, AuthOut, UserOut } from "./types";

/** `idle` until a page that needs the session asks for it (public pages never do). */
type Status = "idle" | "loading" | "authenticated" | "anonymous";

type AuthContextValue = {
  status: Status;
  user: UserOut | null;
  tenant: ActiveTenant | null;
  /** Store a session returned by login/signup/invite-accept/switch-tenant. */
  setSession: (session: AuthOut) => void;
  login: (email: string, password: string) => Promise<AuthOut>;
  logout: () => Promise<void>;
  switchTenant: (tenantId: string) => Promise<void>;
  /** Start the silent refresh once; called by `useSession`. */
  ensure: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>("idle");
  const booted = useRef(false);
  const [user, setUser] = useState<UserOut | null>(null);
  const [tenant, setTenant] = useState<ActiveTenant | null>(null);

  const apply = useCallback((session: AuthOut | null) => {
    if (session) {
      setAccessToken(session.access_token);
      setUser(session.user);
      setTenant(session.tenant);
      setStatus("authenticated");
    } else {
      setAccessToken(null);
      setUser(null);
      setTenant(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    const unsubscribe = onSessionChange(apply);
    return () => {
      unsubscribe();
    };
  }, [apply]);

  // Bootstrap: try the refresh cookie once per page load (SPEC §8).
  const ensure = useCallback(() => {
    if (booted.current) return;
    booted.current = true;
    setStatus((s) => (s === "idle" ? "loading" : s));
    void refreshSession();
  }, []);

  const setSession = useCallback(
    (session: AuthOut) => {
      booted.current = true;
      apply(session);
      queryClient.clear();
    },
    [apply, queryClient],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await api<AuthOut>("/auth/login", {
        body: { email, password },
        auth: false,
      });
      setSession(session);
      return session;
    },
    [setSession],
  );

  const logout = useCallback(async () => {
    try {
      await api<void>("/auth/logout", { method: "POST", auth: false });
    } finally {
      apply(null);
      queryClient.clear();
    }
  }, [apply, queryClient]);

  const switchTenant = useCallback(
    async (tenantId: string) => {
      const session = await api<AuthOut>("/auth/switch-tenant", { body: { tenant_id: tenantId } });
      setSession(session);
    },
    [setSession],
  );

  const value = useMemo(
    () => ({ status, user, tenant, setSession, login, logout, switchTenant, ensure }),
    [status, user, tenant, setSession, login, logout, switchTenant, ensure],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Like `useAuth`, but also restores the session from the refresh cookie if needed. */
export function useSession(): AuthContextValue {
  const ctx = useAuth();
  const { ensure } = ctx;
  useEffect(() => {
    ensure();
  }, [ensure]);
  return ctx;
}
