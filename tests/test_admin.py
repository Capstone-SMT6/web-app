from fastapi.testclient import TestClient
import pytest

def setup_admin_user(client: TestClient):
    # First, try to create an admin user via standard users endpoint.
    # Note: the users create endpoint doesn't allow setting is_admin,
    # so we might need a workaround or test the normal user access first.
    # We will simulate an admin login by inserting directly into DB or 
    # relying on the test structure. For now, let's create a standard user
    # and expect 403 when they try to access admin endpoints.
    client.post(
        "/api/users/",
        json={
            "username": "notadmin",
            "email": "notadmin@example.com",
            "password": "password123"
        }
    )
    
def test_admin_api_login_unauthorized(client: TestClient):
    setup_admin_user(client)
    
    # Try logging into admin with normal user credentials
    response = client.post(
        "/admin/api/login",
        json={
            "email": "notadmin@example.com",
            "password": "password123"
        }
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access only"

def test_admin_api_login_invalid_credentials(client: TestClient):
    response = client.post(
        "/admin/api/login",
        json={
            "email": "wrong@example.com",
            "password": "wrongpassword"
        }
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"

def test_admin_api_endpoints_without_token(client: TestClient):
    response = client.get("/admin/api/me")
    assert response.status_code == 401
    
    response = client.get("/admin/api/stats")
    assert response.status_code == 401
    
    response = client.get("/admin/api/users")
    assert response.status_code == 401
    
    response = client.get("/admin/api/exercises")
    assert response.status_code == 401
