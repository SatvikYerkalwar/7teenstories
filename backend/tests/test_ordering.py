"""Backend tests for online ordering feature (public + admin flows)."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = {"email": "tanujhaldar44@gmail.com", "password": "7teen@2026"}


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sample_products():
    products = requests.get(f"{BASE_URL}/api/products").json()
    available = [p for p in products if p.get("available", True)]
    assert len(available) >= 2, "Need at least 2 available products in DB"
    unavailable = [p for p in products if not p.get("available", True)]
    return {"available": available, "unavailable": unavailable}


# -------- GET /api/products (includes unavailable) --------
def test_products_includes_unavailable_with_flag(sample_products):
    assert len(sample_products["unavailable"]) >= 1, "Expected at least one unavailable product (Cheese Nachos)"
    for p in sample_products["available"] + sample_products["unavailable"]:
        assert "available" in p and isinstance(p["available"], bool)


# -------- POST /api/orders happy path --------
def test_place_order_creates_and_recomputes_totals(sample_products):
    p1, p2 = sample_products["available"][:2]
    payload = {
        "customer_name": "TEST_Customer",
        "customer_phone": "9876543210",
        "order_type": "takeaway",
        "items": [
            {"product_id": p1["id"], "quantity": 2},
            {"product_id": p2["id"], "quantity": 1},
            # Duplicate to verify merge
            {"product_id": p1["id"], "quantity": 1},
        ],
    }
    r = requests.post(f"{BASE_URL}/api/orders", json=payload)
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["order_number"].startswith("ST-")
    assert int(o["order_number"].split("-")[1]) >= 1001
    assert o["status"] == "new"
    assert o["payment_method"] == "pay_at_cafe"
    # Merge duplicate p1 => qty 3
    p1_line = next(i for i in o["items"] if i["product_id"] == p1["id"])
    assert p1_line["quantity"] == 3
    assert p1_line["product_name_snapshot"] == p1["name"]
    assert p1_line["price_snapshot"] == float(p1["price"])
    # Total recomputed from DB
    expected = round(float(p1["price"]) * 3 + float(p2["price"]) * 1, 2)
    assert o["subtotal"] == expected and o["total"] == expected


def test_place_order_ignores_client_supplied_prices(sample_products):
    p = sample_products["available"][0]
    r = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST_Malicious",
        "customer_phone": "9998887777",
        "order_type": "takeaway",
        "items": [{"product_id": p["id"], "quantity": 1, "price": 0.01}],
    })
    assert r.status_code == 200
    assert r.json()["total"] == float(p["price"])


# -------- Validation errors --------
def test_dine_in_requires_table_number(sample_products):
    p = sample_products["available"][0]
    r = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST", "customer_phone": "9876543210",
        "order_type": "dine_in", "items": [{"product_id": p["id"], "quantity": 1}],
    })
    assert r.status_code == 400
    assert "table" in r.json()["detail"].lower()


def test_unavailable_product_rejected(sample_products):
    if not sample_products["unavailable"]:
        pytest.skip("no unavailable product")
    u = sample_products["unavailable"][0]
    r = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST", "customer_phone": "9876543210",
        "order_type": "takeaway", "items": [{"product_id": u["id"], "quantity": 1}],
    })
    assert r.status_code == 400
    assert u["name"] in r.json()["detail"]


def test_unknown_product_rejected():
    r = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST", "customer_phone": "9876543210",
        "order_type": "takeaway", "items": [{"product_id": "nonexistent-id", "quantity": 1}],
    })
    assert r.status_code == 400


def test_invalid_phone_422(sample_products):
    p = sample_products["available"][0]
    r = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST", "customer_phone": "abc12",
        "order_type": "takeaway", "items": [{"product_id": p["id"], "quantity": 1}],
    })
    assert r.status_code == 422


def test_empty_items_422():
    r = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST", "customer_phone": "9876543210",
        "order_type": "takeaway", "items": [],
    })
    assert r.status_code == 422


def test_quantity_over_20_422(sample_products):
    p = sample_products["available"][0]
    r = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST", "customer_phone": "9876543210",
        "order_type": "takeaway", "items": [{"product_id": p["id"], "quantity": 25}],
    })
    assert r.status_code == 422


# -------- GET /api/orders/{number} public with masked phone --------
def test_track_order_masks_phone_case_insensitive(sample_products):
    p = sample_products["available"][0]
    create = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST_Track", "customer_phone": "9123456789",
        "order_type": "takeaway", "items": [{"product_id": p["id"], "quantity": 1}],
    }).json()
    num = create["order_number"]
    r = requests.get(f"{BASE_URL}/api/orders/{num.lower()}")
    assert r.status_code == 200
    data = r.json()
    assert data["customer_phone"].endswith("6789")
    assert data["customer_phone"].startswith("X")
    assert "6789" in data["customer_phone"] and "9123" not in data["customer_phone"]
    assert len(data["items"]) == 1


def test_track_unknown_404():
    r = requests.get(f"{BASE_URL}/api/orders/ST-999999")
    assert r.status_code == 404


# -------- Admin endpoints --------
def test_admin_orders_requires_auth():
    assert requests.get(f"{BASE_URL}/api/admin/orders").status_code == 401


def test_admin_orders_list_filter_and_full_phone(admin, sample_products):
    p = sample_products["available"][0]
    create = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST_Admin", "customer_phone": "9000000123",
        "order_type": "takeaway", "items": [{"product_id": p["id"], "quantity": 1}],
    }).json()
    r = admin.get(f"{BASE_URL}/api/admin/orders")
    assert r.status_code == 200
    orders = r.json()
    assert orders and orders[0]["created_at"] >= orders[-1]["created_at"]  # newest first
    found = next((o for o in orders if o["order_number"] == create["order_number"]), None)
    assert found and found["customer_phone"] == "9000000123"  # unmasked
    assert isinstance(found["items"], list) and len(found["items"]) == 1
    # Filter by status
    r2 = admin.get(f"{BASE_URL}/api/admin/orders?status=new")
    assert r2.status_code == 200
    assert all(o["status"] == "new" for o in r2.json())


def test_admin_update_status_and_validation(admin, sample_products):
    p = sample_products["available"][0]
    create = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST_Status", "customer_phone": "9111222333",
        "order_type": "takeaway", "items": [{"product_id": p["id"], "quantity": 1}],
    }).json()
    oid = create["id"]
    # Valid transitions
    for s in ["accepted", "preparing", "ready", "completed"]:
        r = admin.patch(f"{BASE_URL}/api/admin/orders/{oid}/status", json={"status": s})
        assert r.status_code == 200 and r.json()["status"] == s
    # Invalid status
    bad = admin.patch(f"{BASE_URL}/api/admin/orders/{oid}/status", json={"status": "shipped"})
    assert bad.status_code == 400
    # Unauthenticated
    un = requests.patch(f"{BASE_URL}/api/admin/orders/{oid}/status", json={"status": "cancelled"})
    assert un.status_code == 401


# -------- Snapshot integrity --------
def test_snapshot_survives_product_edit_and_delete(admin):
    # Create category + product to modify
    suffix = uuid.uuid4().hex[:6]
    cat = admin.post(f"{BASE_URL}/api/admin/categories", json={"name": f"TEST_Snap_{suffix}"}).json()
    prod_payload = {"name": f"TEST_SnapProd_{suffix}", "description": "", "category_id": cat["id"],
                    "price": 111, "image_url": "", "available": True, "featured": False}
    prod = admin.post(f"{BASE_URL}/api/admin/products", json=prod_payload).json()
    try:
        order = requests.post(f"{BASE_URL}/api/orders", json={
            "customer_name": "TEST_Snap", "customer_phone": "9222333444",
            "order_type": "takeaway", "items": [{"product_id": prod["id"], "quantity": 2}],
        }).json()
        num = order["order_number"]
        # Edit price + name
        edited = {**prod_payload, "name": f"TEST_Renamed_{suffix}", "price": 999}
        assert admin.put(f"{BASE_URL}/api/admin/products/{prod['id']}", json=edited).status_code == 200
        r = requests.get(f"{BASE_URL}/api/orders/{num}").json()
        it = r["items"][0]
        assert it["product_name_snapshot"] == prod_payload["name"]
        assert it["price_snapshot"] == 111.0
        assert r["total"] == 222.0
        # Delete product; snapshot must remain
        assert admin.delete(f"{BASE_URL}/api/admin/products/{prod['id']}").status_code == 200
        r2 = requests.get(f"{BASE_URL}/api/orders/{num}").json()
        assert r2["items"][0]["price_snapshot"] == 111.0
        assert r2["items"][0]["product_name_snapshot"] == prod_payload["name"]
    finally:
        admin.delete(f"{BASE_URL}/api/admin/products/{prod['id']}")
        admin.delete(f"{BASE_URL}/api/admin/categories/{cat['id']}")


# -------- Uploads via /api/uploads --------
def test_uploads_served_via_api_prefix(admin):
    admin.headers.pop("Content-Type", None)
    # 1x1 PNG
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c626000000000ffff030000060005574c9dfc0000"
        "00004945" + "4e44ae426082"
    )
    up = admin.post(f"{BASE_URL}/api/admin/upload",
                    files={"file": ("t.png", png_bytes, "image/png")})
    admin.headers["Content-Type"] = "application/json"
    assert up.status_code == 200
    url = up.json()["image_url"]  # /uploads/xxx.png
    fname = url.rsplit("/", 1)[-1]
    r = requests.get(f"{BASE_URL}/api/uploads/{fname}")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/")


# -------- Sequential order numbers --------
def test_order_numbers_are_sequential(sample_products):
    p = sample_products["available"][0]
    def make():
        return requests.post(f"{BASE_URL}/api/orders", json={
            "customer_name": "TEST_Seq", "customer_phone": "9333444555",
            "order_type": "takeaway", "items": [{"product_id": p["id"], "quantity": 1}],
        }).json()["order_number"]
    a = int(make().split("-")[1])
    b = int(make().split("-")[1])
    assert b == a + 1
