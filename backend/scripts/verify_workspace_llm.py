"""Verify the workspace BYOK path end-to-end against the live Gemini provider.

Reads the workspace's stored (encrypted) key, resolves it through
``workspace_llm_config`` -> ``_effective_llm`` and runs the real
``enrich_change`` path.

    .venv312/Scripts/python.exe scripts/verify_workspace_llm.py <workspace_id>
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Workspace  # noqa: E402
from app.services.ai_summary import (  # noqa: E402
    _candidate_models,
    _effective_llm,
    enrich_change,
    workspace_llm_config,
)

DIFF = (
    "--- a/pricing.json\n"
    "+++ b/pricing.json\n"
    "@@ -1,4 +1,4 @@\n"
    '-  "plan": "pro",\n'
    '-  "price": "$19.99",\n'
    '-  "currency": "USD",\n'
    '+  "price": "$24.99",\n'
    '+  "currency": "USD",\n'
)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_workspace_llm.py <workspace_id>")
        return 2
    workspace_id = uuid.UUID(sys.argv[1])

    with SessionLocal() as session:
        workspace = session.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        ).scalar_one()

        llm = workspace_llm_config(workspace)
        if not llm:
            print("workspace has no LLM key configured")
            return 1

        cfg = _effective_llm(llm)
        print(f"scope={cfg['scope']} base={cfg['api_base']} model={cfg['model']}")
        print(f"failover candidates: {_candidate_models(cfg['model'], cfg['api_base'])}")

        enrichment = enrich_change(
            workspace_id=workspace_id,
            monitor_name="Acme Cloud Pricing",
            url="https://acme.example/pricing",
            mode="product_price",
            deterministic_summary="price field changed",
            diff_text=DIFF,
            enabled=True,
            llm=llm,
        )

    print(f"provider={enrichment.provider} model={enrichment.model}")
    print(f"category={enrichment.category} impact={enrichment.impact}")
    print(f"summary={enrichment.summary!r}")

    ok = (
        enrichment.provider == "llm"
        and "24.99" in (enrichment.summary or "")
        and enrichment.category == "pricing"
    )
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
