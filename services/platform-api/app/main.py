import logging
from contextlib import asynccontextmanager

import aiomysql
import redis.asyncio as redis_ai
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.base import BaseHTTPMiddleware

from starlette.datastructures import MutableHeaders

from app.common import decode_bearer_token, path_is_public
from app.config import settings
from app.kafka_bus import ensure_producer_started, start_background_consumers

from app.routers import analytics, ai_proxy, applications, connections, jobs, members, messaging, posts, recruiters

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("platform-api")


def mongo_uri() -> str:
    return (
        f"mongodb://{settings.mongo_user}:{settings.mongo_password}"
        f"@{settings.mongo_host}:{settings.mongo_port}/{settings.mongo_database}?authSource=admin"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_producer_started()
    start_background_consumers()

    app.state.mysql_pool = await aiomysql.create_pool(
        host=settings.mysql_host,
        port=int(settings.mysql_port),
        user=settings.mysql_user,
        password=settings.mysql_password,
        db=settings.mysql_database,
        autocommit=True,
        minsize=1,
        maxsize=40,
        cursorclass=aiomysql.DictCursor,
        charset="utf8mb4",
    )

    app.state.redis_cache = redis_ai.Redis(
        host=settings.redis_host,
        port=int(settings.redis_port),
        decode_responses=True,
    )

    motor = AsyncIOMotorClient(mongo_uri())
    app.state.motor_client = motor
    app.state.mongo_db = motor[settings.mongo_database]

    log.info("platform-api startup complete")
    yield

    app.state.mysql_pool.close()
    await app.state.mysql_pool.wait_closed()
    await app.state.redis_cache.aclose()
    motor.close()


class AuthStripMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        scope = request.scope
        original = scope["path"]

        request.scope["_original_path"] = original

        if not path_is_public(original):
            auth_header = request.headers.get("authorization")
            if not auth_header:
                auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return JSONResponse({"error": "Access token required"}, status_code=401)
            claims = decode_bearer_token(auth_header)
            if claims is None:
                return JSONResponse({"error": "Invalid or expired token"}, status_code=403)
            h = MutableHeaders(scope=scope)
            h["x-user-id"] = str(claims.get("id", ""))
            h["x-user-role"] = str(claims.get("role", ""))

        if original.startswith("/api/"):
            suffix = original[4:]
            scope["path"] = suffix if suffix else "/"
        elif original == "/api":
            scope["path"] = "/"

        if scope["path"] != original:
            scope["raw_path"] = scope["path"].encode("utf-8")

        return await call_next(request)


app = FastAPI(title="LinkedIn DS Platform API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthStripMiddleware)

app.include_router(members.router)
app.include_router(recruiters.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(connections.router)
app.include_router(messaging.threads_router)
app.include_router(messaging.messages_router)
app.include_router(analytics.events_router)
app.include_router(analytics.analytics_router)
app.include_router(posts.router)
app.include_router(ai_proxy.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "platform-api"}


@app.post("/auth/login")
async def auth_login_stub():
    return JSONResponse(
        {"error": "Deprecated path — use POST /members/login or /recruiters/login"},
        status_code=410,
    )
