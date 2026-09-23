"""Backend tests: category rename/reorder/delete + featured product flow."""
import os, uuid, requests, pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://story-cafe-admin.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "tanujhaldar44@gmail.com"
ADMIN_PASSWORD = "7teen@2026"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


def test_health():
    r = requests.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200 and r.json().get("ok") is True


def test_auth_me(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_list_admin_categories(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/categories")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_rename_category_duplicate_rejected(admin_session):
    cats = admin_session.get(f"{BASE_URL}/api/admin/categories").json()
    assert len(cats) >= 2
    target = cats[0]
    other = cats[1]
    # Try renaming target to other's name -> should 409
    r = admin_session.put(f"{BASE_URL}/api/admin/categories/{target['id']}", json={"name": other["name"]})
    assert r.status_code == 409, f"expected 409, got {r.status_code} {r.text}"


def test_rename_category_success_and_revert(admin_session):
    cats = admin_session.get(f"{BASE_URL}/api/admin/categories").json()
    target = cats[0]
    original = target["name"]
    new_name = f"TEST_{uuid.uuid4().hex[:6]}"
    r = admin_session.put(f"{BASE_URL}/api/admin/categories/{target['id']}", json={"name": new_name})
    assert r.status_code == 200
    # verify persisted
    cats2 = admin_session.get(f"{BASE_URL}/api/admin/categories").json()
    got = next(c for c in cats2 if c["id"] == target["id"])
    assert got["name"] == new_name
    # revert
    admin_session.put(f"{BASE_URL}/api/admin/categories/{target['id']}", json={"name": original})


def test_reorder_categories_persists(admin_session):
    cats = admin_session.get(f"{BASE_URL}/api/admin/categories").json()
    ids = [c["id"] for c in cats]
    reversed_ids = list(reversed(ids))
    r = admin_session.post(f"{BASE_URL}/api/admin/categories/reorder", json={"ids": reversed_ids})
    assert r.status_code == 200
    cats2 = admin_session.get(f"{BASE_URL}/api/admin/categories").json()
    assert [c["id"] for c in cats2] == reversed_ids
    # restore
    admin_session.post(f"{BASE_URL}/api/admin/categories/reorder", json={"ids": ids})


def test_delete_category_with_products_returns_409(admin_session):
    # create a test category
    name = f"TEST_DEL_{uuid.uuid4().hex[:6]}"
    r = admin_session.post(f"{BASE_URL}/api/admin/categories", json={"name": name})
    assert r.status_code == 200
    cat = r.json()
    # add product
    p = admin_session.post(f"{BASE_URL}/api/admin/products", json={
        "name": f"TEST_P_{uuid.uuid4().hex[:5]}", "description": "d",
        "category_id": cat["id"], "price": 100.0, "available": True, "featured": False,
    })
    assert p.status_code == 200
    product = p.json()
    # attempt delete category
    d = admin_session.delete(f"{BASE_URL}/api/admin/categories/{cat['id']}")
    assert d.status_code == 409
    # cleanup
    admin_session.delete(f"{BASE_URL}/api/admin/products/{product['id']}")
    admin_session.delete(f"{BASE_URL}/api/admin/categories/{cat['id']}")


def test_featured_product_and_public_listing(admin_session):
    # get any category
    cats = admin_session.get(f"{BASE_URL}/api/admin/categories").json()
    assert cats
    cat = cats[0]
    p = admin_session.post(f"{BASE_URL}/api/admin/products", json={
        "name": f"TEST_FEAT_{uuid.uuid4().hex[:5]}", "description": "featured",
        "category_id": cat["id"], "price": 199.0, "available": True, "featured": True,
    })
    assert p.status_code == 200
    prod = p.json()
    assert prod["featured"] is True
    # public list should contain it
    pub = requests.get(f"{BASE_URL}/api/products").json()
    assert any(x["id"] == prod["id"] for x in pub)
    # toggle unavailable -> hidden from public
    t = admin_session.patch(f"{BASE_URL}/api/admin/products/{prod['id']}/availability?available=false")
    assert t.status_code == 200
    pub2 = requests.get(f"{BASE_URL}/api/products").json()
    assert not any(x["id"] == prod["id"] for x in pub2)
    # cleanup
    admin_session.delete(f"{BASE_URL}/api/admin/products/{prod['id']}")
