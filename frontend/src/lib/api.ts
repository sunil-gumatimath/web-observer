import { getAuthToken } from "@/lib/auth-token";
import { config } from "@/lib/config";
import type {
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

async function waitForClerkToken(maxAttempts = 40, delayMs = 50): Promise<string | null> {
  // ClerkTokenBridge may not be mounted yet on the first paint; poll briefly.
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${config.apiBaseUrl}${path}`, {
    ...init,
    headers: {
      ...headers,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

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
};
