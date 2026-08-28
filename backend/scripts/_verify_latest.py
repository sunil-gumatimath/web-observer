"""Verify stored blob for run fb318824."""
import os
import re

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")
engine = create_engine(os.environ["DATABASE_URL"])
from app.services import storage  # noqa: E402

with engine.connect() as conn:
    key = conn.execute(
        text(
            """
            select s.text_object_key from snapshots s
            join monitor_runs r on r.id = s.run_id
            where r.id::text like 'fb318824%'
            """
        )
    ).scalar()

t = storage.get_bytes(key).decode("utf-8", "replace")
n_imgs = len(re.findall(r"!\[", t))
print(f"stored len={len(t)} img_tokens={n_imgs}")
print("--- first 500 chars ---")
print(t[:500])
