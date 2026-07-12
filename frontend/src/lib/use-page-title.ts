"use client";

import { useEffect } from "react";

const BASE = "Web Observer";

/**
 * Set the browser tab title for a client-rendered page.
 * Restores the base title on unmount so navigating away doesn't leak the old label.
 */
export function usePageTitle(title: string | null) {
  useEffect(() => {
    if (!title) return;
    document.title = `${title} · ${BASE}`;
    return () => {
      document.title = BASE;
    };
  }, [title]);
}
