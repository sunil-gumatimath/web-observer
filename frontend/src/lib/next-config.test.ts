import { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD } from "next/constants";
import { afterEach, describe, expect, it } from "vitest";
import { validateBuildEnv } from "../../next.config";

describe("next.config validateBuildEnv", () => {
  const originalToken = process.env.NEXT_PUBLIC_INTERNAL_API_TOKEN;
  const originalNodeEnv = process.env.NODE_ENV;

  afterEach(() => {
    if (originalToken === undefined) {
      delete process.env.NEXT_PUBLIC_INTERNAL_API_TOKEN;
    } else {
      process.env.NEXT_PUBLIC_INTERNAL_API_TOKEN = originalToken;
    }
    (process.env as Record<string, string | undefined>).NODE_ENV = originalNodeEnv;
  });

  it("rejects a non-placeholder NEXT_PUBLIC_INTERNAL_API_TOKEN during production build", () => {
    process.env.NEXT_PUBLIC_INTERNAL_API_TOKEN = "real-owner-secret-token";
    expect(() => validateBuildEnv(PHASE_PRODUCTION_BUILD)).toThrow(
      /NEXT_PUBLIC_INTERNAL_API_TOKEN/,
    );
  });

  it("allows unset or dev placeholder during production build", () => {
    delete process.env.NEXT_PUBLIC_INTERNAL_API_TOKEN;
    expect(() => validateBuildEnv(PHASE_PRODUCTION_BUILD)).not.toThrow();

    process.env.NEXT_PUBLIC_INTERNAL_API_TOKEN = "dev-internal-token";
    expect(() => validateBuildEnv(PHASE_PRODUCTION_BUILD)).not.toThrow();
  });

  it("allows custom dev token in development server phase", () => {
    (process.env as Record<string, string | undefined>).NODE_ENV = "development";
    process.env.NEXT_PUBLIC_INTERNAL_API_TOKEN = "local-dev-token";
    expect(() => validateBuildEnv(PHASE_DEVELOPMENT_SERVER)).not.toThrow();
  });
});
