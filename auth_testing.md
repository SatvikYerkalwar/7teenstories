# Authentication Testing Playbook

1. Log in using the credentials in `/app/memory/test_credentials.md` at `/admin`.
2. Confirm `/api/auth/me` returns the admin session and logout removes access.
3. Confirm unauthenticated product mutation requests return 401.
4. Confirm the admin can create, edit, toggle, and delete products and manage categories.