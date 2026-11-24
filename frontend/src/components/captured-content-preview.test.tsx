// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Monitor, SnapshotAccess } from "@/lib/types";
import { CapturedContentPreview } from "./captured-content-preview";

const monitor = {
  id: "m-1",
  name: "Example",
  url: "https://example.com/",
  mode: "html_meta",
  js_required: false,
} as unknown as Monitor;

const snapshot = {
  normalized_text: "- title: Example\n- meta robots: index\n",
} as unknown as SnapshotAccess;

describe("CapturedContentPreview html_meta", () => {
  afterEach(() => cleanup());

  it("renders stored facts without the '- ' prefix", () => {
    const { container } = render(
      <CapturedContentPreview monitor={monitor} snapshot={snapshot} />,
    );
    expect(container.textContent).toContain("meta robots: index");
    expect(container.textContent).not.toContain("- meta robots: index");
  });
});
