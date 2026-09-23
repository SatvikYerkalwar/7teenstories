from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / '.env')

import os, uuid, logging, secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
import bcrypt, jwt
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

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
class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=100); description: str = ""
    category_id: str; price: float = Field(gt=0); image_url: str = ""
    available: bool = True; featured: bool = False

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
async def public_products(): return await db.products.find({"available": True}, {"_id": 0}).sort("created_at", -1).to_list(500)

@api.get("/admin/categories")
async def admin_categories(_: dict = Depends(current_admin)): return await db.categories.find({}, {"_id": 0}).sort("position", 1).to_list(100)

@api.post("/admin/categories")
async def add_category(data: CategoryIn, _: dict = Depends(current_admin)):
    if await db.categories.find_one({"name": {"$regex": f"^{data.name.strip()}$", "$options": "i"}}): raise HTTPException(409, "Category already exists")
    doc = {"id": str(uuid.uuid4()), "name": data.name.strip(), "position": await db.categories.count_documents({}), "created_at": now()}
    await db.categories.insert_one(doc); return clean(doc)

@api.put("/admin/categories/{category_id}")
async def rename_category(category_id: str, data: CategoryIn, _: dict = Depends(current_admin)):
    result = await db.categories.update_one({"id": category_id}, {"$set": {"name": data.name.strip()}})
    if not result.matched_count: raise HTTPException(404, "Category not found")
    await db.products.update_many({"category_id": category_id}, {"$set": {"category_name": data.name.strip()}})
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
    if file.content_type not in ALLOWED_IMAGES: raise HTTPException(400, "Use JPG, PNG, or WebP images")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024: raise HTTPException(400, "Image must be under 5MB")
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[file.content_type]
    name = f"{uuid.uuid4()}{ext}"; (UPLOADS / name).write_bytes(content)
    return {"image_url": f"/uploads/{name}"}

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.categories.create_index("id", unique=True)
    await db.products.create_index("id", unique=True)
    await db.login_attempts.create_index("identifier", unique=True)
    email, password = os.environ["ADMIN_EMAIL"].lower(), os.environ["ADMIN_PASSWORD"]
    user = await db.users.find_one({"email": email})
    doc = {"id": str(uuid.uuid4()), "email": email, "password_hash": hash_password(password), "role": "admin", "created_at": now()}
    if not user: await db.users.insert_one(doc)
    elif not verify_password(password, user["password_hash"]): await db.users.update_one({"email": email}, {"$set": {"password_hash": doc["password_hash"]}})
    if await db.categories.count_documents({}) == 0:
        await db.categories.insert_many([{"id": str(uuid.uuid4()), "name": name, "position": i, "created_at": now()} for i, name in enumerate(["Coffee", "Cold Coffee", "Thickshakes", "Mocktails", "Snacks", "Desserts", "Food", "Specials"])])

app.include_router(api)
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