from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / '.env')

import os, uuid, logging, secrets, asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
import bcrypt, jwt
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, UploadFile, File, Form, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from storage import detect_image, put_object, get_object, init_storage, APP_NAME, IMAGE_TYPES
from sms import send_sms, sms_configured

ROOT = Path(__file__).parent
UPLOADS = ROOT / "uploads"
UPLOADS.mkdir(exist_ok=True)
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="7teen Stories Cafe API")
api = APIRouter(prefix="/api")
JWT_ALGORITHM = "HS256"
ALLOWED_IMAGES = {"image/jpeg", "image/png", "image/webp"}

def now(): return datetime.now(timezone.utc).isoformat()
def clean(doc):
    if not doc: return None
    doc.pop("_id", None)
    return doc
def token_for(user_id, email):
    return jwt.encode({"sub": user_id, "email": email, "role": "admin", "exp": datetime.now(timezone.utc)+timedelta(hours=12)}, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)
def hash_password(password): return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
def verify_password(password, hashed): return bcrypt.checkpw(password.encode(), hashed.encode())

async def current_admin(request: Request):
    token = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token: raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload.get("sub"), "role": "admin"}, {"_id": 0})
        if not user: raise HTTPException(401, "Admin account not found")
        return user
    except jwt.PyJWTError: raise HTTPException(401, "Session expired")

class Login(BaseModel): email: str; password: str
class CategoryIn(BaseModel): name: str = Field(min_length=1, max_length=60)
class ReorderIn(BaseModel): ids: list[str]
class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=100); description: str = ""
    category_id: str; price: float = Field(gt=0); image_url: str = ""
    available: bool = True; featured: bool = False
ORDER_STATUSES = ["new", "accepted", "preparing", "ready", "completed", "cancelled"]
class OrderItemIn(BaseModel): product_id: str; quantity: int = Field(ge=1, le=20)
class OrderIn(BaseModel):
    customer_name: str = Field(min_length=1, max_length=60)
    customer_phone: str = Field(pattern=r"^[0-9]{10,15}$")
    order_type: str = Field(pattern=r"^(dine_in|takeaway)$")
    table_number: Optional[str] = Field(default=None, max_length=10)
    items: list[OrderItemIn] = Field(min_length=1, max_length=50)
class StatusIn(BaseModel): status: str

async def order_with_items(order):
    items = await db.order_items.find({"order_id": order["id"]}, {"_id": 0}).to_list(100)
    return order | {"items": items}
async def attach_items(orders):
    ids = [o["id"] for o in orders]
    items = await db.order_items.find({"order_id": {"$in": ids}}, {"_id": 0}).to_list(5000)
    by_order = {}
    for it in items: by_order.setdefault(it["order_id"], []).append(it)
    return [o | {"items": by_order.get(o["id"], [])} for o in orders]
def mask_phone(phone): return "X" * max(len(phone) - 4, 0) + phone[-4:]

@api.get("/health")
async def health(): return {"ok": True}

