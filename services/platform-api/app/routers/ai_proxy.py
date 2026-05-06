import httpx
from fastapi import APIRouter, Request, Response

from app.config import settings

router = APIRouter(tags=["ai-proxy"])

_methods = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


async def _forward(request: Request, tail: str) -> Response:
    base = settings.ai_agent_url.rstrip("/")
    qp = request.url.query
    q = f"?{qp}" if qp else ""
    url = f"{base}/{tail}{q}"

    hdrs = [(k.decode(), v.decode()) for k, v in request.scope["headers"] if k.lower() != b"host"]

    async with httpx.AsyncClient(timeout=120.0) as client:
        body = await request.body()
        r = await client.request(
            request.method,
            url,
            headers=dict(hdrs),
            content=body if body else None,
        )
    excluded = {"content-encoding", "transfer-encoding", "connection"}
    out_headers = {k: v for k, v in r.headers.items() if k.lower() not in excluded}
    return Response(content=r.content, status_code=r.status_code, headers=out_headers)


@router.api_route("/agents/{path:path}", methods=_methods)
async def proxy_agents(path: str, request: Request) -> Response:
    return await _forward(request, f"agents/{path}")


@router.api_route("/skills/{path:path}", methods=_methods)
async def proxy_skills(path: str, request: Request) -> Response:
    return await _forward(request, f"skills/{path}")
