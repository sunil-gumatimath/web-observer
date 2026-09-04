# Web Observer — Feature Roadmap & Enhancement Specification

This document details the strategic product enhancements, technical architecture upgrades, and new feature specifications for **Web Observer**. It builds on the existing foundation (Phases 0–7) to elevate the platform to a commercial-grade web monitoring and intelligence engine.

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Advanced Monitoring & Extraction Engines](#2-advanced-monitoring--extraction-engines)
3. [Notification Channels & Alert Intelligence](#3-notification-channels--alert-intelligence)
4. [Diffing, Visualization & UX Upgrades](#4-diffing-visualization--ux-upgrades)
5. [Network, Stealth & Anti-Bot Infrastructure](#5-network-stealth--anti-bot-infrastructure)
6. [Developer Platform & Ecosystem Integrations](#6-developer-platform--ecosystem-integrations)
7. [Operational & Performance Hardening](#7-operational--performance-hardening)
8. [Phased Implementation Roadmap & Priority Matrix](#8-phased-implementation-roadmap--priority-matrix)

---

## 1. Executive Summary

Web Observer currently excels at scheduled webpage fetching (HTTP / Playwright), content hashing, line diffing, heuristic and LLM summaries, and multi-tenant workspace management. 

To expand from developer-centric change detection into an all-in-one web intelligence platform (competing with Visualping, ChangeDetection.io, Hexowatch, and Distill.io), the system should expand across five pillars:
* **Ease of setup:** Visual point-and-click element selection without needing manual CSS/XPath inspection.
* **Access deeper web content:** Multi-step user journeys (logins, cookie banners, dropdowns) and anti-bot evasion.
* **Zero false-alarm alerting:** Natural-language semantic triggers, smart cooldowns, and instant push channels (Telegram, Web Push).
* **Visual fidelity:** Interactive image diff sliders, rendered HTML overlays, and arbitrary timeline time-travel.
* **Integrations:** Browser extension, official Zapier/n8n community nodes, and typed SDKs.

---

## 2. Advanced Monitoring & Extraction Engines

### 2.1 Interactive Point-and-Click Visual Element Selector `[Status: Partially Implemented]`
* **Problem:** Users currently must inspect browser DevTools, locate DOM classes or IDs, and manually paste CSS selectors or JSONPaths into the form.
* **Shipped (2026-09):** proxied `POST /monitors/selector-preview` (sanitized HTML) + `SelectorPicker` overlay (`frontend/src/components/selector-picker.tsx`) with resilient selector synthesis (`frontend/src/lib/selector.ts`) on New/Edit monitor.
* **Remaining:** pre-fill from the browser-extension flow (§6.1), saved-selector confidence scoring.
* **Proposed Solution (original):**
  * In the **New Monitor** flow, adding a URL loads a proxied interactive preview inside the frontend.
  * Headless Chromium retrieves the page DOM and stylesheet snapshot.
  * When hovering over elements, an interactive overlay outlines elements in real-time.
  * Clicking an element highlights it and automatically synthesizes the most resilient CSS selector (prioritizing semantic IDs, data attributes, or resilient hierarchical paths over fragile auto-generated class names).
* **Impact:** Eliminates 80% of onboarding friction for non-technical users.

### 2.2 Multi-Step Scripted User Journeys (Pre-Action Sequences)
* **Problem:** Modern sites require user interactions before target content renders (e.g., dismissing cookie consent banners, logging in, selecting a store location, or clicking accordions).
* **Proposed Solution:**
  * Add a `pre_actions` JSONB column to `monitors`:
    ```json
    [
      {"action": "click", "selector": "#onetrust-accept-btn-handler"},
      {"action": "type", "selector": "input#zipcode", "value": "94103"},
      {"action": "press", "key": "Enter"},
      {"action": "wait_for_selector", "selector": ".inventory-grid", "timeout_ms": 5000}
    ]
    ```
  * Playwright iterates through these actions before taking the content snapshot.
  * Include common pre-action recipes: "Dismiss Cookie Modal", "Accept 18+ Gate", "Scroll to Bottom (Infinite Scroll)".

### 2.3 Visual Region / Bounding-Box Cropping
* **Problem:** Whole-page visual monitoring (`visual` mode) frequently fires false positives due to rotating banner ads, sticky chat widgets, or changing header carousels.
* **Proposed Solution:**
  * Allow users to draw a selection rectangle over the captured screenshot preview (`{x: 100, y: 240, width: 400, height: 180}`).
  * The worker crops the image to the specified bounding box before calculating perceptual hashes (`aHash` / `pHash`) and image diffs.
  * Supports multiple exclusion zones (e.g., "ignore this banner area").

### 2.4 PDF & Document Tracking
* **Problem:** Many organizations track government gazettes, regulatory policy updates, whitepapers, or contracts published exclusively as downloadable PDFs.
* **Proposed Solution:**
  * Add a `document_pdf` mode.
  * Worker downloads the binary, runs `pypdf` or `pdfminer.six` to extract normalized textual content, strips running headers/page numbers, and computes standard textual diffs.
  * Provide visual page-by-page change thumbnails.

### 2.5 Custom HTTP Request Configuration & Session Cookies
* **Problem:** Monitoring internal staging portals, private dashboards, or authenticated accounts requires custom headers or persistent cookies.
* **Proposed Solution:**
  * Support custom HTTP headers (e.g., `Authorization: Bearer <token>`).
  * Support session cookie injection (e.g., `Cookie: session_id=...`).
  * Support custom HTTP methods (`POST`, `PUT`) with JSON payloads for tracking direct REST/GraphQL endpoints.

---

## 3. Notification Channels & Alert Intelligence

### 3.1 Telegram Bot Integration
* **Problem:** Email alerts are often delayed or buried, and Slack/Discord setups require workspace administrative permissions that individual users or small teams may not have.
* **Proposed Solution:**
  * Create an official Web Observer Telegram bot (`@WebObserverBot`).
  * In **Settings → Notification Channels**, user clicks "Connect Telegram".
  * The app generates a deep-link `/start <workspace_token>` that pairs the user's Telegram chat or group.
  * Deliver instant alert messages with change summaries, inline diff snippets, and action buttons (`[View Diff]`, `[Pause Monitor]`, `[Mark as Noise]`).

### 3.2 Web Push Notifications (PWA / Browser Notifications)
* **Proposed Solution:**
  * Integrate the Web Push API via Service Workers and VAPID keys.
  * Users can enable desktop and mobile browser push notifications with a single click.
  * Alerts arrive natively on macOS, Windows, Android, and iOS (PWA home screen).

### 3.3 Semantic / Natural-Language AI Alert Rules `[Status: Implemented]`
* **Problem:** Regex and percentage-based conditional rules require technical syntax and fail on nuanced natural language changes.
* **Implemented Solution:**
  * Added `semantic_trigger` to `Monitor` entity and `MonitorCreate`/`MonitorUpdate` schemas.
  * Added first-class `title`, `impact` (`critical`, `high`, `medium`, `low`), and `confidence` columns to `ChangeEvent` (Alembic migration `012_add_ai_intelligence_fields` on Neon).
  * Enclosed diffs within `<untrusted_diff_content>` XML fences for prompt injection defense.
  * Worker feeds diff and semantic trigger into LLM (`ai_summary.py`); if conditions are not satisfied, the change is triaged as `is_noise=true` with a clear reason, suppressing notifications while preserving visibility in the alerts inbox.
  * Integrated distributed Redis deduplication caching (`ai_dedup:<hash>`) with process-memory fallback.
  * Added AI Executive Digest briefings for daily/weekly digests.
  * Added UI badge display for impact/confidence and semantic trigger input fields in the frontend.

### 3.4 Smart Alert Throttling & Flapping Protection
* **Problem:** Websites that update frequently or flap between two states (e.g., "In Stock" and "Out of Stock" every 5 minutes) flood channels with noise.
* **Proposed Solution:**
  * **Cooldown Window:** Configurable quiet period per monitor (e.g., maximum 1 notification per 3 hours).
  * **Flapping Detection:** Automatically detects when state A alternates with state B repeatedly within a 1-hour window; pauses external alerts and sends a single notice: *"Monitor is flapping between 2 states; alerts temporarily bundled."*
  * **Digest Rollup:** Option to bundle rapid-fire changes into an hourly or daily summary rather than immediate single-fire messages.

---

## 4. Diffing, Visualization & UX Upgrades

### 4.1 Interactive Visual Diff Slider (Swipe / Split-Screen View) `[Status: Partially Implemented]`
* **Done (2026-09):** swipe/split slider component (`frontend/src/components/visual-diff.tsx`), screenshot keying to changed runs (not latest runs), slider polish via UI batch.
* **Remaining:** pixel-difference heatmap overlay (magenta/neon clusters) and flicker/blink mode.
* **Problem:** Viewing old and new screenshots side-by-side makes subtle layout and typography changes difficult to detect.
* **Proposed Solution:**
  * Implement an interactive comparison slider (Juxtapose-style) in the Next.js frontend:
    * **Split/Swipe Mode:** Drag a vertical divider left/right across the screenshot to inspect the delta.
    * **Highlight/Difference Heatmap:** Overlay changed pixel clusters highlighted in high-contrast magenta/neon green.
    * **Flicker/Blink Mode:** Rapidly alternate between previous and current snapshot to spot micro-movements.

### 4.2 Rendered In-Situ HTML Diffs (Wayback Style)
* **Problem:** Line-based Markdown diffs lose visual webpage context.
* **Proposed Solution:**
  * Render the webpage in an isolated iframe sandboxed container with the historical DOM.
  * Inject visual styling: added elements highlighted with a subtle green background and green border; removed elements overlaid in red with strikethrough.

### 4.3 Historical Time-Travel & Snapshot Scrubbing
* **Problem:** Users can currently only view the diff between the latest run and its immediate predecessor.
* **Proposed Solution:**
  * A timeline calendar / scrubbing bar on the Monitor Detail page.
  * Allows selecting any two arbitrary historical snapshots (e.g., "Compare 2026-06-01 baseline against 2026-09-01") to analyze cumulative drift over weeks or months.

### 4.4 Folders, Tags & Bulk Fleet Management `[Status: Partially Implemented]`
* **Done (2026-09):** bulk pause/resume — `POST /monitors/pause-all` + `POST /monitors/resume-all` (`backend/app/routers/monitors.py`) with dashboard Pause-all/Resume-all controls (confirm dialog, optimistic `enabled` flip).
* **Remaining:** `tags`/`folder_id` organization, multi-select *Change Check Interval*, *Assign Channel*, *Batch Export*.
* **Problem:** When a workspace tracks 50+ monitors, the flat list becomes disorganized.
* **Proposed Solution (original):**
  * Add `tags` (array of strings) and `folder_id` (nested categories) to `monitors`.
  * Enable multi-select bulk operations: *Bulk Pause*, *Bulk Resume*, *Change Check Interval*, *Assign Channel*, and *Batch Export*.

---

## 5. Network, Stealth & Anti-Bot Infrastructure

### 5.1 Residential & Rotating Proxy Pools
* **Problem:** Enterprise target sites (Amazon, LinkedIn, Cloudflare, Ticketmaster) ban datacenter IPs or serve localized content based on geography.
* **Proposed Solution:**
  * Add workspace and per-monitor proxy configuration:
    * Support custom HTTP/SOCKS5 proxy URIs with authentication (`http://user:pass@proxy.example.com:8080`).
    * Direct integrations with proxy providers (Bright Data, Oxylabs, ScrapingBee).
    * Geo-location targeting (e.g., execute check from US, EU, UK, or APAC IP addresses).
* **Solo / free-tier note:** proxy providers are paid. Defer provider integrations to Phase 10; Phase 8–9 uses only free custom-proxy-URI support (user brings their own proxy).

### 5.2 Stealth Browser Automation
* **Problem:** Cloudflare Turnstile, DataDome, and Akamai detect default headless Chromium instances.
* **Proposed Solution:**
  * Implement `playwright-stealth` evasions:
    * Randomize WebGL renderer and vendor strings.
    * Mask automated canvas fingerprinting.
    * Emulate realistic user agent client hints (`navigator.userAgentData`).
    * Emulate humanized mouse trajectories and random viewport jitter before taking snapshots.

### 5.3 Warm Browser Worker Context Pool
* **Problem:** Spawning a brand-new Python subprocess and Chromium browser instance per check on Windows incurs a 1.5–2.5 second launch overhead.
* **Proposed Solution:**
  * Maintain a persistent warm Chromium browser process managed by a supervision daemon.
  * Check jobs create and destroy lightweight isolated browser contexts (`browser.new_context()`) rather than launching cold browser binaries, cutting execution latency by ~70%.
  * Recycle the master browser process every $N$ runs to guarantee zero memory or handle leaks.

### 5.4 Real-Time Streaming via Server-Sent Events (SSE)
* **Problem:** Long-running checks historically had the frontend poll for status; newer surfaces (e.g. the dashboard activity card) fetch on interaction (range change) rather than polling.
* **Proposed Solution:**
  * Add a FastAPI SSE endpoint: `GET /api/v1/workspaces/{ws}/monitors/{id}/stream`.
  * Streams real-time pipeline events (`QUEUED` → `CONNECTING` → `RENDERED` → `DIFF_CALCULATED` → `ALERT_DISPATCHED`).
  * Live-updates the Alerts Inbox and Dashboard without polling.

---

## 6. Developer Platform & Ecosystem Integrations

### 6.1 Official Browser Extension (Chrome & Firefox)
* **Proposed Solution:**
  * A lightweight browser extension with OAuth/API key login.
  * **Workflow:**
    1. Navigate to any website.
    2. Click the extension icon.
    3. Click "Select Element" and click anywhere on the page.
    4. Choose checking frequency (e.g., "Every 1 hour").
    5. Hit "Save Monitor".
  * Immediately creates the monitor in Web Observer without leaving the target site.

### 6.2 Official SDKs & Developer CLI
* **Proposed Solution:**
  * **TypeScript SDK:** `@web-observer/sdk` for easy integration in Next.js/Node services.
  * **Python SDK:** `web-observer-client` for data engineers and automation scripts.
  * **CLI (`mtw`):** Command-line utility for DevOps teams to manage monitors as code or trigger checks inside CI/CD pipelines (e.g., checking landing pages post-deploy).

### 6.3 No-Code Integrations (Zapier & n8n)
* **Proposed Solution:**
  * Publish a verified Zapier app and n8n community node.
  * **Triggers:** "New Change Detected", "Monitor Failed", "Price Dropped Below Threshold".
  * **Actions:** "Create Monitor", "Run Check Now", "Pause Monitor".

### 6.4 Executive PDF / CSV Scheduled Reports
* **Proposed Solution:**
  * Enable weekly or monthly compiled digest reports in styled PDF format.
  * Includes brand thumbnails, categorized changes (pricing, features, legal), and competitive intelligence timelines.
  * Designed for agency clients, marketing leads, and compliance officers.

---

## 7. Operational & Performance Hardening

Based on architectural reviews, the following foundational optimizations keep the platform robust as user volume grows.
All four are **implemented** — statuses verified against code 2026-09-04:

| Enhancement | Problem Solved | Architectural Strategy | Status |
|---|---|---|---|
| **Asynchronous Brand Fetching** | Creating a monitor blocked the uvicorn HTTP worker while fetching external page metadata. | `201 Created` returns immediately; brand metadata extraction runs in the background Dramatiq queue (`app/workers/branding.py:enrich_monitor_brand`, enqueued at `routers/monitors.py:create_monitor`). | Done |
| **Bounded Dashboard Query** | `list_monitors` performed an unbounded scan of `ChangeEvent` across workspace history. | LATERAL join — one index walk per monitor via `ix_change_events_monitor_created` (`routers/monitors.py:list_monitors`). | Done |
| **Outbox Conflict Safety** | Outbox insertion used a bare `db.add()`, which poisoned retry workers on race conditions. | `pg_insert(...).on_conflict_do_nothing(index_elements=["idempotency_key"])` keyed on `run:{run_id}:change:channel:{channel_id}` (`services/pipeline.py:_queue_notifications`). | Done |
| **Cloudflare R2 / S3 Storage** | Local disk storage (`STORAGE_BACKEND=local`) does not scale across distributed worker nodes. | `app/services/storage.py` supports `local` / `s3` (R2-compatible via `s3_endpoint_url`) backends with path-traversal guards. | Done (local default; set `STORAGE_BACKEND=s3` + endpoint/keys for R2) |

---

## 8. Phased Implementation Roadmap & Priority Matrix

> Solo + free-tier constraint: no paid proxy/SDK infra in Phase 8–9. Ship deployable increments per phase (see `production.md` for Render/GCP path).

```mermaid
gantt
    title Web Observer Enhancement Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 8 (Immediate High-ROI)
    Telegram Bot Channel                   :p8telegram, 2026-09-08, 7d
    Async Brand Fetch & DB Query Fixes     :p8hard, after p8telegram, 5d
    Interactive Point-and-Click Selector   :p8selector, after p8hard, 14d
    section Phase 9 (Advanced Automation)
    Multi-Step User Journeys (Logins/Clicks) :2026-10-01, 14d
    Visual Bounding-Box Cropping           :2026-10-10, 10d
    Diff Heatmap + Flicker (4.1 remainder) :2026-10-15, 8d
    Web Push (PWA) Notifications           :2026-10-20, 7d
    section Phase 10 (Enterprise & Ecosystem)
    Stealth Evasion & Proxy Rotation       :2026-11-01, 14d
    Chrome/Firefox Extension               :2026-11-10, 14d
    Zapier & n8n Community Nodes           :2026-11-20, 10d
    PDF / Document Monitoring Engine       :2026-11-25, 12d
```

### Effort vs. Impact Matrix

| Feature | User Impact | Implementation Effort | Recommended Order |
|---|---|---|---|
| **Telegram Bot Alerting** | High | Low (1–2 days) | 1 |
| **Async Brand Fetch & Query Hardening** | Done 2026-09 (all 4 items verified in code) | — | Done, skip |
| **Visual Element Selector (Point-and-Click)** | Partially done 2026-09 (preview + picker shipped; extension flow left) | — | Partial, see 2.1 |
| **Visual Bounding-Box Crop** | High | Low-Medium (2 days) | 4 |
| **Diff Heatmap + Flicker (4.1 remainder)** | Medium-High | Low (1–2 days) | 5 |
| **Multi-Step Journeys (Logins, Clicks)** | Very High | Medium (4–5 days) | 6 |
| **Smart Alert Throttling & Flapping** | Medium-High | Low (2 days) | 7 |
| **Browser Extension** | Very High | Medium (4–5 days) | 8 — Phase 10 (needs packaging + store review) |
| **Residential / Rotating Proxy Pool** | High | Medium (3 days) | 9 — Phase 10, paid providers only; free BYO-proxy URI first |
| **PDF Document Diffing** | Medium | Medium (3 days) | 10 |
| **Zapier / n8n Nodes** | Medium-High | Low-Medium (2–3 days) | 11 |
| **Semantic AI Alert Rules (3.3)** | Done 2026-09 | — | Done, skip |
| **Swipe Diff Slider base (4.1)** | Done 2026-09 | — | Done, only heatmap/flicker left |

---

*Document created for pair-programming and roadmap tracking. Last reviewed 2026-09-04: marked 3.3 + 4.1-base + bulk pause/resume (4.4) done, 2.1 partially implemented (selector-preview + picker shipped), re-sequenced Phase 8 (Telegram first), deferred paid proxy/extension to Phase 10. Deploy path: see `production.md`. Review or update as feature requirements evolve.*