@api.post("/auth/login")
async def login(data: Login, response: Response, request: Request):
    email = data.email.lower().strip()
    # Track by normalized account email so rotating proxy/ingress IPs cannot bypass lockout.
    identifier = email
    attempt = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    if attempt and attempt.get("locked_until", "") > now():
        raise HTTPException(429, "Too many failed attempts. Please try again in 15 minutes.")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        failures = (attempt.get("failures", 0) if attempt else 0) + 1
        update = {"identifier": identifier, "failures": failures, "updated_at": now()}
        if failures >= 5: update["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        await db.login_attempts.update_one({"identifier": identifier}, {"$set": update}, upsert=True)
        raise HTTPException(401, "Invalid email or password")
    await db.login_attempts.delete_one({"identifier": identifier})
    response.set_cookie("access_token", token_for(user["id"], user["email"]), httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    return {"id": user["id"], "email": user["email"], "role": user["role"]}

@api.post("/auth/logout")
async def logout(response: Response, _: dict = Depends(current_admin)):
    response.delete_cookie("access_token", path="/"); return {"ok": True}

@api.get("/auth/me")
async def me(user: dict = Depends(current_admin)): return {"id": user["id"], "email": user["email"], "role": user["role"]}

@api.get("/categories")
async def public_categories(): return await db.categories.find({}, {"_id": 0}).sort("position", 1).to_list(100)

@api.get("/products")
async def public_products(): return await db.products.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)

@api.post("/orders")
async def place_order(data: OrderIn):
    if data.order_type == "dine_in" and not (data.table_number or "").strip(): raise HTTPException(400, "Please enter your table number")
    merged = {}
    for it in data.items: merged[it.product_id] = merged.get(it.product_id, 0) + it.quantity
    products = {p["id"]: p for p in await db.products.find({"id": {"$in": list(merged)}}, {"_id": 0}).to_list(100)}
    items, subtotal = [], 0.0
    for pid, qty in merged.items():
        p = products.get(pid)
        if not p: raise HTTPException(400, "One of the items is no longer on the menu")
        if not p.get("available", True): raise HTTPException(400, f"{p['name']} is currently unavailable")
        line = round(float(p["price"]) * qty, 2); subtotal += line
        items.append({"id": str(uuid.uuid4()), "product_id": pid, "product_name_snapshot": p["name"], "price_snapshot": float(p["price"]), "product_image_snapshot": p.get("image_url", ""), "quantity": qty, "subtotal": line})
    counter = await db.counters.find_one_and_update({"_id": "order_number"}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    order = {"id": str(uuid.uuid4()), "order_number": f"ST-{counter['seq']}", "customer_name": data.customer_name.strip(), "customer_phone": data.customer_phone,
             "order_type": data.order_type, "table_number": data.table_number.strip() if data.order_type == "dine_in" else None,
             "subtotal": round(subtotal, 2), "total": round(subtotal, 2), "status": "new", "payment_method": "pay_at_cafe", "payment_status": "pending", "created_at": now(), "updated_at": now()}
    await db.orders.insert_one(dict(order))
    for it in items: await db.order_items.insert_one(dict(it) | {"order_id": order["id"]})
    return order | {"items": [it | {"order_id": order["id"]} for it in items]}

@api.get("/orders/{order_number}")
async def track_order(order_number: str):
    order = await db.orders.find_one({"order_number": order_number.upper()}, {"_id": 0})
    if not order: raise HTTPException(404, "We couldn't find that order")
    full = await order_with_items(order)
    return full | {"customer_phone": mask_phone(full["customer_phone"])}

@api.get("/admin/orders")
async def admin_orders(status: Optional[str] = None, limit: int = 300, _: dict = Depends(current_admin)):
    query = {"status": status} if status else {}
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 1000))
    return await attach_items(orders)

@api.get("/admin/orders/{order_id}")
async def admin_order(order_id: str, _: dict = Depends(current_admin)):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order: raise HTTPException(404, "Order not found")
    return await order_with_items(order)

@api.patch("/admin/orders/{order_id}/status")
async def update_order_status(order_id: str, data: StatusIn, background: BackgroundTasks, _: dict = Depends(current_admin)):
    if data.status not in ORDER_STATUSES: raise HTTPException(400, "Unknown status")
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order: raise HTTPException(404, "Order not found")
    await db.orders.update_one({"id": order_id}, {"$set": {"status": data.status, "updated_at": now()}})
    if data.status == "ready" and order["status"] != "ready" and not order.get("ready_sms_sent_at"):
        background.add_task(notify_ready, order)
    return {"ok": True, "status": data.status}

async def notify_ready(order):
    where = f"we're bringing it to table {order['table_number']}" if order["order_type"] == "dine_in" and order.get("table_number") else "please collect it at the counter"
    body = f"7teen Stories Cafe: Hi {order['customer_name']}, your order {order['order_number']} is ready - {where}. Thank you for visiting!"
    ok, detail = await send_sms(order["customer_phone"], body)
    update = {"ready_sms_status": "sent" if ok else "failed", "ready_sms_detail": detail}
    if ok: update["ready_sms_sent_at"] = now()
    await db.orders.update_one({"id": order["id"]}, {"$set": update})

@api.get("/admin/categories")
async def admin_categories(_: dict = Depends(current_admin)): return await db.categories.find({}, {"_id": 0}).sort("position", 1).to_list(100)

