import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import jwt

from fastapi import Request

from app.config import settings


def uuid4_str() -> str:
    return str(uuid.uuid4())


def json_dump(obj: Any) -> str:
    def default(o: Any) -> Any:
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, bytes):
            return o.decode(errors="replace")
        raise TypeError

    return json.dumps(obj, default=default)


def jsonable_row(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: jsonable_row(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [jsonable_row(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode(errors="replace")
    return obj


def trace_id(body: Optional[dict], x_trace_id: Optional[str]) -> str:
    if body is not None and body.get("trace_id"):
        return str(body["trace_id"])
    if x_trace_id:
        return x_trace_id
    return uuid4_str()


def make_event_idempotency_key(
    body: Optional[dict],
    header_key: Optional[str],
    event_type: str,
    entity_id: str,
) -> str:
    if body is not None and body.get("idempotency_key"):
        b = str(body["idempotency_key"])
    elif header_key:
        b = header_key
    else:
        b = uuid4_str()
    return f"{b}:{event_type}:{entity_id}"


def bearer_user(request: Request) -> tuple[Optional[str], Optional[str]]:
    uid = request.headers.get("x-user-id")
    role = request.headers.get("x-user-role")
    return uid, role


def require_role_member(request: Request, body_member_id: Optional[str] = None) -> Optional[str]:
    uid, role = bearer_user(request)
    if role == "member" and uid:
        return uid
    if body_member_id:
        return body_member_id
    return None


PUBLIC_PATH_PREFIXES = [
    "/api/members/create",
    "/api/members/login",
    "/api/members/get",
    "/api/members/update",
    "/api/members/delete",
    "/api/members/skills",
    "/api/members/search",
    "/api/recruiters/create",
    "/api/recruiters/login",
    "/api/recruiters/get",
    "/api/recruiters/search",
    "/api/recruiters/update",
    "/api/recruiters/delete",
    "/api/auth/login",
    "/api/jobs/search",
    "/api/jobs/get",
    "/api/jobs/byRecruiter",
    "/api/jobs/save",
    "/api/jobs/unsave",
    "/api/jobs/saved",
    "/api/applications/byMember",
    "/api/applications/byJob",
    "/api/applications/submit",
    "/api/analytics",
    "/api/events",
    "/api/threads",
    "/api/messages",
    "/api/connections",
    "/api/agents",
    "/api/skills",
    "/api/posts",
]


def path_is_public(path: str) -> bool:
    if path.rstrip("/") in ("/health", ""):
        return True
    # FastAPI OpenAPI / Swagger — no JWT in browser
    if path == "/openapi.json" or path.startswith("/docs") or path.startswith("/redoc"):
        return True
    candidates = []
    for p in PUBLIC_PATH_PREFIXES:
        candidates.append(p)
        if p.startswith("/api"):
            rest = "/" + p[4:].lstrip("/")
            candidates.append(rest)
    return any(path.startswith(p) for p in candidates)


def decode_bearer_token(auth_header: Optional[str]) -> Optional[dict]:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except Exception:
        return None

