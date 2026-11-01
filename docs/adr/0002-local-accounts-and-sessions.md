# ADR 0002 — Local accounts, roles and server-side sessions

- Status: accepted (2026-10-30)
- Context: the plan requires permissions and an audit trail with the identity of whoever made each change.
- Decision: local accounts with four roles (admin, archivist, reviewer, viewer). Passwords use stdlib
  scrypt (n=2^14, r=8, p=1, 16-byte salt). Sessions are random 256-bit tokens in an HttpOnly, SameSite=Lax
  cookie; the database stores only their SHA-256. Five failed logins lock an account for 15 minutes.
  The first admin is created through a one-time setup endpoint that refuses once any user exists.
  Mutating requests keep the existing Origin allow-list check (CSRF defence together with SameSite).
  Document events record the username; account events go to a separate append-only `security_events`.
- Consequences: no external identity provider is needed. Deactivating a user or changing their role or
  password revokes their sessions immediately. TLS and secure cookies are required before any network
  deployment (`SMARTARCHIVE_SECURE_COOKIES=true`).
