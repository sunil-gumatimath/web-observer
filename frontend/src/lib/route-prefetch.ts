import { api } from "@/lib/api";
import { fetchCached } from "@/lib/query-cache";
import { ensureWorkspace, getCachedMe } from "@/lib/workspace";

const PREFETCH_MAX_AGE_MS = 10_000;

export const cacheKeys = {
  me: () => "me",
  health: () => "health",
  workspace: (ws: string) => `workspace:${ws}`,
  workspaceSettings: (ws: string) => `workspaceSettings:${ws}`,
  modelCatalog: () => "modelCatalog",
  monitors: (ws: string) => `monitors:${ws}`,
  usage: (ws: string) => `usage:${ws}`,
  alertsSummary: (ws: string) => `alertsSummary:${ws}`,
  alertsSignal: (ws: string, limit: number) => `alerts:${ws}:signal:${limit}`,
  alertsNoise: (ws: string, limit: number) => `alerts:${ws}:noise:${limit}`,
  alertsUnread: (ws: string, limit: number) => `alerts:${ws}:unread:${limit}`,
  channels: (ws: string) => `channels:${ws}`,
  activity: (ws: string, days: number) => `activity:${ws}:${days}`,
  runLogs: (
    ws: string,
    filters: {
      monitorId: string;
      outcome: string;
      from: string;
      to: string;
      limit: number;
    },
  ) =>
    `runLogs:${ws}:${filters.monitorId}:${filters.outcome}:${filters.from}:${filters.to}:${filters.limit}`,
  members: (ws: string) => `members:${ws}`,
  invites: (ws: string) => `invites:${ws}`,
  apiKeys: (ws: string) => `apiKeys:${ws}`,
  webhooks: (ws: string) => `webhooks:${ws}`,
  webhookDeliveries: (ws: string) => `webhookDeliveries:${ws}`,
  auditLogs: (ws: string) => `auditLogs:${ws}`,
};

/**
 * Warm the client cache when the user hovers or focuses a top-nav tab so
 * clicking into that route has data ready (or already in flight).
 */
export function prefetchRouteData(href: string): void {
  if (typeof window === "undefined") return;
  void (async () => {
    try {
      const ws = await ensureWorkspace();
      const opts = { maxAgeMs: PREFETCH_MAX_AGE_MS };

      if (href === "/dashboard") {
        await Promise.allSettled([
          fetchCached(cacheKeys.monitors(ws), () => api.listMonitors(ws), opts),
          fetchCached(cacheKeys.usage(ws), () => api.getUsage(ws), opts),
          fetchCached(cacheKeys.alertsSummary(ws), () => api.alertsSummary(ws), opts),
          fetchCached(cacheKeys.channels(ws), () => api.listNotificationChannels(ws), opts),
          fetchCached(cacheKeys.activity(ws, 14), () => api.getChangeActivity(ws, { days: 28 }), opts),
        ]);
      } else if (href === "/monitors") {
        await fetchCached(cacheKeys.monitors(ws), () => api.listMonitors(ws), opts);
      } else if (href === "/logs") {
        await Promise.allSettled([
          fetchCached(
            cacheKeys.runLogs(ws, {
              monitorId: "all",
              outcome: "all",
              from: "",
              to: "",
              limit: 50,
            }),
            () => api.listRunLogs(ws, { limit: 50 }),
            opts,
          ),
          fetchCached(cacheKeys.monitors(ws), () => api.listMonitors(ws), opts),
        ]);
      } else if (href === "/alerts") {
        await Promise.allSettled([
          fetchCached(
            cacheKeys.alertsSignal(ws, 100),
            () => api.listAlerts(ws, { unread_only: false, include_noise: false, limit: 100 }),
            opts,
          ),
          fetchCached(cacheKeys.alertsSummary(ws), () => api.alertsSummary(ws), opts),
          fetchCached(cacheKeys.monitors(ws), () => api.listMonitors(ws), opts),
        ]);
      } else if (href === "/settings") {
        await Promise.allSettled([
          getCachedMe(opts),
          fetchCached(cacheKeys.workspace(ws), () => api.getWorkspace(ws), opts),
          fetchCached(cacheKeys.workspaceSettings(ws), () => api.getWorkspaceSettings(ws), opts),
          fetchCached(cacheKeys.modelCatalog(), () => api.getModelCatalog(), opts),
          fetchCached(cacheKeys.channels(ws), () => api.listNotificationChannels(ws), opts),
          fetchCached(cacheKeys.invites(ws), () => api.listInvites(ws), opts),
          fetchCached(cacheKeys.members(ws), () => api.listMembers(ws), opts),
          fetchCached(cacheKeys.apiKeys(ws), () => api.listApiKeys(ws), opts),
          fetchCached(cacheKeys.webhooks(ws), () => api.listWebhooks(ws), opts),
          fetchCached(cacheKeys.webhookDeliveries(ws), () => api.listWebhookDeliveries(ws, { limit: 50 }), opts),
        ]);
      } else if (href === "/activity") {
        await Promise.allSettled([
          getCachedMe(opts),
          fetchCached(cacheKeys.members(ws), () => api.listMembers(ws), opts),
          fetchCached(cacheKeys.auditLogs(ws), () => api.listAuditLogs(ws, { limit: 100 }), opts),
        ]);
      }
    } catch {
      // Prefetch is strictly opportunistic.
    }
  })();
}
