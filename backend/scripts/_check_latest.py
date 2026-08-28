"""Latest runs + snapshot content quality after main-content rollout."""
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")
import os  # noqa: E402

engine = create_engine(os.environ["DATABASE_URL"])
from app.services import storage  # noqa: E402

now = datetime.now(timezone.utc)
print("UTC now:", now.isoformat(timespec="seconds"))

IMG_RE = re.compile(r"!\[")

with engine.connect() as conn:
    rows = conn.execute(
        text(
            """
            select m.name, m.mode, r.status, r.created_at,
                   s.id, s.text_object_key
            from monitor_runs r
            join monitors m on m.id = r.monitor_id
            left join snapshots s on s.run_id = r.id
            where r.created_at > now() - interval '45 minutes'
            order by r.created_at desc limit 14
            """
        )
    ).fetchall()

for name, mode, status, created, sid, key in rows:
    info = ""
    if key:
        b = storage.get_bytes(key)
        if b:
            t = b.decode("utf-8", "replace")
            imgs = len(IMG_RE.findall(t))
            first = t[:70].replace("\n", "\\n")
            info = f"len={len(t)} imgs={imgs} start={first!r}"
        else:
            info = "(blob miss)"
    print(f"{created:%H:%M} {status:<9} {name:<18} {mode:<12} snap={str(sid)[:8] if sid else '-'} {info}")
