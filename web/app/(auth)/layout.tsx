import Link from "next/link";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="bg-muted/40 flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-10">
      <Link href="/" className="text-primary text-lg font-bold tracking-tight">
        Bazaarly
      </Link>
      <div className="w-full max-w-md">{children}</div>
    </div>
  );
}
