/**
 * Wire FastAPI Clerk settings from frontend/.env.local without printing secrets.
 * Derives CLERK_ISSUER + CLERK_JWKS_URL from the publishable key payload.
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const frontendEnv = path.join(root, "frontend", ".env.local");
const rootEnv = path.join(root, ".env");

function getEnv(text, key) {
  const m = text.match(new RegExp(`^${key}=(.*)$`, "m"));
  if (!m) return "";
  return m[1].trim().replace(/^["']|["']$/g, "");
}

function setKey(content, key, value) {
  const re = new RegExp(`^${key}=.*$`, "m");
  if (re.test(content)) return content.replace(re, `${key}=${value}`);
  return `${content.trimEnd()}\n${key}=${value}\n`;
}

if (!fs.existsSync(frontendEnv)) {
  console.error("Missing frontend/.env.local — run: cd frontend && clerk env pull");
  process.exit(1);
}

const text = fs.readFileSync(frontendEnv, "utf8");
const pk = getEnv(text, "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY");
if (!pk) {
  console.error("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY missing from frontend/.env.local");
  process.exit(1);
}

const b64 = pk.split("_").slice(2).join("_");
let frontendApi = "";
for (const raw of [b64, b64.replace(/-/g, "+").replace(/_/g, "/")]) {
  try {
    const decoded = Buffer.from(raw, "base64").toString("utf8");
    frontendApi = decoded.replace(/\0/g, "").split("$")[0].trim();
    if (frontendApi.includes("clerk") || frontendApi.includes(".")) break;
  } catch {
    /* try next */
  }
}

if (!frontendApi) {
  console.error("Could not decode Frontend API host from publishable key");
  process.exit(1);
}

const issuer = `https://${frontendApi}`;
const jwks = `${issuer}/.well-known/jwks.json`;

let env = fs.existsSync(rootEnv) ? fs.readFileSync(rootEnv, "utf8") : "";
env = setKey(env, "CLERK_JWKS_URL", jwks);
env = setKey(env, "CLERK_ISSUER", issuer);
const sk = getEnv(text, "CLERK_SECRET_KEY");
if (sk) env = setKey(env, "CLERK_SECRET_KEY", sk);
fs.writeFileSync(rootEnv, env);

console.log("OK: wrote CLERK_JWKS_URL and CLERK_ISSUER to root .env");
console.log(`Frontend API host: ${frontendApi}`);
