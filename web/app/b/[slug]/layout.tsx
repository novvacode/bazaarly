import { CartProvider } from "@/components/storefront/cart";

export default async function StoreLayout({ children, params }: LayoutProps<"/b/[slug]">) {
  const { slug } = await params;
  return <CartProvider slug={slug.toLowerCase()}>{children}</CartProvider>;
}
