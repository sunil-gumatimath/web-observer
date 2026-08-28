"""Trigger a manual check on the HN browser monitor and verify what code runs."""
import re
import time

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")
import os  # noqa: E402

engine = create_engine(os.environ["DATABASE_URL"])
WID = "67f2c65c-1aaa-4364-9b1a-2f430b9769cc"
MID = "cf9472d8-2b3c-4855-8274-1a5b4202db77"

resp = httpx.post(
    f"http://127.0.0.1:8002/api/v1/workspaces/{WID}/monitors/{MID}/run",
    headers={"X-Internal-Token": os.environ.get("INTERNAL_API_TOKEN", "dev-internal-token")},
    timeout=20,
)
print("trigger:", resp.status_code, resp.text[:200])
if resp.status_code >= 300:
    raise SystemExit("trigger failed")

run_id = None
key = None
sid = None
status = None
for _ in range(60):
    time.sleep(3)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                select r.id, r.status, s.id, s.text_object_key
                from monitor_runs r left join snapshots s on s.run_id = r.id
                where r.monitor_id = :mid order by r.created_at desc limit 1
                """
            ),
            {"mid": MID},
        ).fetchone()
    if row and row[1] in ("succeeded", "failed"):
        run_id, status, sid, key = row
        print(f"run {str(run_id)[:8]} status={status}")
        break

if key:
    from app.services import storage
    b = storage.get_bytes(key)
    if b:
        t = b.decode("utf-8", "replace")
        n_imgs = len(re.findall(r"!\[", t))
        print(f"stored len={len(t)} img_tokens={n_imgs}")
        print("first 150:", repr(t[:150]))
