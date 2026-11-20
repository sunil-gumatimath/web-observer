import test from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";

const makeRequest = (path, host = "public.example") =>
  new Request(`https://${host}${path}`);

test("passes through when cache host is unset or mismatched", async (t) => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async (request) => {
    calls += 1;
    return new Response(new URL(request.url).pathname);
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
  });

  for (const env of [{}, { CACHE_HOST: "other.example" }]) {
    const response = await worker.fetch(makeRequest("/share/id"), env, {});
    assert.equal(response.status, 200);
    assert.equal(await response.text(), "/share/id");
  }
  assert.equal(calls, 2);
});

test("does not cache responses that set cookies", async (t) => {
  const originalFetch = globalThis.fetch;
  const originalCaches = globalThis.caches;
  let puts = 0;
  globalThis.fetch = async () => new Response("private", {
    headers: { "Set-Cookie": "session=user-secret" },
  });
  globalThis.caches = {
    default: {
      match: async () => undefined,
      put: async () => { puts += 1; },
    },
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
    globalThis.caches = originalCaches;
  });

  const response = await worker.fetch(
    makeRequest("/share/id"),
    { CACHE_HOST: "public.example" },
    { waitUntil: () => {} },
  );
  assert.equal(response.headers.get("set-cookie"), "session=user-secret");
  assert.equal(puts, 0);
});
