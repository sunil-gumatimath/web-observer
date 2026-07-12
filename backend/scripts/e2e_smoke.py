"""End-to-end API smoke test against a running local stack."""
from __future__ import annotations

import sys
import time
import uuid

import httpx
from sqlalchemy import create_engine, text

from app.config import get_settings

BASE = "http://127.0.0.1:8000"
HEADERS = {
    "X-Internal-Token": "dev-internal-token",
    "Content-Type": "application/json",
}


def main() -> int:
    results: list[tuple[str, str, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        results.append((status, name, detail))
        print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))

    client = httpx.Client(base_url=BASE, headers=HEADERS, timeout=30.0)

    try:
        r = client.get("/health")
        check("GET /health", r.status_code == 200, r.text[:80])

        r = client.get("/ready")
        check("GET /ready", r.status_code == 200, r.text[:80])

        r = client.get("/api/v1/me")
        check("GET /api/v1/me", r.status_code == 200, f"status={r.status_code}")
        me = r.json() if r.status_code == 200 else {}
        workspaces = me.get("workspaces") or []
        check("me has workspaces", len(workspaces) > 0, f"count={len(workspaces)}")
        for w in workspaces:
            print(f"    workspace: {w.get('id')} {w.get('name')}")

        ws_id = None
        for w in workspaces:
            if w.get("name") == "Dev Workspace":
                ws_id = w["id"]
                break
        if not ws_id and workspaces:
            ws_id = workspaces[0]["id"]
        check("resolved workspace", bool(ws_id), str(ws_id))
        if not ws_id:
            print("ABORT: no workspace")
            return 1

        r = client.get(f"/api/v1/workspaces/{ws_id}/usage")
        check("GET usage", r.status_code == 200, r.text[:160])

        r = client.get(f"/api/v1/workspaces/{ws_id}/monitors")
        mon_list = r.json() if r.status_code == 200 else []
        check("GET monitors", r.status_code == 200, f"count={len(mon_list)}")

        name = f"E2E Test {uuid.uuid4().hex[:8]}"
        body = {
            "name": name,
            "url": "https://example.com/",
            "mode": "whole_page",
            "schedule_interval_minutes": 60,
            "timezone": "UTC",
            "enabled": True,
        }
        r = client.post(f"/api/v1/workspaces/{ws_id}/monitors", json=body)
        check("POST create monitor", r.status_code in (200, 201), r.text[:240])
        mon = r.json() if r.status_code in (200, 201) else None
        mon_id = mon["id"] if mon else None

        if mon_id:
            r = client.get(f"/api/v1/workspaces/{ws_id}/monitors/{mon_id}")
            check("GET monitor", r.status_code == 200, mon_id)

            # Pause so the scheduler does not race our manual run.
            r = client.post(f"/api/v1/workspaces/{ws_id}/monitors/{mon_id}/pause")
            check("POST pause monitor", r.status_code == 200, r.text[:120])

            # Wait out any run the scheduler may have already queued at create time.
            for _ in range(20):
                r = client.get(f"/api/v1/workspaces/{ws_id}/monitors/{mon_id}/runs")
                runs = r.json() if r.status_code == 200 else []
                active = [x for x in runs if x.get("status") in ("queued", "running")]
                if not active:
                    break
                time.sleep(1.0)

            r = client.post(f"/api/v1/workspaces/{ws_id}/monitors/{mon_id}/run")
            check("POST manual run", r.status_code in (200, 201, 202), r.text[:200])
            run_payload = r.json() if r.status_code < 300 else {}
            run_id = run_payload.get("run_id") or run_payload.get("id")
            print(f"    run payload: {run_payload}")

            final = None
            for i in range(20):
                time.sleep(1.5)
                r = client.get(f"/api/v1/workspaces/{ws_id}/monitors/{mon_id}/runs")
                if r.status_code != 200:
                    continue
                runs = r.json()
                if not runs:
                    continue
                latest = runs[0]
                if run_id:
                    for rr in runs:
                        if rr.get("id") == run_id:
                            latest = rr
                            break
                st = latest.get("status")
                print(
                    f"    poll {i + 1}: status={st} "
                    f"error={latest.get('error_code')} {latest.get('error_message')}"
                )
                if st in ("succeeded", "failed", "cancelled"):
                    final = latest
                    break

            check(
                "worker completed run",
                final is not None and final.get("status") == "succeeded",
                (
                    f"status={final.get('status') if final else None} "
                    f"err={final.get('error_code') if final else None} "
                    f"msg={final.get('error_message') if final else None}"
                ),
            )

            r = client.post(f"/api/v1/workspaces/{ws_id}/monitors/{mon_id}/run")
            check("POST second manual run", r.status_code in (200, 201, 202), r.text[:120])
            second_ok = False
            for _ in range(15):
                time.sleep(1.5)
                r = client.get(f"/api/v1/workspaces/{ws_id}/monitors/{mon_id}/runs")
                if r.status_code != 200:
                    continue
                runs = sorted(
                    r.json(),
                    key=lambda x: x.get("created_at") or "",
                    reverse=True,
                )
                if len(runs) >= 2 and runs[0].get("status") in ("succeeded", "failed"):
                    check(
                        "second run terminal",
                        runs[0].get("status") == "succeeded",
                        f"status={runs[0].get('status')} err={runs[0].get('error_code')}",
                    )
                    second_ok = True
                    break
            if not second_ok:
                check("second run terminal", False, "timeout")

            r = client.get(f"/api/v1/workspaces/{ws_id}/notification-channels")
            check("GET notification-channels", r.status_code == 200, r.text[:100])

            r = client.delete(f"/api/v1/workspaces/{ws_id}/monitors/{mon_id}")
            check("DELETE monitor", r.status_code in (200, 204), f"{r.status_code} {r.text[:200]}")

        # Clerk user membership sanity
        s = get_settings()
        engine = create_engine(s.database_url, connect_args={"connect_timeout": 10})
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT w.id::text, w.name, u.email, u.clerk_user_id
                    FROM workspaces w
                    LEFT JOIN workspace_members wm ON wm.workspace_id = w.id
                    LEFT JOIN users u ON u.id = wm.user_id
                    ORDER BY w.created_at
                    """
                )
            ).fetchall()
            print("\n[INFO] workspace memberships:")
            for row in rows:
                print(f"    {row}")
            clerk_ws = [
                row
                for row in rows
                if row[3]  # clerk_user_id present
            ]
            check(
                "clerk user has a workspace membership",
                len(clerk_ws) > 0,
                f"clerk_memberships={len(clerk_ws)}",
            )
            # Dev workspace monitors should not be required for clerk UI
            mon_counts = conn.execute(
                text(
                    """
                    SELECT w.name, count(m.id)
                    FROM workspaces w
                    LEFT JOIN monitors m ON m.workspace_id = w.id
                    GROUP BY w.name
                    ORDER BY w.name
                    """
                )
            ).fetchall()
            print("[INFO] monitors per workspace:")
            for row in mon_counts:
                print(f"    {row}")

    finally:
        client.close()

    print("\n===== SUMMARY =====")
    fails = [x for x in results if x[0] == "FAIL"]
    print(f"{len(results) - len(fails)} passed, {len(fails)} failed")
    for st, name, detail in fails:
        print(f"  FAIL: {name} — {detail}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
