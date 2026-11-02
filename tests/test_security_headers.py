from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app


def test_non_demo_api_sets_security_headers_and_https_hsts(monkeypatch):
    monkeypatch.setenv("VILLAGE_COVERAGE_PUBLIC_DEMO", "false")
    response = TestClient(app, base_url="http://testserver").get("/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"] == (
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
    )
    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert "strict-transport-security" not in response.headers

    secure = TestClient(app, base_url="https://testserver").get("/health")
    assert secure.status_code == 200
    assert secure.headers["strict-transport-security"] == "max-age=31536000"
    assert "includesubdomains" not in secure.headers["strict-transport-security"].lower()
    assert "preload" not in secure.headers["strict-transport-security"].lower()
