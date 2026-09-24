/**
 * API client (SPEC §14.2).
 *
 * - The access token lives in memory only.
 * - On a 401 the client refreshes once (one shared in-flight refresh per page) and retries once.
 * - Errors are mapped from the API's `{error: {code, message, details}}` envelope to `ApiError`.
 *
 * DTOs keep the API's snake_case field names (see docs/DECISIONS.md D-010).
 */

import type { AuthOut } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Field-level validation messages, e.g. `{password: "too short"}`. */
  get fields(): Record<string, string> {
    const fields = this.details.fields;
    return fields && typeof fields === "object" ? (fields as Record<string, string>) : {};
  }
}

let accessToken: string | null = null;
let refreshInFlight: Promise<AuthOut | null> | null = null;
const sessionListeners = new Set<(session: AuthOut | null) => void>();

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

/** Subscribe to session changes caused by refreshes inside the client. */
export function onSessionChange(listener: (session: AuthOut | null) => void) {
  sessionListeners.add(listener);
  return () => sessionListeners.delete(listener);
}

async function parseError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // Non-JSON error (e.g. proxy failure).
  }
  const err = (body as { error?: { code?: string; message?: string; details?: object } } | null)
    ?.error;
  return new ApiError(
    res.status,
    err?.code ?? "HTTP_ERROR",
    err?.message ?? `Request failed (${res.status})`,
    (err?.details as Record<string, unknown>) ?? {},
  );
}

/** Rotate the refresh cookie. Resolves to the new session or null when signed out. */
export function refreshSession(): Promise<AuthOut | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch("/api/v1/auth/refresh", {
          method: "POST",
          credentials: "same-origin",
        });
        if (!res.ok) {
          setAccessToken(null);
          return null;
        }
        const session = (await res.json()) as AuthOut;
        setAccessToken(session.access_token);
        return session;
      } catch {
        return null;
      } finally {
        // Let the next 401 trigger a fresh refresh.
        setTimeout(() => {
          refreshInFlight = null;
        }, 0);
      }
    })().then((session) => {
      sessionListeners.forEach((l) => l(session));
      return session;
    });
  }
  return refreshInFlight;
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  formData?: FormData;
  query?: Record<string, string | number | boolean | null | undefined>;
  auth?: boolean;
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

function buildUrl(path: string, query?: RequestOptions["query"]) {
  const url = path.startsWith("/api/") ? path : `/api/v1${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

async function send(path: string, opts: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
  let body: BodyInit | undefined;
  if (opts.formData) {
    body = opts.formData;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  if (opts.auth !== false && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return fetch(buildUrl(path, opts.query), {
    method: opts.method ?? (body ? "POST" : "GET"),
    headers,
    body,
    credentials: "same-origin",
    signal: opts.signal,
  });
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  let res = await send(path, opts);
  if (res.status === 401 && opts.auth !== false) {
    const session = await refreshSession();
    if (session) res = await send(path, opts);
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong";
}
