# 7teen Stories Cafe — PRD

## Vision
A storybook-inspired premium café website with a secure owner admin panel to manage the menu without touching code.

## Personas
- **Café Owner** — manages products/categories from `/admin` on desktop or mobile.
- **Café Visitor** — reads the menu, browses gallery, finds the café.

## Core Requirements (static)
1. Public site: Home, Our Story, Menu (dynamic), Gallery (lightbox), Experience, Instagram, Find Us.
2. Admin panel (`/admin`): Secure auth, dashboard, Product CRUD w/ image upload, Category CRUD.
3. Dynamic menu — no hardcoded products.
4. Persistent MongoDB, HttpOnly-cookie JWT auth with rate-limit lockout.
5. Warm storybook design (cream/ivory, brown ink, rust accents).

## Implemented (2026-02)
- FastAPI backend, React frontend, MongoDB, JWT auth w/ bcrypt + lockout.
- Public: hero, story, dynamic menu grouped by category, masonry gallery + lightbox, experience, visit.
- Admin: login, stats dashboard, product table (search, filter, availability toggle, featured toggle), image upload (JPG/PNG/WebP ≤5MB).
- Category CRUD **+ inline rename + HTML5 drag-and-drop reordering + "Save order" persistence**.
- Duplicate-name protection on category rename (409).
- Delete-guard: cannot delete a category with products.
- Homepage "Stories We Serve" featured products section (auto-renders 3-5 featured items).

## Implemented (2026-06) — Online Ordering
- Menu cards: qty stepper + "Add to Cart"; unavailable products shown with "Unavailable" tag (public `/api/products` now returns all products with `available` flag).
- Cart: navbar cart button (desktop + mobile), slide-in drawer, localStorage persistence, qty edit/remove, subtotal/total, Proceed to Checkout.
- `/checkout`: name, 10-digit phone, Dine-in (table number) / Takeaway, order summary, Pay at Café. Backend recomputes totals from DB prices, merges duplicate items.
- `/order/:number/confirmed` confirmation page ("Your Story Has Begun ✨") and `/order/:number` tracking page (polls every 5s; Received→Accepted→Preparing→Ready→Completed; cancelled state).
- Admin: new **Dashboard** tab (order stats, live order cards, new-order alert banners w/ chime + browser Notification) and **Orders** tab (search, status filters, table, detail modal with status change). Sidebar badge shows count of new orders. Polling every 5s.
- DB: `orders` (id, order_number ST-####, customer_name, customer_phone, order_type, table_number, subtotal, total, status, payment_method=pay_at_cafe, payment_status=pending, created_at, updated_at), `order_items` (id, order_id, product_id, product_name_snapshot, price_snapshot, product_image_snapshot, quantity, subtotal), `counters` (sequential order numbers from 1001).
- Fix: uploaded images now served at `/api/uploads/...` (ingress only proxies `/api`); frontend rewrites legacy `/uploads/` paths.
- Frontend code for ordering lives in `/app/frontend/src/ordering/` (Cart.js, Checkout.js, OrderPages.js, AdminOrders.js, PageShell.js, shared.js, ordering.css).

## Ordering API
- `POST /api/orders` (public), `GET /api/orders/{order_number}` (public, masked phone)
- `GET /api/admin/orders?status=`, `GET /api/admin/orders/{id}`, `PATCH /api/admin/orders/{id}/status`

## API endpoints
- `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`
- `GET /api/categories`, `GET /api/products` (public, only available)
- `GET/POST/PUT/DELETE /api/admin/categories(/{id})`, `POST /api/admin/categories/reorder`
- `GET/POST/PUT/DELETE /api/admin/products(/{id})`, `PATCH /api/admin/products/{id}/availability`
- `POST /api/admin/upload`

## Implemented (2026-06) — Image storage fix + Ready SMS
- Root cause of broken product images: uploads stored at `/uploads/*` on local disk; ingress only proxies `/api/*`, so `<img>` received HTML. WebP rejected on loose MIME.
- Fix: `POST /api/admin/upload` validates by magic bytes (PNG/JPG/WebP ≤5MB), stores in **Emergent Object Storage** (`7teen-cafe/products/<uuid>.<ext>`), records in `files` collection, returns `/api/files/<name>`; `GET /api/files/{name}` streams with correct MIME. Legacy `/uploads/` images auto-migrated on startup. Modules: `backend/storage.py`, `backend/sms.py`.
- Admin ProductModal: instant local preview, "Uploading…" state, Save disabled while uploading, "Replace image"/"Remove image", clear error messages.
- Ready SMS: marking an order **Ready** fires a Twilio SMS in a background task (`notify_ready`); result stored on order (`ready_sms_status`, `ready_sms_detail`, `ready_sms_sent_at`) and shown in the order detail modal. `GET /api/admin/settings` → `{sms_configured}`. Env: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` (currently EMPTY → SMS gracefully skipped).

- Product/featured card images + admin upload preview locked to a fixed **4:3** ratio (`aspect-ratio:4/3; object-fit:cover; object-position:center; overflow:hidden`), cards flex so "Add to Cart" aligns across a row. Original files untouched.

## Backlog
- **P1** — Online payment (schema ready: `payment_method`/`payment_status` on orders).
- **P1** — Admin "Accepting orders" on/off switch (Settings tab).
- **P2** — Analytics widget (top-selling products) in admin.
- **P2** — Bulk product import via CSV.
- **P2** — Public menu section anchors matching category order.
- **P2** — Instagram feed live embed once handle is provided.
- **P2** — Real address / Google Maps once owner shares final location.
