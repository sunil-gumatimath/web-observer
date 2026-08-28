"""Fingerprint: re-run every extraction variant on the newest snapshot's html."""
import os
import re

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")
engine = create_engine(os.environ["DATABASE_URL"])
from app.services import storage  # noqa: E402

with engine.connect() as conn:
    row = conn.execute(
        text(
            """
            select m.name, m.mode, m.js_required, r.id,
                   s.raw_object_key, s.text_object_key, s.created_at
            from snapshots s
            join monitors m on m.id = s.monitor_id
            join monitor_runs r on r.id = s.run_id
            where s.id::text like 'a9bf395c%'
            """
        )
    ).fetchone()

name, mode, js, rid, raw_key, txt_key, created = row
print(f"monitor={name} mode={mode} js={js} run={str(rid)[:8]} created={created}")

html = storage.get_bytes(raw_key).decode("utf-8", "replace")
stored = storage.get_bytes(txt_key).decode("utf-8", "replace")
print("raw html <img> count:", html.lower().count("<img"))
print("stored len:", len(stored))

from app.services.extract import extract_main_markdown, extract_markdown  # noqa: E402

main = extract_main_markdown(html)
whole = extract_markdown(html)
IMG = re.compile(r"!\[")
main_n = "None" if main is None else f"len={len(main)} imgs={len(IMG.findall(main))}"
whole_n = f"len={len(whole)} imgs={len(IMG.findall(whole))}"
print("\ncurrent MAIN   :", main_n)
print("current WHOLE  :", whole_n)
print("stored matches current WHOLE exactly?", stored == whole)
print("stored starts:", stored[:60])
