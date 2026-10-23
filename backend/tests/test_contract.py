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


def test_openapi_contains_must_paths():
    paths = app.openapi()["paths"]
    missing = [path for path in MUST_PATHS if path not in paths]
    assert missing == []


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
