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
  accepts_online_payments: boolean;
};

export type StorefrontOut = {
  business: PublicBusiness;
  categories: { id: string | null; name: string; items: PublicItem[] }[];
};

export type OrderStatus =
  | "pending_payment"
  | "placed"
  | "confirmed"
  | "preparing"
  | "ready"
  | "out_for_delivery"
  | "completed"
  | "cancelled";
export type PaymentMethod = "online" | "cod";
export type PaymentStatus = "pending" | "paid" | "failed" | "refunded";

export type Totals = { subtotal_paise: number; delivery_fee_paise: number; total_paise: number };

export type OrderItemOut = {
  menu_item_id: string | null;
  name: string;
  unit_price_paise: number;
  quantity: number;
  line_total_paise: number;
};

export type StatusEvent = {
  from_status: OrderStatus | null;
  to_status: OrderStatus;
  at: string;
  note: string | null;
};

export type PaymentParams = {
  key_id: string;
  razorpay_order_id: string;
  amount_paise: number;
  currency: string;
  name: string;
  prefill: Record<string, string>;
};

export type OrderCreatedOut = {
  order: {
    code: number;
    public_token: string;
    status: OrderStatus;
    payment_method: PaymentMethod;
    payment_status: PaymentStatus;
    totals: Totals;
  };
  tracking_url: string;
  payment: PaymentParams | null;
};

export type PublicOrderOut = {
  code: number;
  status: OrderStatus;
  fulfillment_mode: FulfillmentMode;
  payment_method: PaymentMethod;
  payment_status: PaymentStatus;
  customer_name: string;
  delivery_address: string | null;
  delivery_area: string | null;
  notes: string | null;
  items: OrderItemOut[];
  totals: Totals;
  timeline: StatusEvent[];
  business: { name: string; slug: string; phone: string | null; address: string | null };
  created_at: string;
  is_terminal: boolean;
  can_pay: boolean;
};

export type OrderSummary = {
  id: string;
  code: number;
  status: OrderStatus;
  customer_name: string;
  customer_phone: string;
  fulfillment_mode: FulfillmentMode;
  payment_method: PaymentMethod;
  payment_status: PaymentStatus;
  total_paise: number;
  item_count: number;
  created_at: string;
};

export type OrderListOut = { items: OrderSummary[]; next_cursor: string | null };

export type OrderDetail = OrderSummary & {
  public_token: string;
  customer_email: string | null;
  delivery_address: string | null;
  delivery_area: string | null;
  notes: string | null;
  items: OrderItemOut[];
  totals: Totals;
  timeline: StatusEvent[];
  allowed_transitions: OrderStatus[];
  refund_required: boolean;
};

export type DashboardSummary = {
  date: string;
  timezone: string;
  orders_total: number;
  orders_by_status: Partial<Record<OrderStatus, number>>;
  revenue_paise: number;
  top_items: { name: string; quantity: number; revenue_paise: number }[];
};

export type SalesOut = {
  days: number;
  timezone: string;
  series: { date: string; orders: number; revenue_paise: number }[];
  top_items: { name: string; quantity: number; revenue_paise: number }[];
};

export type AdminTenant = {
  id: string;
  name: string;
  slug: string;
  email: string | null;
  accepts_orders: boolean;
  created_at: string;
  members: number;
  orders: number;
  orders_last_7_days: number;
};

export type JobStats = {
  stream_length: number;
  pending: number;
  delayed: number;
  dead: number;
  consumers: { name: string; pending: number; idle_ms: number }[];
  counters: Record<string, number>;
};

export type DeadJob = {
  entry_id: string;
  type: string;
  payload: Record<string, unknown>;
  attempt: number;
  job_id: string | null;
  idempotency_key: string | null;
  error_type: string | null;
  error: string | null;
  traceback: string | null;
  failed_at: string | null;
};

export type AssistantReply = {
  answer: string;
  answered: boolean;
  sources: { type: "menu_item" | "faq" | "business_info"; title: string }[];
};

export type AssistantLog = {
  id: string;
  session_id: string;
  question: string;
  answer: string;
  answered: boolean;
  top_score: number | null;
  latency_ms: number;
  model: string;
  created_at: string;
};

export type AssistantLogList = { items: AssistantLog[]; next_cursor: string | null };
