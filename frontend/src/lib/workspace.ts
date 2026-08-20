import { api } from "@/lib/api";
import { getClerkUserId, setClerkUserId } from "@/lib/auth-token";
import { config } from "@/lib/config";

const STORAGE_KEY = "web_observer_workspace_id";
const LEGACY_STORAGE_KEY = "mtw_workspace_id";

function migrateWorkspaceKey() {
  if (typeof window === "undefined") return;
  const legacy = localStorage.getItem(LEGACY_STORAGE_KEY);
  if (legacy && !localStorage.getItem(STORAGE_KEY)) {
    localStorage.setItem(STORAGE_KEY, legacy);
  }
}

export function getStoredWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
  migrateWorkspaceKey();
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored) return stored;
  // Only use the seeded dev workspace id when Clerk is off.
  if (!config.clerkEnabled && config.devWorkspaceId) {
    return config.devWorkspaceId;
  }
  return null;
}

export function setStoredWorkspaceId(id: string) {
  localStorage.setItem(STORAGE_KEY, id);
  localStorage.removeItem(LEGACY_STORAGE_KEY);
}

/**
 * Resolve the active workspace:
 * - Clerk mode: GET /me (auto-provisions default workspace)
 * - Dev mode: seed internal workspace if needed
 *
 * Concurrent callers within the same tick share the in-flight promise so we
 * don't fire N redundant /me (or seed) requests on a single page mount.
 * Call `invalidateWorkspace()` to force a re-resolution.
 *
 * The cache is keyed by the current Clerk user id: if the user changes (or
 * signs out) between calls, the cached promise and the stored workspace id are
 * discarded so user B can never see user A's workspace.
 */
let workspacePromise: Promise<string> | null = null;
let workspacePromiseUid: string | null = null;

export function invalidateWorkspace(): void {
  workspacePromise = null;
  workspacePromiseUid = null;
  if (typeof window !== "undefined") {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {}
  }
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === STORAGE_KEY && e.newValue === null) invalidateWorkspace();
  });
}

export async function ensureWorkspace(): Promise<string> {
  // Drop any cache that belongs to a different (or now signed-out) user before
  // trusting it. This is the safety net when Clerk's user changes without an
  // explicit invalidateWorkspace() call.
  if (config.clerkEnabled) {
    const uid = getClerkUserId();
    if (workspacePromise && workspacePromiseUid !== uid) {
      invalidateWorkspace();
      // The previously stored workspace id belonged to the other user; don't
      // reuse it as a "preferred" id for the new user.
      if (typeof window !== "undefined") localStorage.removeItem(STORAGE_KEY);
    }
  }

  if (workspacePromise) return workspacePromise;

  const requestUid = config.clerkEnabled ? getClerkUserId() : null;
  workspacePromiseUid = requestUid;

  workspacePromise = (async () => {
    if (config.clerkEnabled) {
      const me = await api.me();
      // Keep the tracked user id in sync with the authenticated identity and
      // re-tag the cache so a subsequent user switch is detected.
      setClerkUserId(me.clerk_user_id);
      workspacePromiseUid = me.clerk_user_id;
      if (me.workspaces.length > 0) {
        // Prefer a previously chosen id only if the user is still a member.
        // Never use NEXT_PUBLIC_DEV_WORKSPACE_ID here — that is the internal seed workspace.
        const preferred = localStorage.getItem(STORAGE_KEY);
        const match = preferred
          ? me.workspaces.find((w) => w.id === preferred)
          : undefined;
        const id = match?.id ?? me.workspaces[0].id;
        setStoredWorkspaceId(id);
        return id;
      }
      const created = await api.createWorkspace("My workspace");
      setStoredWorkspaceId(created.id);
      return created.id;
    }

    const existing = getStoredWorkspaceId();
    if (existing) {
      // Validate still accessible
      try {
        await api.getUsage(existing);
        return existing;
      } catch {
        // fall through to seed
      }
    }

    const seed = await api.seed();
    setStoredWorkspaceId(seed.workspace_id);
    return seed.workspace_id;
  })().catch((err) => {
    // Don't cache failures; let the next caller retry.
    workspacePromise = null;
    workspacePromiseUid = null;
    throw err;
  });

  return workspacePromise;
}
