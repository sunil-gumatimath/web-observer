import { getAuthToken } from "@/lib/auth-token";
import { config } from "@/lib/config";
import type {
  AlertInboxItem,
  AlertsSummary,
  ApiKeyCreated,
  BulkImportResponse,
  ChangeEvent,
  ChangeEventDetail,
  Monitor,
  MonitorCreateInput,
  MonitorRun,
  MonitorUpdateInput,
  NotificationChannel,
  SeedResponse,
  SnapshotAccess,
  Usage,
  WebhookOut,
} from "@/lib/types";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export type MeResponse = {
  id: string | null;
  email: string | null;
  clerk_user_id: string | null;
  is_internal: boolean;
  workspaces: Array<{ id: string; name: string; created_at: string }>;
};

async function waitForClerkToken(maxAttempts = 30, delayMs = 100): Promise<string | null> {
  // ClerkTokenBridge may not be mounted yet on the first paint; poll briefly (~3s).
  // Each getAuthToken() itself times out so a hung Clerk getToken cannot block forever.
  for (let i = 0; i < maxAttempts; i++) {
    const token = await getAuthToken();
    if (token) return token;
    await new Promise((r) => setTimeout(r, delayMs));
  }
  return null;
}

async function authHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (config.clerkEnabled) {
    // Never fall back to the internal token while Clerk is enabled — that would
    // expose every workspace (including seeded "Dev Workspace") via /me and then
    // 404 on membership-scoped routes once the real JWT is used.
    const token = await waitForClerkToken();
    if (!token) {
      throw new ApiError(401, "Not signed in (missing Clerk session token)", {
        detail: "Not signed in",
      });
    }
    headers.Authorization = `Bearer ${token}`;
    return headers;
  }

  // Dev / smoke fallback (Clerk disabled)
  headers["X-Internal-Token"] = config.internalToken;
  return headers;
}

