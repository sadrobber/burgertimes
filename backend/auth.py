"""JWT + bcrypt admin auth helpers for Burger Times."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

JWT_ALGORITHM = "HS256"


def _secret() -> str:
    return os.environ.get("ADMIN_JWT_SECRET") or os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_admin_token(user_id: str, email: str, role: str = "admin") -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_admin_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])


async def require_admin(request: Request) -> Dict[str, Any]:
    """FastAPI dependency: verifies Bearer token and returns admin payload."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = header[7:].strip()
    try:
        payload = decode_admin_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return payload


async def require_kitchen(request: Request) -> Dict[str, Any]:
    """FastAPI dependency: verifies Bearer token, allows kitchen or admin role.

    Kitchen staff accounts are role="kitchen" and can only reach /api/kitchen/*
    routes (this dependency). Admin accounts (role="admin") can also reach the
    kitchen dashboard, but require_admin still rejects kitchen-role tokens —
    so a kitchen tablet token can never touch admin-only routes.
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = header[7:].strip()
    try:
        payload = decode_admin_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") not in ("admin", "kitchen"):
        raise HTTPException(status_code=403, detail="Kitchen or admin role required")
    return payload
