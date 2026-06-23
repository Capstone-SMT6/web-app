from fastapi.testclient import TestClient
import pytest

def test_create_user(client: TestClient):
    response = client.post(
        "/api/users/",
        json={
            "username": "testuser",
            "email": "testuser@example.com",
            "password": "testpassword123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "testuser@example.com"
    assert data["username"] == "testuser"
    assert "id" in data

def test_create_existing_user(client: TestClient):
    # First create
    client.post(
        "/api/users/",
        json={
            "username": "testuser2",
            "email": "testuser2@example.com",
            "password": "testpassword123"
        }
    )
    # Then try to create again
    response = client.post(
        "/api/users/",
        json={
            "username": "testuser2",
            "email": "testuser2@example.com",
            "password": "testpassword123"
        }
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already exists"

def test_login_user(client: TestClient):
    # Create user first
    client.post(
        "/api/users/",
        json={
            "username": "loginuser",
            "email": "loginuser@example.com",
            "password": "loginpassword123"
        }
    )
    
    # Login
    response = client.post(
        "/api/users/login",
        json={
            "email": "loginuser@example.com",
            "password": "loginpassword123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "loginuser@example.com"

def test_read_users(client: TestClient):
    # Create user first
    client.post(
        "/api/users/",
        json={
            "username": "readuser",
            "email": "readuser@example.com",
            "password": "readpassword123"
        }
    )
    
    # Login to get token
    login_response = client.post(
        "/api/users/login",
        json={
            "email": "readuser@example.com",
            "password": "readpassword123"
        }
    )
    token = login_response.json()["access_token"]
    
    # Get users with token
    response = client.get(
        "/api/users/",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(user["email"] == "readuser@example.com" for user in data)
