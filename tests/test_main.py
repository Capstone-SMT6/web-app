from fastapi.testclient import TestClient

def test_read_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"Hello": "World"}

def test_read_item(client: TestClient):
    response = client.get("/items/1?q=somequery")
    assert response.status_code == 200
    assert response.json() == {"item_id": 1, "q": "somequery"}
