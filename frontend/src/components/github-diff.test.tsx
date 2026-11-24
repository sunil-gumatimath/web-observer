// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { GithubDiff } from "./github-diff";

describe("GithubDiff list bullets", () => {
  afterEach(() => cleanup());

  it("strips stored '- ' prefixes when stripBullets is set", () => {
    render(
      <GithubDiff
        before={"- meta robots: noindex\n"}
        after={"- meta robots: index\n"}
        stripBullets
      />,
    );
    expect(screen.getByText("meta robots: index")).toBeTruthy();
    expect(screen.queryByText("- meta robots: index")).toBeNull();
  });

  it("keeps lines untouched by default", () => {
    render(<GithubDiff before={""} after={"- meta robots: index\n"} />);
    expect(screen.getByText("- meta robots: index")).toBeTruthy();
  });
});
