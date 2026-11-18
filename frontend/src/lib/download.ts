/** Client-side download helpers shared by the authenticated CSV/JSON exports. */

import type { ExportFormat } from "@/lib/api";

/** Stable, dated filename so repeated exports never overwrite each other. */
export function exportFileName(
  kind: string,
  format: ExportFormat,
  now: Date = new Date(),
): string {
  return `web-observer-${kind}-${now.toISOString().slice(0, 10)}.${format}`;
}

/**
 * Trigger a browser download of an already-fetched blob. The blob came from an
 * authenticated fetch (see `api.export*`), so no auth header is needed here —
 * and unlike window.open() this cannot lose the session on a navigation.
 */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Give the browser a tick to start the download before releasing the blob.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
