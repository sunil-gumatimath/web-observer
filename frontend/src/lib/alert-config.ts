/**
 * Monitor update payload helper. The backend PATCH treats a present
 * `alert_config` as authoritative, so it must always be sent — including when
 * the editor is blanked — otherwise clearing every threshold is a no-op.
 */
export function alertConfigPatch(
  alertConfig: Record<string, unknown> | null | undefined,
): { alert_config: Record<string, unknown> } {
  return { alert_config: alertConfig ?? {} };
}