@api.post("/admin/categories")
async def add_category(data: CategoryIn, _: dict = Depends(current_admin)):
    if await db.categories.find_one({"name": {"$regex": f"^{data.name.strip()}$", "$options": "i"}}): raise HTTPException(409, "Category already exists")
    doc = {"id": str(uuid.uuid4()), "name": data.name.strip(), "position": await db.categories.count_documents({}), "created_at": now()}
    await db.categories.insert_one(doc); return clean(doc)

@api.post("/admin/categories/reorder")
async def reorder_categories(data: ReorderIn, _: dict = Depends(current_admin)):
    for position, cid in enumerate(data.ids):
        await db.categories.update_one({"id": cid}, {"$set": {"position": position}})
    return {"ok": True}

@api.put("/admin/categories/{category_id}")
async def rename_category(category_id: str, data: CategoryIn, _: dict = Depends(current_admin)):
    name = data.name.strip()
    if await db.categories.find_one({"id": {"$ne": category_id}, "name": {"$regex": f"^{name}$", "$options": "i"}}): raise HTTPException(409, "Another category already uses that name")
    result = await db.categories.update_one({"id": category_id}, {"$set": {"name": name}})
    if not result.matched_count: raise HTTPException(404, "Category not found")
    await db.products.update_many({"category_id": category_id}, {"$set": {"category_name": name}})
    return {"ok": True}

@api.delete("/admin/categories/{category_id}")
async def delete_category(category_id: str, _: dict = Depends(current_admin)):
    if await db.products.find_one({"category_id": category_id}): raise HTTPException(409, "Move products before deleting this category")
    result = await db.categories.delete_one({"id": category_id})
    if not result.deleted_count: raise HTTPException(404, "Category not found")
    return {"ok": True}

@api.get("/admin/products")
async def admin_products(_: dict = Depends(current_admin)): return await db.products.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)

@api.post("/admin/products")
async def add_product(data: ProductIn, _: dict = Depends(current_admin)):
    category = await db.categories.find_one({"id": data.category_id}, {"_id": 0})
    if not category: raise HTTPException(400, "Choose a valid category")
    doc = data.model_dump() | {"id": str(uuid.uuid4()), "category_name": category["name"], "created_at": now(), "updated_at": now()}
    await db.products.insert_one(doc); return clean(doc)

@api.put("/admin/products/{product_id}")
async def edit_product(product_id: str, data: ProductIn, _: dict = Depends(current_admin)):
    category = await db.categories.find_one({"id": data.category_id}, {"_id": 0})
    if not category: raise HTTPException(400, "Choose a valid category")
    doc = data.model_dump() | {"category_name": category["name"], "updated_at": now()}
    result = await db.products.update_one({"id": product_id}, {"$set": doc})
    if not result.matched_count: raise HTTPException(404, "Product not found")
    return {"ok": True}

@api.patch("/admin/products/{product_id}/availability")
async def toggle_product(product_id: str, available: bool = True, _: dict = Depends(current_admin)):
    result = await db.products.update_one({"id": product_id}, {"$set": {"available": available, "updated_at": now()}})
    if not result.matched_count: raise HTTPException(404, "Product not found")
    return {"ok": True}

@api.delete("/admin/products/{product_id}")
async def delete_product(product_id: str, _: dict = Depends(current_admin)):
    result = await db.products.delete_one({"id": product_id})
    if not result.deleted_count: raise HTTPException(404, "Product not found")
    return {"ok": True}

@api.post("/admin/upload")
async def upload_image(file: UploadFile = File(...), _: dict = Depends(current_admin)):
    content = await file.read()
    if len(content) > 5 * 1024 * 1024: raise HTTPException(400, "Image must be under 5MB")
    ext = detect_image(content)
    if not ext: raise HTTPException(400, "That file isn't a valid image. Use JPG, PNG, or WebP")
    name = f"{uuid.uuid4()}.{ext}"
    try: result = await put_object(f"{APP_NAME}/products/{name}", content, IMAGE_TYPES[ext])
    except Exception as e:
        logging.error("Upload to storage failed: %s", e)
        raise HTTPException(502, "Image upload failed. Please try again.")
    await db.files.insert_one({"id": name, "storage_path": result["path"], "content_type": IMAGE_TYPES[ext], "original_filename": file.filename, "size": len(content), "is_deleted": False, "created_at": now()})
    return {"image_url": f"/api/files/{name}"}

