from fastapi.testclient import TestClient
from limiter import limiter
import pytest

def test_secure_headers(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    
    headers = response.headers
    assert "Content-Security-Policy" in headers
    assert "Permissions-Policy" in headers
    assert "Referrer-Policy" in headers
    assert "Strict-Transport-Security" in headers
    assert "X-Content-Type-Options" in headers
    assert "X-Frame-Options" in headers
    
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "max-age=31536000" in headers["Strict-Transport-Security"]
    assert "includeSubDomains" in headers["Strict-Transport-Security"]
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "camera=()" in headers["Permissions-Policy"]
    assert "microphone=()" in headers["Permissions-Policy"]
    assert "geolocation=()" in headers["Permissions-Policy"]

def test_rate_limiting(client: TestClient):
    # Enable the limiter specifically for this test
    limiter.enabled = True
    try:
        # Hit /api/users/otp/send multiple times. The rate limit is 5 attempts per 15 minutes.
        for i in range(5):
            resp = client.post(
                "/api/users/otp/send",
                json={"email": f"test_limiter_{i}@example.com", "purpose": "register"}
            )
            assert resp.status_code in (200, 400) # 400 if email registered (which is not 429)
            
        # The 6th request should exceed the limit and return 429
        resp = client.post(
            "/api/users/otp/send",
            json={"email": "excessive@example.com", "purpose": "register"}
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert int(resp.headers["Retry-After"]) > 0
    finally:
        # Restore limiter.enabled to False so other tests are unaffected
        limiter.enabled = False
