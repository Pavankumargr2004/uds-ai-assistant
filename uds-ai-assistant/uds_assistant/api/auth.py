"""Minimal auth: dev mode (trust X-User/X-Role headers) or token mode (Bearer token lookup)."""
from __future__ import annotations

import json
from dataclasses import dataclass

from fastapi import Header, HTTPException

from ..config import Settings, get_settings

ROLES = ("viewer", "engineer", "lead", "admin")
ROLE_RANK = {r: i for i, r in enumerate(ROLES)}


@dataclass
class Principal:
    user: str
    role: str

    def require(self, min_role: str) -> None:
        if ROLE_RANK.get(self.role, -1) < ROLE_RANK.get(min_role, 99):
            raise HTTPException(403, f"role '{self.role}' cannot perform an action that needs '{min_role}' or higher")


def get_current_user(
    x_user: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Principal:
    s: Settings = get_settings()
    if s.auth_mode == "token":
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "missing bearer token")
        token = authorization.split(" ", 1)[1].strip()
        users = json.loads(s.users_json or "{}")
        rec = users.get(token)
        if not rec:
            raise HTTPException(401, "invalid token")
        return Principal(user=rec.get("name", "unknown"), role=rec.get("role", "viewer"))
    # dev mode: trust headers, default to a named engineer so the API is usable without setup
    role = x_role if x_role in ROLES else "engineer"
    return Principal(user=x_user or "dev-user", role=role)
