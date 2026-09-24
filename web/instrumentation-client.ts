// Browser error reporting (SPEC §18): a no-op unless NEXT_PUBLIC_SENTRY_DSN is set. The SDK is
// loaded lazily so pages without a DSN don't pay for it.
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  import("@sentry/nextjs")
    .then((Sentry) =>
      Sentry.init({
        dsn,
        environment: process.env.NEXT_PUBLIC_APP_ENV ?? "production",
        tracesSampleRate: 0.1,
      }),
    )
    .catch(() => {
      // Monitoring must never break the app.
    });
}
