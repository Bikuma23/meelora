# P1.2 - Tenant-aware authentication

Implemented without changing company permissions or financial routes.

## Changes
- Added `backend/core/auth_context.py`.
- `get_current_user()` now loads the user's workspace when `workspace_id` exists.
- Migrated users that reference a missing workspace fail closed with HTTP 403.
- Legacy users without `workspace_id` can still authenticate temporarily (`tenant_migrated=false`).
- Inactive users are rejected with HTTP 403.
- `GET /api/auth/me` now returns `workspace_id`, safe public `workspace`, `status`, and `tenant_migrated` while preserving existing fields.
- Workspace details returned to the browser omit internal fields such as `primary_admin_user_id` and `created_by`.

## Validation
- Python compile check passed for modified backend files.
- Focused auth-context smoke tests passed.
- The repository's pytest configuration requires `pytest-xdist`, which is not installed in this execution environment, so the pytest suite could not be invoked here.

## Explicitly deferred to P1.3+
- No company access enforcement yet.
- No workspace scoping of `/users` yet.
- No role migration (`editor -> user`) yet.
- No changes to acct/qc9434 financial engines.
