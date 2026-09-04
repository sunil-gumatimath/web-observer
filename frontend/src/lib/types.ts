export type MonitorMode =
  | "page_content"
  | "site_links"
  | "product_price"
  | "list_items"
  | "json_field"
  | "rss_feed"
  | "readme"
  | "visual";

export type Monitor = {
  id: string;
  workspace_id: string;
  name: string;
  url: string;
  mode: MonitorMode;
  css_selector: string | null;
  schedule_interval_minutes: number;
  timezone: string;
  next_run_at: string;
  enabled: boolean;
  config_version: number;
  js_required?: boolean;
  watch_note?: string | null;
  semantic_trigger?: string | null;
  ignore_selectors?: string[] | null;
  ignore_regexes?: string[] | null;
  alert_config?: Record<string, unknown> | null;
  consecutive_failures?: number;
  screenshots_enabled?: boolean;
  brand?: MonitorBrand | null;
  created_at: string;
  latest_change: LatestChange | null;
};

export type MonitorBrand = {
  title?: string | null;
  description?: string | null;
  logo_path?: string | null;
  hero_path?: string | null;
  logo_url?: string | null;
  hero_url?: string | null;
};

export type BrandInfo = {
  title: string | null;
  description: string | null;
  logo_url: string | null;
  hero_url: string | null;
  assets_available: boolean;
};

export type SelectorPreview = {
  final_url: string;
  html: string;
  truncated: boolean;
};

export type LatestChange = {
  id: string;
  change_category: string | null;
  ai_summary: string | null;
  diff_summary: string | null;
  title?: string | null;
  impact?: string | null;
  confidence?: number | null;
  is_read: boolean;
  is_noise: boolean;
  created_at: string;
};

export type MonitorRun = {
  id: string;
  monitor_id: string;
  workspace_id: string;
  config_version: number;
  status: string;
  attempt: number;
  scheduled_at: string;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  http_status: number | null;
  latency_ms: number | null;
  content_hash: string | null;
  snapshot_id: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
};

export type ChangeEvent = {
  id: string;
  workspace_id: string;
  monitor_id: string;
  run_id: string;
  previous_snapshot_id: string | null;
  new_snapshot_id: string;
  previous_hash: string | null;
  new_hash: string;
  diff_summary: string | null;
  ai_summary?: string | null;
  change_category?: string | null;
  title?: string | null;
  impact?: string | null;
  confidence?: number | null;
  is_noise?: boolean;
  is_read?: boolean;
  created_at: string;
};

export type AlertInboxItem = ChangeEvent & {
  monitor_name: string;
  monitor_url: string;
  monitor_brand?: MonitorBrand | null;
};

export type AlertsSummary = {
  total: number;
  unread: number;
  noise: number;
};

export type ChangeEventDetail = ChangeEvent & {
  diff: string | null;
  previous_text: string | null;
  new_text: string | null;
  mode: string | null;
};

export type Usage = {
  workspace_id: string;
  period_start: string;
  checks_count: number;
  checks_limit: number;
  notifications_count: number;
  storage_bytes: number;
  max_monitors: number;
  min_check_interval_minutes: number;
};

export type SeedResponse = {
  user_id: string;
  workspace_id: string;
  email: string;
};

export type MonitorCreateInput = {
  name: string;
  url: string;
  mode: MonitorMode;
  css_selector?: string | null;
  schedule_interval_minutes: number;
  timezone?: string;
  notification_email?: string;
  js_required?: boolean;
  watch_note?: string | null;
  semantic_trigger?: string | null;
  ignore_selectors?: string[] | null;
  ignore_regexes?: string[] | null;
  alert_config?: Record<string, unknown> | null;
  screenshots_enabled?: boolean;
  run_now?: boolean;
};
export type MonitorUpdateInput = {
  name?: string;
  url?: string;
  mode?: MonitorMode;
  css_selector?: string | null;
  schedule_interval_minutes?: number;
  timezone?: string;
  timeout_seconds?: number;
  enabled?: boolean;
  js_required?: boolean;
  watch_note?: string | null;
  semantic_trigger?: string | null;
  ignore_selectors?: string[] | null;
  ignore_regexes?: string[] | null;
  alert_config?: Record<string, unknown> | null;
  screenshots_enabled?: boolean;
};

export type NotificationChannel = {
  id: string;
  workspace_id: string;
  type: string;
  address: string;
  enabled: boolean;
  created_at: string;
};

export type SnapshotAccess = {
  id: string;
  content_hash: string;
  content_type: string | null;
  byte_size: number | null;
  normalized_text: string;
  created_at: string;
};

export type BulkImportResponse = {
  created: Array<{ id: string; name: string; url: string }>;
  skipped: Array<{ url: string; reason: string }>;
  errors: Array<{ row: number; url: string | null; error: string }>;
  created_count: number;
};

export type ApiKeyCreated = {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  raw_key: string;
};

export type WebhookOut = {
  id: string;
  url: string;
  enabled: boolean;
  created_at: string;
  secret: string | null;
};

export type WebhookDelivery = {
  id: string;
  endpoint_id: string;
  event_type: string;
  status: "pending" | "processing" | "sent" | "failed";
  response_code: number | null;
  attempts: number;
  last_error: string | null;
  created_at: string;
};

export type SitemapDiscovery = {
  url: string;
  urls: string[];
  count: number;
};

export type SitemapImportResult = {
  created: string[];
  skipped: Array<{ row: string; reason?: string; url?: string }>;
  errors: Array<{ row: string; error: string }>;
  created_count: number;
};

export type ShareLinkCreated = {
  id: string;
  monitor_id: string;
  token: string;
  url: string;
  enabled: boolean;
  expires_at: string | null;
  created_at: string;
  note?: string | null;
};

export type ShareLinkRow = {
  id: string;
  monitor_id: string;
  token_prefix: string;
  enabled: boolean;
  expires_at: string | null;
  created_at: string;
};

export type InviteCreated = {
  id: string;
  token: string;
  url: string;
  role: string;
  max_uses: number;
  use_count: number;
  expires_at: string | null;
  created_at: string;
};

export type InviteRow = {
  id: string;
  token_prefix: string;
  role: string;
  max_uses: number;
  use_count: number;
  expires_at: string | null;
  created_at: string;
};

export type WorkspaceSettings = {
  workspace_id: string;
  ai_summaries_enabled: boolean;
  as_llm_api_key: boolean;
  llm_api_base: string | null;
  llm_model: string | null;
  as_resend_api_key: boolean;
  email_from: string | null;
};

export type PublicShareAlert = {
  id: string;
  change_category: string | null;
  ai_summary: string | null;
  diff_summary: string | null;
  diff: string | null;
  new_hash: string;
  previous_hash: string | null;
  created_at: string;
};

export type PublicShare = {
  monitor: {
    monitor_id: string;
    name: string;
    url: string;
    mode: string;
    watch_note: string | null;
    brand: MonitorBrand | null;
  };
  alerts: PublicShareAlert[];
  total: number;
};

export type InvitePreview = {
  invite_id: string;
  workspace_id: string;
  workspace_name: string;
  role: string;
};

export type InviteRedeem = {
  workspace_id: string;
  workspace_name: string;
  role: string;
  message: string;
};

export type ApiKeyRow = {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};

export type WorkspaceMemberRow = {
  user_id: string;
  email: string | null;
  role: string;
};

export type AuditLogRow = {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  actor_email: string | null;
  meta: Record<string, unknown> | null;
  created_at: string;
};
