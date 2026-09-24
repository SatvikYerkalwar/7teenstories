"""Tests for image upload (Emergent Object Storage), files serving, and SMS-on-ready background task."""
import io, os, time, pytest, requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://story-cafe-admin.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "tanujhaldar44@gmail.com"
ADMIN_PASSWORD = "7teen@2026"


def _img_bytes(fmt: str, size=(200, 150), color=(200, 100, 50)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def default_category(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/categories", timeout=15)
    assert r.status_code == 200
    cats = r.json()
    assert cats, "no categories seeded"
    # prefer Desserts (that's where Dark chocolate brownie lives)
    for c in cats:
        if c["name"].lower() == "desserts":
            return c
    return cats[0]


# ---------- Upload endpoint ----------

@pytest.mark.parametrize("fmt,ext,ct", [
    ("PNG", "png", "image/png"),
    ("JPEG", "jpg", "image/jpeg"),
    ("WEBP", "webp", "image/webp"),
])
def test_upload_valid_image_and_serve(admin_session, fmt, ext, ct):
    data = _img_bytes(fmt)
    # send with WRONG generic content type to prove magic-byte detection
    files = {"file": (f"TEST_upload.{ext}", data, "application/octet-stream")}
    r = admin_session.post(f"{BASE_URL}/api/admin/upload", files=files, timeout=60)
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text}"
    body = r.json()
    assert "image_url" in body and body["image_url"].startswith("/api/files/")
    assert body["image_url"].endswith(f".{ext}")

    # Public GET (no cookie): use fresh session
    url = f"{BASE_URL}{body['image_url']}"
    g = requests.get(url, timeout=30)
    assert g.status_code == 200, f"serve failed: {g.status_code}"
    assert g.headers.get("Content-Type", "").startswith(ct)
    assert len(g.content) == len(data), "byte-length mismatch"
    # Note: preview ingress (Cloudflare) rewrites Cache-Control to no-store; backend sets 'public, immutable'.
    # Skip strict cache-header assertion — infra overrides. Byte-perfect content + correct Content-Type is what matters.


def test_upload_non_image_rejected(admin_session):
    files = {"file": ("TEST_fake.png", b"this is not an image at all", "image/png")}
    r = admin_session.post(f"{BASE_URL}/api/admin/upload", files=files, timeout=30)
    assert r.status_code == 400
    assert "valid image" in r.text.lower()


def test_upload_too_large_rejected(admin_session):
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024 + 10)
    files = {"file": ("TEST_big.png", big, "image/png")}
    r = admin_session.post(f"{BASE_URL}/api/admin/upload", files=files, timeout=60)
    assert r.status_code == 400
    assert "5mb" in r.text.lower()


def test_upload_unauthenticated_rejected():
    data = _img_bytes("PNG")
    files = {"file": ("TEST.png", data, "image/png")}
    r = requests.post(f"{BASE_URL}/api/admin/upload", files=files, timeout=30)
    assert r.status_code == 401


def test_unknown_file_404():
    r = requests.get(f"{BASE_URL}/api/files/does-not-exist-xyz.png", timeout=15)
    assert r.status_code == 404


# ---------- Product image lifecycle ----------

@pytest.fixture(scope="module")
def created_product(admin_session, default_category):
    data = _img_bytes("PNG", color=(20, 200, 90))
    up = admin_session.post(f"{BASE_URL}/api/admin/upload",
                            files={"file": ("TEST_p.png", data, "application/octet-stream")}, timeout=60)
    assert up.status_code == 200
    image_url = up.json()["image_url"]
    p = admin_session.post(f"{BASE_URL}/api/admin/products", json={
        "name": "TEST_ImageProduct",
        "description": "test",
        "category_id": default_category["id"],
        "price": 99.0,
        "image_url": image_url,
        "available": True,
        "featured": False,
    }, timeout=30)
    assert p.status_code == 200, p.text
    prod = p.json()
    yield prod, image_url
    admin_session.delete(f"{BASE_URL}/api/admin/products/{prod['id']}", timeout=30)


def test_product_public_lists_with_image(created_product):
    prod, image_url = created_product
    r = requests.get(f"{BASE_URL}/api/products", timeout=15)
    assert r.status_code == 200
    found = next((x for x in r.json() if x["id"] == prod["id"]), None)
    assert found and found["image_url"] == image_url


