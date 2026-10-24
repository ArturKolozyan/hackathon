from pathlib import Path

import pytest

from app.export_openapi import canonical
from app.main import app

MUST_PATHS = [
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/users",
    "/api/v1/users/{user_id}",
    "/api/v1/recurring-payments",
    "/api/v1/recurring-payments/{payment_id}",
    "/api/v1/payment-occurrences",
    "/api/v1/payment-occurrences/inbox",
    "/api/v1/payment-occurrences/{occurrence_id}",
    "/api/v1/payment-occurrences/{occurrence_id}/confirm",
    "/api/v1/payment-occurrences/{occurrence_id}/revoke",
    "/api/v1/payments/summary",
    "/api/v1/health",
]

STAR_PATHS = [
    "/api/v1/payments/calendar",
    "/api/v1/budgets",
    "/api/v1/budgets/report",
    "/api/v1/budgets/{budget_id}",
    "/api/v1/audit-logs",
    "/api/v1/telegram/status",
    "/api/v1/telegram/team-chat/link",
    "/api/v1/telegram/team-chat",
    "/api/v1/telegram/team-chat/test",
    "/api/v1/me/telegram",
    "/api/v1/me/telegram/link",
    "/api/v1/me/notifications",
    "/api/v1/notifications",
    "/api/v1/notifications/personal",
    "/api/v1/notifications/personal/email/test",
    "/api/v1/notifications/personal/telegram/test",
    "/api/v1/notifications/team/webhook",
    "/api/v1/notifications/team/webhook/test",
]


def test_openapi_contains_must_paths():
    schema = app.openapi()
    paths = schema["paths"]
    missing = [path for path in MUST_PATHS if path not in paths]
    assert missing == []
    missing_stars = [path for path in STAR_PATHS if path not in paths]
    assert missing_stars == []
    summary = paths["/api/v1/payments/summary"]["get"]
    assert any(param.get("name") == "as_of" for param in summary.get("parameters", []))
    patch = paths["/api/v1/payment-occurrences/{occurrence_id}"]["patch"]
    ref = patch["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    name = ref.rsplit("/", 1)[-1]
    assert "receipt_url" in schema["components"]["schemas"][name]["properties"]
    assert "receipt_note" in schema["components"]["schemas"][name]["properties"]


def _artifact():
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "openapi" / "openapi.json"
        if candidate.is_file():
            return candidate
    return None


def test_committed_openapi_matches_app():
    path = _artifact()
    if path is None:
        pytest.skip("openapi/openapi.json нет в этом окружении")
    assert path.read_text(encoding="utf-8") == canonical(app.openapi())
