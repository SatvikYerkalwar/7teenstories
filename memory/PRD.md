# 7teen Stories Cafe — Product Record

## Original problem statement
Build a premium, aesthetic, fully responsive café website for “7teen Stories Cafe” with a storybook-inspired public experience and secure admin panel for menu management. Use the uploaded logo and café photographs, keep the menu database-driven, support secure owner authentication, product/category CRUD, image uploads, featured products, availability controls, gallery lightbox, and editable visit placeholders.

## Architecture decisions
- React frontend with a storybook/editorial visual system and responsive public/admin routes.
- FastAPI backend with MongoDB collections for users, categories, products, and login attempts.
- JWT access session in an httpOnly secure cookie, bcrypt password hashing, admin-only mutations.
- Uploaded product images are validated and stored in backend uploads, served from `/uploads`.
- Public menu reads only available database products; initial menu intentionally starts empty.

## User personas
- Café visitor: explores the café story, gallery, menu, and visit information on desktop or mobile.
- Café owner: manages products and categories quickly from a phone-friendly `/admin` dashboard.

## Core requirements (static)
- Storybook-inspired public home with Home, Our Story, Menu, Gallery, and Visit Us sections.
- Dynamic MongoDB menu with product image, name, category, description, price, availability, and featured state.
- Secure admin login and protected product/category/image operations.
- Uploaded brand assets used throughout the experience.
- Mobile responsive navigation, admin table, forms, gallery lightbox, and smooth visual interactions.

## Implemented (2026-09-23)
- Replaced starter splash with complete public 7teen Stories Cafe website.
- Added uploaded logo and four uploaded café photo placements for hero, story, gallery, and visit sections.
- Added public empty-menu state and database-backed menu rendering.
- Added seeded café categories, owner authentication, admin dashboard stats, product CRUD, image upload validation, availability toggle, featured flag, search, delete confirmation, and category management.
- Added secure bcrypt/JWT session, failed-login lockout after five attempts, credentialed CORS handling, and admin credential documentation.
- Verified frontend production build, API health, public rendering, and core end-to-end flows.

## Backlog
- P0: Add real address, Instagram URL, and Google Maps link when the owner supplies them.
- P1: Add drag-and-drop category ordering and a settings page for editable café details.
- P2: Add richer product image compression and menu export/print view.

## Next tasks
1. Owner adds the live menu through `/admin`.
2. Owner replaces the three visit placeholders with real location/social information.
3. Consider a dedicated settings view for café details and gallery curation.