import json
from datetime import datetime, timedelta

import bcrypt
import jwt
import aiomysql
import pymysql.err
from fastapi import APIRouter, HTTPException

from app.common import jsonable_row, uuid4_str
from app.config import settings
from app.deps import MysqlPoolDep

router = APIRouter(prefix="/recruiters", tags=["recruiters"])


def _normalize_hiring_highlights(val):
    if val is None:
        return None
    if isinstance(val, (list, tuple)):
        return json.dumps(val)
    if isinstance(val, str):
        return val
    return json.dumps(val)


@router.post("/create")
async def create_recruiter(body: dict, pool: MysqlPoolDep):
    req = ["first_name", "last_name", "email", "password", "company_name"]
    for k in req:
        if not body.get(k):
            raise HTTPException(status_code=400, detail="first_name, last_name, email, password, company_name required")
    rid = uuid4_str()
    cid = body.get("company_id") or uuid4_str()
    phash = bcrypt.hashpw(body["password"].encode(), bcrypt.gensalt(rounds=10)).decode()
    hl = _normalize_hiring_highlights(body.get("hiring_highlights"))
    try:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """INSERT INTO recruiters
               (recruiter_id, company_id, first_name, last_name, email, password_hash, phone,
                company_name, company_industry, company_size, role,
                headline, about, location, specialties, hiring_highlights, profile_photo_url)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [
                        rid,
                        cid,
                        body["first_name"],
                        body["last_name"],
                        body["email"],
                        phash,
                        body.get("phone"),
                        body["company_name"],
                        body.get("company_industry"),
                        body.get("company_size"),
                        body.get("role") or "recruiter",
                        body.get("headline"),
                        body.get("about"),
                        body.get("location"),
                        body.get("specialties"),
                        hl,
                        body.get("profile_photo_url"),
                    ],
                )
    except pymysql.err.IntegrityError as e:
        if e.args[0] == 1062:
            raise HTTPException(status_code=409, detail="Email already exists")
        raise

    return {"recruiter_id": rid, "company_id": cid}


@router.post("/login")
async def login(body: dict, pool: MysqlPoolDep):
    email, pw = body.get("email"), body.get("password")
    if not email or not pw:
        raise HTTPException(status_code=400, detail="email and password are required")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM recruiters WHERE email = %s AND (is_deleted IS NULL OR is_deleted = 0)",
                [email],
            )
            rows = await cur.fetchall()
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    r = rows[0]
    if not r.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not bcrypt.checkpw(pw.encode(), r["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    expire = datetime.utcnow() + timedelta(days=7)
    tok = jwt.encode(
        {"id": r["recruiter_id"], "role": "recruiter", "exp": expire},
        settings.jwt_secret,
        algorithm="HS256",
    )
    safe = {k: v for k, v in r.items() if k != "password_hash"}
    safe["token"] = tok if isinstance(tok, str) else (tok.decode() if isinstance(tok, bytes) else str(tok))
    return jsonable_row(safe)


@router.post("/search")
async def search(body: dict, pool: MysqlPoolDep):
    raw = (body.get("keyword") or "").strip()
    page = max(int(body.get("page") or 1), 1)
    limit = min(max(int(body.get("limit") or 20), 1), 50)
    offset = (page - 1) * limit
    if not raw:
        return {"results": [], "page": page, "limit": limit}
    kw = f"%{raw}%"
    q = """SELECT recruiter_id, first_name, last_name, email, company_name, company_industry
       FROM recruiters
       WHERE (is_deleted IS NULL OR is_deleted = 0)
         AND (email LIKE %s OR first_name LIKE %s OR last_name LIKE %s OR company_name LIKE %s OR company_industry LIKE %s)
       ORDER BY updated_at DESC
       LIMIT %s OFFSET %s"""
    params = [kw, kw, kw, kw, kw, limit, offset]
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(q, params)
            rows = await cur.fetchall()

    return {"results": jsonable_row(rows), "page": page, "limit": limit}


@router.post("/get")
async def get(body: dict, pool: MysqlPoolDep):
    rid = body.get("recruiter_id")
    if not rid:
        raise HTTPException(status_code=400, detail="recruiter_id required")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT * FROM recruiters WHERE recruiter_id = %s
               AND (is_deleted IS NULL OR is_deleted = 0)""",
                [rid],
            )
            rows = await cur.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Recruiter not found")
    row = dict(rows[0])
    row.pop("password_hash", None)
    return jsonable_row(row)


@router.post("/update")
async def update(body: dict, pool: MysqlPoolDep):
    rid = body.get("recruiter_id")
    if not rid:
        raise HTTPException(status_code=400, detail="recruiter_id required")
    allowed = {
        "first_name",
        "last_name",
        "phone",
        "company_name",
        "company_industry",
        "company_size",
        "role",
        "headline",
        "about",
        "location",
        "specialties",
        "hiring_highlights",
        "profile_photo_url",
    }
    updates = []
    for k in allowed:
        if k not in body:
            continue
        val = body[k]
        if k == "hiring_highlights":
            val = _normalize_hiring_highlights(val)
        elif k == "profile_photo_url" and isinstance(val, str) and val.strip() == "":
            val = None
        updates.append((k, val))
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT recruiter_id FROM recruiters WHERE recruiter_id=%s", [rid])
            if not await cur.fetchall():
                raise HTTPException(status_code=404, detail="Recruiter not found")
            clauses = ",".join(f"{k}=%s" for k, _ in updates)
            await cur.execute(
                f"UPDATE recruiters SET {clauses} WHERE recruiter_id=%s",
                [v for _, v in updates] + [rid],
            )

    return {"recruiter_id": rid, "updated_fields": [k for k, _ in updates]}


@router.post("/delete")
async def delete(body: dict, pool: MysqlPoolDep):
    rid = body.get("recruiter_id")
    if not rid:
        raise HTTPException(status_code=400, detail="recruiter_id required")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT recruiter_id FROM recruiters WHERE recruiter_id=%s", [rid])
            if not await cur.fetchall():
                raise HTTPException(status_code=404, detail="Recruiter not found")
            await cur.execute("UPDATE recruiters SET is_deleted = 1 WHERE recruiter_id=%s", [rid])
    return {"recruiter_id": rid, "deleted": True}
