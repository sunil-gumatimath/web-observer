"""End-to-end monitor test covering creation, execution, diffing, change detection, and cleanup."""

import os
import sys
import time
import uuid

import httpx

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8002")
HEADERS = {
    "X-Internal-Token": "dev-internal-token",
    "Content-Type": "application/json",
}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    client = httpx.Client(base_url=BASE, headers=HEADERS, timeout=40.0)
    try:
        me = client.get("/api/v1/me").json()
        workspaces = me.get("workspaces", [])
        assert workspaces, "No workspaces found"
        ws_id = workspaces[0]["id"]
        for w in workspaces:
            if w.get("name") == "Dev Workspace":
                ws_id = w["id"]
                break
        print(f"[1] Using workspace: {ws_id}")

        name = f"UUID Test {uuid.uuid4().hex[:6]}"
        mon_res = client.post(
            f"/api/v1/workspaces/{ws_id}/monitors",
            json={
                "name": name,
                "url": "https://httpbin.org/uuid",
                "mode": "page_content",
                "schedule_interval_minutes": 60,
                "enabled": True,
            },
        )
        assert mon_res.status_code in (200, 201), f"Create failed: {mon_res.text}"
        mon = mon_res.json()
        mid = mon["id"]
        print(f"[2] Created monitor: {mid} ('{name}')")

        # -----------------------------------------------------------------
        # RUN 1: Baseline run (picked up by scheduler since next_run_at = now)
        # -----------------------------------------------------------------
        print("[3] Waiting for initial baseline run to be executed...")
        run1 = None
        for i in range(30):
            time.sleep(2.0)
            res = client.get(f"/api/v1/workspaces/{ws_id}/monitors/{mid}/runs")
            if res.status_code != 200:
                continue
            runs = res.json()
            if runs:
                latest = runs[0]
                st = latest.get("status")
                print(f"    Run 1 poll {i+1}: status={st} error={latest.get('error_code')}")
                if st in ("succeeded", "failed"):
                    run1 = latest
                    break

        assert run1 and run1["status"] == "succeeded", f"Baseline run failed: {run1}"
        print(f"[4] Baseline run succeeded: latency={run1.get('latency_ms')}ms hash={run1.get('content_hash')[:12]}")

        # Pause now so scheduler does not schedule while we trigger Run 2
        pause_res = client.post(f"/api/v1/workspaces/{ws_id}/monitors/{mid}/pause")
        assert pause_res.status_code == 200, f"Pause failed: {pause_res.text}"
        print("[5] Monitor paused for controlled change test")

        changes = client.get(f"/api/v1/workspaces/{ws_id}/monitors/{mid}/changes").json()
        print(f"[6] Changes after baseline: {len(changes)} (expected 0)")
        assert len(changes) == 0, "Baseline should have 0 changes"

        # -----------------------------------------------------------------
        # RUN 2: Changing content run (httpbin.org/uuid produces a new UUID)
        # -----------------------------------------------------------------
        r2 = client.post(f"/api/v1/workspaces/{ws_id}/monitors/{mid}/run")
        assert r2.status_code in (200, 201, 202), f"Manual run failed: {r2.status_code} {r2.text}"
        run2_payload = r2.json()
        run2_id = run2_payload.get("run_id") or run2_payload.get("id")
        print(f"[7] Queued Run 2 (expecting change): {run2_id}")

        run2 = None
        for i in range(30):
            time.sleep(2.0)
            res = client.get(f"/api/v1/workspaces/{ws_id}/monitors/{mid}/runs")
            if res.status_code != 200:
                continue
            runs = res.json()
            target = next((r for r in runs if r["id"] == run2_id), None)
            if target and target["status"] in ("succeeded", "failed"):
                run2 = target
                break

        assert run2 and run2["status"] == "succeeded", f"Run 2 failed: {run2}"
        print(f"[8] Run 2 succeeded: latency={run2.get('latency_ms')}ms hash={run2.get('content_hash')[:12]}")

        # Poll for change event processing (worker computes diff / AI summary)
        ch_list = []
        for i in range(15):
            time.sleep(1.5)
            ch_list = client.get(f"/api/v1/workspaces/{ws_id}/monitors/{mid}/changes").json()
            if len(ch_list) > 0:
                break
            print(f"    Waiting for change event... ({i+1})")

        print(f"[9] Changes detected after Run 2: {len(ch_list)}")
        assert len(ch_list) >= 1, "Run 2 must produce a ChangeEvent!"

        ch = ch_list[0]
        cid = ch["id"]
        print(f"    Change ID: {cid}")
        print(f"    Diff summary: {ch.get('diff_summary')}")
        print(f"    AI summary: {ch.get('ai_summary')}")
        print(f"    Category: {ch.get('change_category')}")

        # Verify change detail endpoint
        ch_detail = client.get(f"/api/v1/workspaces/{ws_id}/changes/{cid}").json()
        diff_text = ch_detail.get("diff")
        print(f"[10] Diff retrieved: {bool(diff_text)}")
        if diff_text:
            print("    Diff content preview:")
            for line in diff_text.strip().splitlines()[:6]:
                print(f"      {line}")

        # Check alerts inbox
        alerts = client.get(f"/api/v1/workspaces/{ws_id}/alerts").json()
        in_alerts = any(a["id"] == cid for a in alerts)
        print(f"[11] Found in workspace alerts inbox: {in_alerts}")

        # Check change activity
        activity = client.get(f"/api/v1/workspaces/{ws_id}/changes/activity?days=7").json()
        print(f"[12] Activity summary total changes: {activity.get('total')}")

        # -----------------------------------------------------------------
        # CLEANUP
        # -----------------------------------------------------------------
        del_res = client.delete(f"/api/v1/workspaces/{ws_id}/monitors/{mid}")
        print(f"[13] Cleanup DELETE monitor: {del_res.status_code}")
        assert del_res.status_code in (200, 204)

        print("\n========================================================")
        print(">>> ALL END-TO-END MONITOR & CHANGE PIPELINE CHECKS PASSED! <<<")
        print("========================================================")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
