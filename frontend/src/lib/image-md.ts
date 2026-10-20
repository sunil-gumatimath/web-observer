/**
 * Shared parsing of inline markdown images found in snapshot text
 * (`![alt](src)` tokens, optionally wrapped in links `[…](href)`).
 *
 * Used by ReadableContent (monitor preview) and GithubDiff (change alerts)
 * so captured images render visually instead of as raw markdown soup.
 */

export type LineSegment =
  | { type: "text"; value: string }
  | { type: "image"; alt: string; src: string };

/** One markdown image token: ![alt](src) — src must not contain spaces/')' */
const IMG_TOKEN_SRC = String.raw`!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)`;
/** A markdown link whose body is one or more image tokens: [![a](u1)![](u2)](href) */
const LINKED_GROUP_SRC = String.raw`\[((?:${IMG_TOKEN_SRC})(?:\s|"[^"]*")?)+\]\([^)\s]*\)`;

/** Sticky variants let us walk a line left-to-right unambiguously. */
const GROUP_Y = new RegExp(LINKED_GROUP_SRC, "y");
const TOKEN_Y = new RegExp(IMG_TOKEN_SRC, "y");

/** Resolve a (possibly relative) image URL against the monitored page URL. */
export function resolveImageUrl(src: string, baseUrl?: string): string | null {
  // Explicit allow-list — never render javascript:/blob:/data:text etc.
  if (/^data:image\//i.test(src)) return src;
  try {
    if (/^https?:\/\//i.test(src)) return src;
    if (!baseUrl) return null;
    return new URL(src, baseUrl).toString();
  } catch {
    return null;
  }
}

/**
 * Base URL used to resolve relative asset paths inside a repo README.
 *
 * A README on GitHub references sibling files relatively (`docs/logo.png`),
 * but those live on `raw.githubusercontent.com`, not on `github.com`. The
 * branch is taken from the monitor URL when it was pinned (`/tree/<branch>`),
 * otherwise `HEAD` resolves to the default branch.
 */
export function readmeAssetBase(repoUrl?: string | null): string | null {
  if (!repoUrl) return null;
  const m = /github\.com\/([^/\s?#]+)\/([^/\s?#]+)(?:\/tree\/([^/\s?#]+))?/i.exec(repoUrl);
  if (!m) return null;
  const owner = m[1];
  const repo = m[2].replace(/\.git$/i, "");
  const branch = m[3] || "HEAD";
  if (!owner || !repo) return null;
  return `https://raw.githubusercontent.com/${owner}/${repo}/${branch}/`;
}

/**
 * Resolve an asset URL referenced by markdown against a base URL.
 *
 * Absolute http(s) and `data:image/` URLs are kept as-is; relative paths are
 * resolved against *baseUrl*. Unsafe schemes (javascript:, blob:, file:) are
 * rejected.
 */
export function resolveMarkdownAssetUrl(src: string, baseUrl?: string | null): string | null {
  const raw = (src || "").trim();
  if (!raw) return null;
  if (/^data:image\//i.test(raw)) return raw;
  if (/^https?:\/\//i.test(raw)) return raw;
  if (!baseUrl) return null;
  try {
    const resolved = new URL(raw, baseUrl);
    if (resolved.protocol !== "http:" && resolved.protocol !== "https:") return null;
    return resolved.toString();
  } catch {
    return null;
  }
}

/**
 * Split one physical line into text / image segments, preserving order.
 * Linked image groups contribute their inner images; the link href itself is
 * dropped (the wrapper is navigation noise around the visual).
 */
export function splitLineSegments(line: string): LineSegment[] {
  const segs: LineSegment[] = [];
  let textStart = 0;
  let i = 0;

  const pushText = (end: number) => {
    if (end > textStart) segs.push({ type: "text", value: line.slice(textStart, end) });
  };

  while (i < line.length) {
    GROUP_Y.lastIndex = i;
    const g = GROUP_Y.exec(line);
    TOKEN_Y.lastIndex = i;
    const t = TOKEN_Y.exec(line);

    if (!g && !t) {
      i += 1;
      continue;
    }

    // Whichever construct starts earlier (or is longer at same spot) wins.
    const gStart = g ? g.index : Number.POSITIVE_INFINITY;
    const tStart = t ? t.index : Number.POSITIVE_INFINITY;
    const useGroup = gStart <= tStart;
    const m = (useGroup ? g : t)!;
    const start = m.index;

    pushText(start);

    if (useGroup) {
      // Emit each inner image of the [![a](u)![b](v)](href) wrapper.
      const innerRe = new RegExp(IMG_TOKEN_SRC, "g");
      let im: RegExpExecArray | null;
      while ((im = innerRe.exec(m[0])) !== null) {
        segs.push({ type: "image", alt: im[1], src: im[2] });
      }
    } else {
      segs.push({ type: "image", alt: m[1], src: m[2] });
    }

    i = start + m[0].length;
    textStart = i;
  }

  pushText(line.length);
  return segs;
}

