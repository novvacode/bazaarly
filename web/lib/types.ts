/** API DTOs. Field names mirror the API (snake_case); see docs/DECISIONS.md D-010. */

export type Role = "owner" | "staff";

export type UserOut = {
  id: string;
  email: string;
  name: string;
  is_platform_admin: boolean;
};

export type TenantBrief = { id: string; name: string; slug: string };
export type ActiveTenant = TenantBrief & { role: Role };

export type AuthOut = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserOut;
  tenant: ActiveTenant | null;
};

export type MeOut = {
  user: UserOut;
  memberships: { tenant: TenantBrief; role: Role }[];
  active_tenant: ActiveTenant | null;
};

export type FulfillmentMode = "pickup" | "delivery";

export type TenantOut = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  logo_url: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  accepts_orders: boolean;
  fulfillment_modes: FulfillmentMode[];
  delivery_areas: string[];
  min_order_paise: number;
  delivery_fee_paise: number;
  hours_text: string | null;
  timezone: string;
};

export type MemberOut = {
  membership_id: string;
  user_id: string;
  name: string;
  email: string;
  role: Role;
  joined_at: string;
};

export type TeamOut = {
  members: MemberOut[];
  pending_invites: { id: string; role: Role; expires_at: string; created_at: string }[];
};

export type InviteCreatedOut = {
  id: string;
  url: string;
  token: string;
  role: Role;
  expires_at: string;
};

export type InvitePreviewOut = { business_name: string; role: Role; expires_at: string };

export type CategoryOut = { id: string; name: string; position: number };

export type ItemOut = {
  id: string;
  category_id: string | null;
  name: string;
  description: string | null;
  price_paise: number;
  image_url: string | null;
  is_available: boolean;
  is_veg: boolean;
  tags: string[];
  position: number;
};

export type FaqOut = { id: string; question: string; answer: string; position: number };

export type PublicItem = {
  id: string;
  name: string;
  description: string | null;
  price_paise: number;
  image_url: string | null;
  is_veg: boolean;
  tags: string[];
};

export type PublicBusiness = {
  name: string;
  slug: string;
  description: string | null;
  logo_url: string | null;
  phone: string | null;
  address: string | null;
  hours_text: string | null;
  accepts_orders: boolean;
  fulfillment_modes: FulfillmentMode[];
  delivery_areas: string[];
  min_order_paise: number;
  delivery_fee_paise: number;
};

export type StorefrontOut = {
  business: PublicBusiness;
  categories: { id: string | null; name: string; items: PublicItem[] }[];
};