const FETCH_TIMEOUT_MS = 20_000;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await authHeaders();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  // Honour caller abort if provided
  const parentSignal = init?.signal;
  if (parentSignal) {
    if (parentSignal.aborted) controller.abort();
    else parentSignal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  let res: Response;
  try {
    res = await fetch(`${config.apiBaseUrl}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        ...headers,
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError(0, `Request timed out after ${FETCH_TIMEOUT_MS / 1000}s: ${path}`, {
        detail: "timeout",
      });
    }
    throw new ApiError(
      0,
      err instanceof Error ? err.message : `Network error calling ${path}`,
      { detail: "network_error" },
    );
  } finally {
    clearTimeout(timer);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    const message =
      typeof body === "object" && body && "detail" in body
        ? JSON.stringify((body as { detail: unknown }).detail)
        : res.statusText;
    throw new ApiError(res.status, message, body);
  }

  return body as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>("/health"),

  me: () => request<MeResponse>("/api/v1/me"),

  listWorkspaces: () =>
    request<Array<{ id: string; name: string; created_at: string }>>("/api/v1/workspaces"),

  createWorkspace: (name: string) =>
    request<{ id: string; name: string; created_at: string }>("/api/v1/workspaces", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  seed: () => request<SeedResponse>("/api/v1/internal/seed", { method: "POST" }),

  listMonitors: (workspaceId: string) =>
    request<Monitor[]>(`/api/v1/workspaces/${workspaceId}/monitors`),

  getMonitor: (workspaceId: string, monitorId: string) =>
    request<Monitor>(`/api/v1/workspaces/${workspaceId}/monitors/${monitorId}`),

  createMonitor: (workspaceId: string, body: MonitorCreateInput) =>
    request<Monitor>(`/api/v1/workspaces/${workspaceId}/monitors`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateMonitor: (workspaceId: string, monitorId: string, body: MonitorUpdateInput) =>
    request<Monitor>(`/api/v1/workspaces/${workspaceId}/monitors/${monitorId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  pauseMonitor: (workspaceId: string, monitorId: string) =>
    request<Monitor>(`/api/v1/workspaces/${workspaceId}/monitors/${monitorId}/pause`, {
      method: "POST",
    }),

  resumeMonitor: (workspaceId: string, monitorId: string) =>
    request<Monitor>(`/api/v1/workspaces/${workspaceId}/monitors/${monitorId}/resume`, {
      method: "POST",
    }),

  deleteMonitor: (workspaceId: string, monitorId: string) =>
    request<void>(`/api/v1/workspaces/${workspaceId}/monitors/${monitorId}`, {
      method: "DELETE",
    }),

  runMonitor: (workspaceId: string, monitorId: string) =>
    request<{ run_id: string; status: string; message: string }>(
      `/api/v1/workspaces/${workspaceId}/monitors/${monitorId}/run`,
      { method: "POST" },
    ),

  listRuns: (workspaceId: string, monitorId: string) =>
    request<MonitorRun[]>(`/api/v1/workspaces/${workspaceId}/monitors/${monitorId}/runs`),

  getSnapshot: (workspaceId: string, snapshotId: string) =>
    request<SnapshotAccess>(`/api/v1/workspaces/${workspaceId}/snapshots/${snapshotId}`),

  listChanges: (workspaceId: string, monitorId: string) =>
    request<ChangeEvent[]>(`/api/v1/workspaces/${workspaceId}/monitors/${monitorId}/changes`),

  getChange: (workspaceId: string, changeId: string) =>
    request<ChangeEventDetail>(`/api/v1/workspaces/${workspaceId}/changes/${changeId}`),

  listAlerts: (
    workspaceId: string,
    opts?: { unread_only?: boolean; include_noise?: boolean; limit?: number },
  ) => {
    const q = new URLSearchParams();
    if (opts?.unread_only) q.set("unread_only", "true");
    if (opts?.include_noise) q.set("include_noise", "true");
    if (opts?.limit) q.set("limit", String(opts.limit));
    const qs = q.toString();
    return request<AlertInboxItem[]>(
      `/api/v1/workspaces/${workspaceId}/alerts${qs ? `?${qs}` : ""}`,
    );
  },

  alertsSummary: (workspaceId: string) =>
    request<AlertsSummary>(`/api/v1/workspaces/${workspaceId}/alerts/summary`),

  markChangeRead: (workspaceId: string, changeId: string, isRead = true) =>
    request<ChangeEvent>(`/api/v1/workspaces/${workspaceId}/changes/${changeId}/read`, {
      method: "POST",
      body: JSON.stringify({ is_read: isRead }),
    }),

  markAllAlertsRead: (workspaceId: string) =>
    request<AlertsSummary>(`/api/v1/workspaces/${workspaceId}/alerts/read-all`, {
      method: "POST",
    }),

  getUsage: (workspaceId: string) =>
    request<Usage>(`/api/v1/workspaces/${workspaceId}/usage`),

  listNotificationChannels: (workspaceId: string) =>
    request<NotificationChannel[]>(
      `/api/v1/workspaces/${workspaceId}/notification-channels`,
    ),

  getWorkspace: (workspaceId: string) =>
    request<{
      id: string;
      name: string;
      digest_cadence: string;
      digest_hour_utc: number;
      ai_summaries_enabled: boolean;
      plan?: string;
      plan_status?: string;
    }>(`/api/v1/workspaces/${workspaceId}`),

  updateWorkspace: (
    workspaceId: string,
    body: {
      name?: string;
      digest_cadence?: string;
      digest_hour_utc?: number;
      ai_summaries_enabled?: boolean;
    },
  ) =>
    request<{
      id: string;
      name: string;
      digest_cadence: string;
      digest_hour_utc: number;
      ai_summaries_enabled: boolean;
      plan?: string;
    }>(`/api/v1/workspaces/${workspaceId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  createNotificationChannel: (
    workspaceId: string,
    body: { type?: string; address: string; enabled?: boolean },
  ) =>
    request<NotificationChannel>(
      `/api/v1/workspaces/${workspaceId}/notification-channels`,
      {
        method: "POST",
        body: JSON.stringify({ type: "email", enabled: true, ...body }),
      },
    ),

  markChangeNoise: (workspaceId: string, changeId: string, isNoise: boolean) =>
    request<ChangeEvent>(`/api/v1/workspaces/${workspaceId}/changes/${changeId}/noise`, {
      method: "POST",
      body: JSON.stringify({ is_noise: isNoise }),
    }),

  updateNotificationChannel: (
    workspaceId: string,
    channelId: string,
    body: { address?: string; enabled?: boolean },
  ) =>
    request<NotificationChannel>(
      `/api/v1/workspaces/${workspaceId}/notification-channels/${channelId}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      },
    ),

  deleteNotificationChannel: (workspaceId: string, channelId: string) =>
    request<void>(`/api/v1/workspaces/${workspaceId}/notification-channels/${channelId}`, {
      method: "DELETE",
    }),

  // Enterprise (Phase 6–7) — all go through the same authHeaders() so
  // Clerk JWT (or dev internal token) is attached consistently.
  bulkImportMonitors: (workspaceId: string, csvText: string) =>
    request<BulkImportResponse>(
      `/api/v1/workspaces/${workspaceId}/monitors/import`,
      { method: "POST", body: JSON.stringify({ csv_text: csvText }) },
    ),

  createApiKey: (workspaceId: string, name: string) =>
    request<ApiKeyCreated>(`/api/v1/workspaces/${workspaceId}/api-keys`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  createWebhook: (workspaceId: string, url: string) =>
    request<WebhookOut>(`/api/v1/workspaces/${workspaceId}/webhooks`, {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
};
