import type { Metadata } from "next";

export const metadata: Metadata = { title: "Platform admin", robots: { index: false } };

export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return <div className="mx-auto w-full max-w-6xl p-4 md:p-6">{children}</div>;
}
