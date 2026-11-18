import { describe, expect, it } from "vitest";
import { alertConfigPatch } from "@/lib/alert-config";

describe("alertConfigPatch", () => {
  it("sends an empty alert_config so blanking every field clears the configuration", () => {
    expect(alertConfigPatch(null)).toEqual({ alert_config: {} });
    expect(alertConfigPatch({})).toEqual({ alert_config: {} });
  });

  it("preserves configured thresholds", () => {
    const config = { min_diff_chars: 120, regex_must_match: "price" };
    expect(alertConfigPatch(config)).toEqual({ alert_config: config });
  });
});
