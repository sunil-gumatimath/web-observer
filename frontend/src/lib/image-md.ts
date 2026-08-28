/**
 * Shared parsing of inline markdown images found in snapshot text
 * (`![alt](src)` tokens, optionally wrapped in links `[…](href)`).
 *
 * Used by ReadableContent (monitor preview) and GithubDiff (change alerts)
 * so captured images render visually instead of as raw markdown soup.
 */

export type MdImage = { alt: string; src: string };

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

/**
 * Pull every markdown image out of a single line. Returns the images plus the
 * remaining text (with empty `[](...)` wrappers tidied away).
 */
export function extractImages(line: string): { imgs: MdImage[]; rest: string } {
  const segs = splitLineSegments(line);
  const imgs: MdImage[] = [];
  const textParts: string[] = [];
  for (const s of segs) {
    if (s.type === "image") imgs.push({ alt: s.alt, src: s.src });
    else textParts.push(s.value);
  }
  const rest = textParts
    .join(" ")
    .replace(/\[\s*\]\([^)]*\)/g, " ") // empty wrappers left from group removal
    .replace(/[ \t]{2,}/g, " ")
    .trim();
  return { imgs, rest };
}
