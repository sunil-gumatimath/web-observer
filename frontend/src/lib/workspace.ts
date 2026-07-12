import { api } from "@/lib/api";
import { config } from "@/lib/config";

const STORAGE_KEY = "mtw_workspace_id";

export function getStoredWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
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
}

/**
 * Resolve the active workspace:
 * - Clerk mode: GET /me (auto-provisions default workspace)
 * - Dev mode: seed internal workspace if needed
 */
export async function ensureWorkspace(): Promise<string> {
  if (config.clerkEnabled) {
    const me = await api.me();
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
}
