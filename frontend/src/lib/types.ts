export type MonitorMode =
  | "whole_page"
  | "css_selector"
  | "json_field"
  | "list_items"
  | "visual";

export type Monitor = {
  id: string;
  workspace_id: string;
  name: string;
  url: string;
  mode: string;
  css_selector: string | null;
  schedule_interval_minutes: number;
  timezone: string;
  next_run_at: string;
  enabled: boolean;
  config_version: number;
  js_required?: boolean;
  watch_note?: string | null;
  ignore_selectors?: string[] | null;
  ignore_regexes?: string[] | null;
  consecutive_failures?: number;
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
  is_noise?: boolean;
  is_read?: boolean;
  created_at: string;
};

export type AlertInboxItem = ChangeEvent & {
  monitor_name: string;
  monitor_url: string;
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
  ignore_selectors?: string[] | null;
  ignore_regexes?: string[] | null;
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
  ignore_selectors?: string[] | null;
  ignore_regexes?: string[] | null;
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

export type ScreenshotItem = {
  snapshot_id: string;
  run_id: string | null;
  captured_at: string;
  run_status: string | null;
  http_status: number | null;
  latency_ms: number | null;
  content_type: string | null;
  byte_size: number | null;
  ahash: string | null;
  distance_from_previous: number | null;
  is_first: boolean;
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
