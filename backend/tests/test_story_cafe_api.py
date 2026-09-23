"""Regression coverage for public menu, owner auth, and admin CRUD."""
import os
import uuid

import pytest
import requests


BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "tanujhaldar44@gmail.com", "password": "7teen@2026"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "admin"
    return session


def test_public_health_and_empty_or_valid_menu():
    health = requests.get(f"{BASE_URL}/api/health")
    assert health.status_code == 200 and health.json() == {"ok": True}
    products = requests.get(f"{BASE_URL}/api/products")
    categories = requests.get(f"{BASE_URL}/api/categories")
    assert products.status_code == categories.status_code == 200
    assert isinstance(products.json(), list) and isinstance(categories.json(), list)
    assert all("_id" not in item for item in products.json() + categories.json())


def test_mutation_rejected_without_session():
    response = requests.post(f"{BASE_URL}/api/admin/categories", json={"name": "TEST_unauth"})
    assert response.status_code == 401


def test_login_cookie_and_bruteforce_lockout():
    session = requests.Session()
    success = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "tanujhaldar44@gmail.com", "password": "7teen@2026"},
    )
    assert success.status_code == 200
    cookie = success.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=none" in cookie
    for _ in range(5):
        failed = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "tanujhaldar44@gmail.com", "password": "wrong-password"},
        )
        assert failed.status_code == 401
    locked = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "tanujhaldar44@gmail.com", "password": "wrong-password"},
    )
    assert locked.status_code in (423, 429)


def test_category_product_crud_and_public_availability(client):
    suffix = uuid.uuid4().hex[:8]
    category_name = f"TEST_Category_{suffix}"
    category_response = client.post(f"{BASE_URL}/api/admin/categories", json={"name": category_name})
    assert category_response.status_code == 200
    category = category_response.json()
    assert category["name"] == category_name and isinstance(category["id"], str)

    product = {
        "name": f"TEST_Product_{suffix}",
        "description": "Regression item",
        "category_id": category["id"],
        "price": 99,
        "image_url": "",
        "available": True,
        "featured": True,
    }
    create = client.post(f"{BASE_URL}/api/admin/products", json=product)
    assert create.status_code == 200
    created = create.json()
    product_id = created["id"]
    assert created["category_name"] == category_name and created["featured"] is True

    admin_products = client.get(f"{BASE_URL}/api/admin/products")
    assert admin_products.status_code == 200
    assert any(item["id"] == product_id for item in admin_products.json())
    public_products = requests.get(f"{BASE_URL}/api/products").json()
    assert any(item["id"] == product_id for item in public_products)

    blocked_delete = client.delete(f"{BASE_URL}/api/admin/categories/{category['id']}")
    assert blocked_delete.status_code == 409

    edit = {**product, "name": f"TEST_Edited_{suffix}", "price": 125}
    update = client.put(f"{BASE_URL}/api/admin/products/{product_id}", json=edit)
    assert update.status_code == 200
    assert any(item["name"] == edit["name"] and item["price"] == 125 for item in client.get(f"{BASE_URL}/api/admin/products").json())

    toggle = client.patch(f"{BASE_URL}/api/admin/products/{product_id}/availability?available=false")
    assert toggle.status_code == 200
    assert not any(item["id"] == product_id for item in requests.get(f"{BASE_URL}/api/products").json())

    delete = client.delete(f"{BASE_URL}/api/admin/products/{product_id}")
    assert delete.status_code == 200
    category_delete = client.delete(f"{BASE_URL}/api/admin/categories/{category['id']}")
    assert category_delete.status_code == 200


def test_upload_and_logout(client):
    client.headers.pop("Content-Type", None)
    image = client.post(
        f"{BASE_URL}/api/admin/upload",
        files={"file": ("test.png", b"not-a-real-png", "image/png")},
    )
    assert image.status_code == 200
    assert image.json()["image_url"].startswith("/uploads/")
    assert client.get(f"{BASE_URL}/api/auth/me").status_code == 200
    assert client.post(f"{BASE_URL}/api/auth/logout").status_code == 200
    assert client.get(f"{BASE_URL}/api/auth/me").status_code == 401