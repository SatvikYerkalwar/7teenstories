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

## API endpoints
- `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`
- `GET /api/categories`, `GET /api/products` (public, only available)
- `GET/POST/PUT/DELETE /api/admin/categories(/{id})`, `POST /api/admin/categories/reorder`
- `GET/POST/PUT/DELETE /api/admin/products(/{id})`, `PATCH /api/admin/products/{id}/availability`
- `POST /api/admin/upload`

## Backlog
- **P1** — Analytics widget (top-viewed products) in admin.
- **P2** — Bulk product import via CSV.
- **P2** — Public menu section anchors matching category order.
- **P2** — Instagram feed live embed once handle is provided.
- **P2** — Real address / Google Maps once owner shares final location.