@api.get("/files/{name}")
async def serve_file(name: str):
    record = await db.files.find_one({"id": name, "is_deleted": False}, {"_id": 0})
    if not record: raise HTTPException(404, "File not found")
    try: data, _ct = await get_object(record["storage_path"])
    except Exception as e:
        logging.error("Storage read failed: %s", e)
        raise HTTPException(502, "Image temporarily unavailable")
    return Response(content=data, media_type=record["content_type"], headers={"Cache-Control": "public, max-age=31536000, immutable"})

async def migrate_local_uploads():
    async for p in db.products.find({"image_url": {"$regex": "^/uploads/"}}, {"_id": 0, "id": 1, "image_url": 1}):
        local = UPLOADS / p["image_url"].split("/")[-1]
        if not local.exists(): continue
        content = local.read_bytes(); ext = detect_image(content)
        if not ext: continue
        name = f"{uuid.uuid4()}.{ext}"
        try: result = await put_object(f"{APP_NAME}/products/{name}", content, IMAGE_TYPES[ext])
        except Exception as e: logging.error("Migration failed for %s: %s", p["id"], e); continue
        await db.files.insert_one({"id": name, "storage_path": result["path"], "content_type": IMAGE_TYPES[ext], "original_filename": local.name, "size": len(content), "is_deleted": False, "created_at": now()})
        await db.products.update_one({"id": p["id"]}, {"$set": {"image_url": f"/api/files/{name}"}})
        logging.info("Migrated image for product %s", p["id"])

@api.get("/admin/settings")
async def admin_settings(_: dict = Depends(current_admin)): return {"sms_configured": sms_configured()}

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.categories.create_index("id", unique=True)
    await db.products.create_index("id", unique=True)
    await db.login_attempts.create_index("identifier", unique=True)
    await db.orders.create_index("id", unique=True)
    await db.orders.create_index("order_number", unique=True)
    await db.orders.create_index([("created_at", -1)])
    await db.order_items.create_index("order_id")
    await db.counters.update_one({"_id": "order_number"}, {"$setOnInsert": {"seq": 1000}}, upsert=True)
    await db.files.create_index("id", unique=True)
    try: await asyncio.to_thread(init_storage); logging.info("Object storage ready")
    except Exception as e: logging.error("Object storage init failed: %s", e)
    asyncio.create_task(migrate_local_uploads())
    email, password = os.environ["ADMIN_EMAIL"].lower(), os.environ["ADMIN_PASSWORD"]
    user = await db.users.find_one({"email": email})
    doc = {"id": str(uuid.uuid4()), "email": email, "password_hash": hash_password(password), "role": "admin", "created_at": now()}
    if not user: await db.users.insert_one(doc)
    elif not verify_password(password, user["password_hash"]): await db.users.update_one({"email": email}, {"$set": {"password_hash": doc["password_hash"]}})
    if await db.categories.count_documents({}) == 0:
        await db.categories.insert_many([{"id": str(uuid.uuid4()), "name": name, "position": i, "created_at": now()} for i, name in enumerate(["Coffee", "Cold Coffee", "Thickshakes", "Mocktails", "Snacks", "Desserts", "Food", "Specials"])])

app.include_router(api)
app.mount("/api/uploads", StaticFiles(directory=UPLOADS), name="api_uploads")
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
origins = [os.environ.get("FRONTEND_URL", "https://story-cafe-admin.preview.emergentagent.com"), "https://story-cafe-admin.preview.emergentagent.com", "http://localhost:3000"]
app.add_middleware(CORSMiddleware, allow_origins=list(set(origins)), allow_origin_regex=r"https://.*\.preview\.emergentagent\.com", allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def credentialed_preflight(request: Request, call_next):
    origin = request.headers.get("origin", "")
    if request.method == "OPTIONS" and (origin in origins or origin.endswith(".preview.emergentagent.com")):
        return Response(status_code=200, headers={"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true", "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS", "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers", "Content-Type, Authorization"), "Vary": "Origin"})
    response = await call_next(request)
    if origin in origins or origin.endswith(".preview.emergentagent.com"):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response

@app.on_event("shutdown")
async def shutdown(): client.close()