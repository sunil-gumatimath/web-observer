from app.services.bulk_import import _normalize_row, parse_csv
from app.services.plans import PLANS, get_plan
from app.services.webhooks import new_webhook_secret, sign_payload
from app.models.entities import Workspace


def test_plans_exist() -> None:
    assert "free" in PLANS and "pro" in PLANS
    ws = Workspace(name="x", plan="pro")
    assert get_plan(ws).max_monitors >= PLANS["free"].max_monitors


def test_parse_csv_and_normalize() -> None:
    text = "name,url,mode\nA,https://example.com/,whole_page\n"
    rows = parse_csv(text)
    assert len(rows) == 1
    n = _normalize_row(rows[0])
    assert n["name"] == "A"
    assert n["url"].startswith("https://")


def test_webhook_signature_stable() -> None:
    secret = new_webhook_secret()
    body = b'{"a":1}'
    s1 = sign_payload(secret, body, "100")
    s2 = sign_payload(secret, body, "100")
    assert s1 == s2
    assert s1 != sign_payload(secret, body, "101")
