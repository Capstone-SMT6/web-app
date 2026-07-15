from fastapi.testclient import TestClient
from sqlmodel import Session
from tests.test_users import create_test_user_helper
import pytest

def setup_admin_user(client: TestClient, session: Session):
    create_test_user_helper(client, session, "notadmin", "notadmin@example.com", "password123")
    
def test_admin_api_login_unauthorized(client: TestClient, session: Session):
    setup_admin_user(client, session)
    
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