def test_product_update_replaces_image(admin_session, created_product, default_category):
    prod, old_url = created_product
    data = _img_bytes("JPEG", color=(30, 30, 220))
    up = admin_session.post(f"{BASE_URL}/api/admin/upload",
                            files={"file": ("TEST_p2.jpg", data, "application/octet-stream")}, timeout=60)
    assert up.status_code == 200
    new_url = up.json()["image_url"]
    assert new_url != old_url
    r = admin_session.put(f"{BASE_URL}/api/admin/products/{prod['id']}", json={
        "name": prod["name"], "description": "test", "category_id": default_category["id"],
        "price": 99.0, "image_url": new_url, "available": True, "featured": False,
    }, timeout=30)
    assert r.status_code == 200
    # public product now has new url
    lst = requests.get(f"{BASE_URL}/api/products", timeout=15).json()
    found = next((x for x in lst if x["id"] == prod["id"]), None)
    assert found and found["image_url"] == new_url
    # old file still serves (no deletion)
    old = requests.get(f"{BASE_URL}{old_url}", timeout=15)
    assert old.status_code == 200
    assert old.headers.get("Content-Type", "").startswith("image/")


def test_migrated_brownie_serves(admin_session):
    r = requests.get(f"{BASE_URL}/api/products", timeout=15)
    assert r.status_code == 200
    br = next((x for x in r.json() if x["name"].lower() == "dark chocolate brownie"), None)
    assert br, "seed product 'Dark chocolate brownie' missing"
    assert br["image_url"].startswith("/api/files/"), f"not migrated: {br['image_url']}"
    g = requests.get(f"{BASE_URL}{br['image_url']}", timeout=30)
    assert g.status_code == 200
    assert g.headers.get("Content-Type", "").startswith("image/")


# ---------- Orders regression + ready SMS ----------

def _first_available_product():
    prods = requests.get(f"{BASE_URL}/api/products", timeout=15).json()
    for p in prods:
        if p.get("available", True):
            return p
    raise RuntimeError("no available product")


def test_admin_settings_sms_off(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/settings", timeout=15)
    assert r.status_code == 200
    assert r.json() == {"sms_configured": False}


def test_ready_sms_background_task(admin_session):
    p = _first_available_product()
    order = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST_ReadySms",
        "customer_phone": "9999999999",
        "order_type": "takeaway",
        "items": [{"product_id": p["id"], "quantity": 1}],
    }, timeout=30)
    assert order.status_code == 200, order.text
    oid = order.json()["id"]

    # PATCH to ready -> should return 200 quickly
    t0 = time.time()
    r = admin_session.patch(f"{BASE_URL}/api/admin/orders/{oid}/status", json={"status": "ready"}, timeout=15)
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert elapsed < 5, f"patch too slow ({elapsed}s) — background task blocking?"

    # Poll admin order for ready_sms fields
    deadline = time.time() + 8
    sms_status = sms_detail = None
    while time.time() < deadline:
        detail = admin_session.get(f"{BASE_URL}/api/admin/orders/{oid}", timeout=15).json()
        sms_status = detail.get("ready_sms_status")
        sms_detail = detail.get("ready_sms_detail")
        if sms_status:
            break
        time.sleep(0.5)
    assert sms_status == "failed", f"expected failed, got {sms_status}"
    assert sms_detail == "SMS not configured", f"detail={sms_detail}"

    # Setting 'ready' again should NOT clobber (guarded by status change AND ready_sms_sent_at absence)
    # Actually failure has no ready_sms_sent_at, but current status is 'ready' so branch skipped by status equality.
    r2 = admin_session.patch(f"{BASE_URL}/api/admin/orders/{oid}/status", json={"status": "ready"}, timeout=15)
    assert r2.status_code == 200
    time.sleep(1.0)
    detail2 = admin_session.get(f"{BASE_URL}/api/admin/orders/{oid}", timeout=15).json()
    assert detail2.get("ready_sms_status") == "failed"

    # Move to completed — should not add sms fields
    r3 = admin_session.patch(f"{BASE_URL}/api/admin/orders/{oid}/status", json={"status": "completed"}, timeout=15)
    assert r3.status_code == 200
    detail3 = admin_session.get(f"{BASE_URL}/api/admin/orders/{oid}", timeout=15).json()
    assert detail3["status"] == "completed"
    # sms fields remain from earlier 'ready' PATCH (they're not deleted, just not modified)
    assert detail3.get("ready_sms_status") == "failed"


def test_orders_basic_regression(admin_session):
    p = _first_available_product()
    o = requests.post(f"{BASE_URL}/api/orders", json={
        "customer_name": "TEST_Regress",
        "customer_phone": "9998887777",
        "order_type": "dine_in",
        "table_number": "12",
        "items": [{"product_id": p["id"], "quantity": 2}],
    }, timeout=30)
    assert o.status_code == 200
    num = o.json()["order_number"]
    t = requests.get(f"{BASE_URL}/api/orders/{num}", timeout=15)
    assert t.status_code == 200
    assert t.json()["order_number"] == num
    lst = admin_session.get(f"{BASE_URL}/api/admin/orders", timeout=15)
    assert lst.status_code == 200
    assert any(x["order_number"] == num for x in lst.json())
