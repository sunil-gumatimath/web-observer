import test from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";

const request = (method = "POST", token = "secret", body = "{}") =>
  new Request("https://worker.example/", {
    method,
    headers: { "X-CF-Failover-Token": token, "Content-Type": "application/json" },
    body: method === "GET" ? undefined : body,
  });

test("fails closed when SHARED_TOKEN is not configured", async () => {
  const response = await worker.fetch(request(), {}, {});
  assert.equal(response.status, 503);
});

test("rejects unsupported methods before browser launch", async () => {
  const response = await worker.fetch(request("GET"), { SHARED_TOKEN: "secret" }, {});
  assert.equal(response.status, 405);
});

test("rejects invalid tokens before browser launch", async () => {
  const response = await worker.fetch(request("POST", "wrong"), { SHARED_TOKEN: "secret" }, {});
  assert.equal(response.status, 401);
});

test("rejects malformed JSON and non-HTTP URLs", async () => {
  const env = { SHARED_TOKEN: "secret" };
  const malformed = await worker.fetch(request("POST", "secret", "{"), env, {});
  assert.equal(malformed.status, 400);
  const unsupported = await worker.fetch(
    request("POST", "secret", JSON.stringify({ url: "file:///etc/passwd" })),
    env,
    {},
  );
  assert.equal(unsupported.status, 400);
});
