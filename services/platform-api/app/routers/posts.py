import aiomysql
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.common import jsonable_row, uuid4_str
from app.deps import MysqlPoolDep

router = APIRouter(prefix="/posts", tags=["posts"])

_posts_ready = False

BOOTSTRAP_POSTS = [
    ("career_update", "Excited to share that I started a new backend role this week.\nGrateful for everyone who helped with interview prep."),
    ("hiring", "We're hiring software engineers across backend and full-stack.\nIf you enjoy API design and distributed systems, let's connect."),
    ("project", "Built a real-time Kafka pipeline for application events.\nLatency dropped significantly after moving to event-driven processing."),
    ("learning", "Recently revisited system design basics.\nOne key lesson: start with clarity on constraints before architecture."),
    ("general", "Consistency beats intensity in career growth.\nSmall daily progress compounds quickly over a year."),
    ("job_update", "Looking for Summer 2026 internship opportunities.\nComfortable with React, Node.js, and SQL."),
]

BOOTSTRAP_COMMENTS = [
    "Congrats! Wishing you the best in this new chapter.",
    "Great share. This is super relevant right now.",
    "Thanks for posting this - really useful takeaway.",
    "Love this perspective. Appreciate the breakdown.",
]


async def ensure_posts(pool: aiomysql.Pool) -> None:
    global _posts_ready
    if _posts_ready:
        return
    stmts = [
        """CREATE TABLE IF NOT EXISTS posts (
      post_id        VARCHAR(36) PRIMARY KEY,
      author_id      VARCHAR(36) NOT NULL,
      content        TEXT NOT NULL,
      post_type      ENUM('general','job_update','project','hiring','learning','career_update') DEFAULT 'general',
      likes_count    INT DEFAULT 0,
      comments_count INT DEFAULT 0,
      created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      FOREIGN KEY (author_id) REFERENCES members(member_id) ON DELETE CASCADE,
      INDEX idx_author (author_id),
      INDEX idx_created_at (created_at),
      INDEX idx_post_type (post_type)
    )""",
        """CREATE TABLE IF NOT EXISTS post_likes (
      like_id      VARCHAR(36) PRIMARY KEY,
      post_id      VARCHAR(36) NOT NULL,
      member_id    VARCHAR(36) NOT NULL,
      created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY uq_post_member_like (post_id, member_id),
      FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
      FOREIGN KEY (member_id) REFERENCES members(member_id) ON DELETE CASCADE
    )""",
        """CREATE TABLE IF NOT EXISTS post_comments (
      comment_id    VARCHAR(36) PRIMARY KEY,
      post_id       VARCHAR(36) NOT NULL,
      author_id     VARCHAR(36) NOT NULL,
      content       TEXT NOT NULL,
      created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
      FOREIGN KEY (author_id) REFERENCES members(member_id) ON DELETE CASCADE
    )""",
        """CREATE TABLE IF NOT EXISTS saved_posts (
      save_id       VARCHAR(36) PRIMARY KEY,
      post_id       VARCHAR(36) NOT NULL,
      member_id     VARCHAR(36) NOT NULL,
      created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
      UNIQUE KEY uq_saved_post_member (post_id, member_id),
      FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
      FOREIGN KEY (member_id) REFERENCES members(member_id) ON DELETE CASCADE
    )""",
    ]
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            for sql in stmts:
                await cur.execute(sql)
    _posts_ready = True


async def refresh_counters(pool, pid: str) -> tuple[int, int]:
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT COUNT(*) AS total FROM post_likes WHERE post_id=%s", [pid])
            like_row = (await cur.fetchone())["total"]
            await cur.execute("SELECT COUNT(*) AS total FROM post_comments WHERE post_id=%s", [pid])
            comment_row = (await cur.fetchone())["total"]
            likes_c = like_row or 0
            com_c = comment_row or 0
            await cur.execute(
                "UPDATE posts SET likes_count=%s, comments_count=%s WHERE post_id=%s",
                [likes_c, com_c, pid],
            )
    return likes_c, com_c


def actor_member(request: Request, body_mid: str | None) -> str | None:
    uid = request.headers.get("x-user-id")
    role_hdr = request.headers.get("x-user-role")
    if role_hdr == "member" and uid:
        return uid
    return body_mid


async def member_exists(pool, mid: str) -> bool:
    if not mid:
        return False
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT member_id FROM members WHERE member_id=%s AND is_deleted=0", [mid])
            return bool(await cur.fetchone())


async def bootstrap_posts_if_needed(pool):
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT COUNT(*) AS total FROM posts")
            total = (await cur.fetchone())["total"]
            if total and total > 0:
                return
            await cur.execute(
                "SELECT member_id FROM members WHERE is_deleted=0 ORDER BY created_at ASC LIMIT 12"
            )
            authors = await cur.fetchall()
    if not authors:
        return
    seeded = []
    for i, pdata in enumerate(BOOTSTRAP_POSTS):
        author = authors[i % len(authors)]["member_id"]
        pid = uuid4_str()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO posts (post_id, author_id, content, post_type, likes_count, comments_count,
                    created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,DATE_SUB(NOW(), INTERVAL %s HOUR), DATE_SUB(NOW(), INTERVAL %s HOUR))""",
                    [pid, author, pdata[1], pdata[0], 0, 0, i + 1, i + 1],
                )
        seeded.append(pid)

    for i, pid in enumerate(seeded):
        for j in range(2):
            author = authors[(i + j + 1) % len(authors)]["member_id"]
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """INSERT INTO post_comments (comment_id, post_id, author_id, content,
                    created_at, updated_at)
                VALUES (%s,%s,%s,%s,DATE_SUB(NOW(), INTERVAL %s HOUR), DATE_SUB(NOW(), INTERVAL %s HOUR))""",
                        [
                            uuid4_str(),
                            pid,
                            author,
                            BOOTSTRAP_COMMENTS[(i + j) % len(BOOTSTRAP_COMMENTS)],
                            i + j + 1,
                            i + j + 1,
                        ],
                    )
        await refresh_counters(pool, pid)


async def build_post_dict(pool, post_id: str, actor_id: str | None) -> dict | None:
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT p.post_id, p.author_id, p.content, p.post_type, p.likes_count, p.comments_count,
                p.created_at, p.updated_at, m.first_name, m.last_name, m.headline, m.profile_photo_url
               FROM posts p JOIN members m ON m.member_id=p.author_id
               WHERE p.post_id=%s AND m.is_deleted=0 LIMIT 1""",
                [post_id],
            )
            prow = await cur.fetchone()
            if not prow:
                return None
            await cur.execute(
                """SELECT c.comment_id, c.post_id, c.author_id, c.content, c.created_at,
                cm.first_name, cm.last_name, cm.headline
               FROM post_comments c JOIN members cm ON cm.member_id=c.author_id WHERE c.post_id=%s ORDER BY c.created_at ASC""",
                [post_id],
            )
            crows = await cur.fetchall()

    liked = saved = False
    if actor_id:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT COUNT(*) AS total FROM post_likes WHERE post_id=%s AND member_id=%s",
                    [post_id, actor_id],
                )
                liked = ((await cur.fetchone())["total"] or 0) > 0
                await cur.execute(
                    "SELECT COUNT(*) AS total FROM saved_posts WHERE post_id=%s AND member_id=%s",
                    [post_id, actor_id],
                )
                saved = ((await cur.fetchone())["total"] or 0) > 0

    aid = prow["author_id"]
    comments = []
    for c in crows:
        comments.append(
            {
                "id": c["comment_id"],
                "postId": c["post_id"],
                "authorId": c["author_id"],
                "content": c["content"],
                "createdAt": c["created_at"],
                "author": {
                    "id": c["author_id"],
                    "name": f"{c['first_name']} {c['last_name']}".strip(),
                    "headline": c["headline"] or "LinkedIn Member",
                },
                "canDelete": bool(actor_id) and actor_id == c["author_id"],
            }
        )
    owner_can = bool(actor_id) and actor_id == aid
    for cm in comments:
        cm["canDelete"] = cm["canDelete"] or owner_can

    return {
        "id": prow["post_id"],
        "authorId": prow["author_id"],
        "content": prow["content"],
        "type": prow["post_type"],
        "likesCount": prow["likes_count"] or 0,
        "commentsCount": prow["comments_count"] or len(comments),
        "createdAt": prow["created_at"],
        "updatedAt": prow["updated_at"],
        "likedByCurrentUser": liked,
        "savedByCurrentUser": saved,
        "author": {
            "id": prow["author_id"],
            "name": f"{prow['first_name']} {prow['last_name']}".strip(),
            "headline": prow["headline"] or "LinkedIn Member",
            "profileImage": prow["profile_photo_url"],
        },
        "comments": comments,
    }


@router.get("")
async def feed(pool: MysqlPoolDep, request: Request, limit: int = Query(30)):
    lim = max(1, min(limit, 100))
    actor_id = actor_member(request, None)

    await ensure_posts(pool)
    await bootstrap_posts_if_needed(pool)

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                f"""SELECT p.post_id, p.author_id, p.content, p.post_type, p.likes_count, p.comments_count,
               p.created_at, p.updated_at, m.first_name, m.last_name, m.headline, m.profile_photo_url
               FROM posts p JOIN members m ON m.member_id=p.author_id WHERE m.is_deleted=0 ORDER BY p.created_at DESC LIMIT {lim}"""
            )
            rows = await cur.fetchall()

    results = []
    for r in rows:
        d = await build_post_dict(pool, r["post_id"], actor_id)
        if d:
            results.append(jsonable_row(d))

    return {"results": results}


@router.get("/saved")
async def saved_posts(pool: MysqlPoolDep, request: Request, limit: int = Query(50)):
    await ensure_posts(pool)
    mid = actor_member(request, None)
    lim = max(1, min(limit, 100))
    if not await member_exists(pool, mid or ""):
        raise HTTPException(status_code=401, detail="Member authentication required")

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                f"""SELECT p.post_id FROM saved_posts sp JOIN posts p ON p.post_id=sp.post_id
               WHERE sp.member_id=%s ORDER BY sp.created_at DESC LIMIT {lim}""",
                [mid],
            )
            srows = await cur.fetchall()

    posts_out = []
    for r in srows:
        pd = await build_post_dict(pool, r["post_id"], mid)
        if pd:
            posts_out.append(jsonable_row(pd))
    return {"results": posts_out}


@router.post("")
async def create_post(pool: MysqlPoolDep, request: Request, body: dict):
    mid = actor_member(request, body.get("member_id"))
    content = (body.get("content") or "").strip()
    typ = body.get("type") or "general"

    await ensure_posts(pool)

    if not await member_exists(pool, mid or ""):
        raise HTTPException(status_code=401, detail="Member authentication required")
    if not content:
        raise HTTPException(status_code=400, detail="Post content is required")

    pid = uuid4_str()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO posts (post_id, author_id, content, post_type, likes_count, comments_count)
           VALUES (%s,%s,%s,%s,%s,%s)""",
                [pid, mid, content, typ, 0, 0],
            )

    post = await build_post_dict(pool, pid, mid)
    return JSONResponse({"post": jsonable_row(post)}, status_code=201)


@router.post("/{post_id}/like")
async def like_post(pool: MysqlPoolDep, request: Request, post_id: str):
    await ensure_posts(pool)
    mid = actor_member(request, None)
    if not await member_exists(pool, mid or ""):
        raise HTTPException(status_code=401, detail="Member authentication required")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT IGNORE INTO post_likes (like_id, post_id, member_id) VALUES (%s,%s,%s)",
                [uuid4_str(), post_id, mid],
            )
    lk, cc = await refresh_counters(pool, post_id)
    return {"likedByCurrentUser": True, "likesCount": lk, "commentsCount": cc}


@router.delete("/{post_id}/like")
async def unlike_post(pool: MysqlPoolDep, request: Request, post_id: str):
    await ensure_posts(pool)
    mid = actor_member(request, None)
    if not await member_exists(pool, mid or ""):
        raise HTTPException(status_code=401, detail="Member authentication required")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM post_likes WHERE post_id=%s AND member_id=%s", [post_id, mid])
    lk, cc = await refresh_counters(pool, post_id)
    return {"likedByCurrentUser": False, "likesCount": lk, "commentsCount": cc}


@router.post("/{post_id}/save")
async def save_post(pool: MysqlPoolDep, request: Request, post_id: str):
    await ensure_posts(pool)
    mid = actor_member(request, None)
    if not await member_exists(pool, mid or ""):
        raise HTTPException(status_code=401, detail="Member authentication required")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT IGNORE INTO saved_posts (save_id, post_id, member_id) VALUES (%s,%s,%s)",
                [uuid4_str(), post_id, mid],
            )
    return {"savedByCurrentUser": True}


@router.delete("/{post_id}/save")
async def unsave_post(pool: MysqlPoolDep, request: Request, post_id: str):
    await ensure_posts(pool)
    mid = actor_member(request, None)
    if not await member_exists(pool, mid or ""):
        raise HTTPException(status_code=401, detail="Member authentication required")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM saved_posts WHERE post_id=%s AND member_id=%s", [post_id, mid])
    return {"savedByCurrentUser": False}


@router.post("/{post_id}/comments")
async def add_comment(pool: MysqlPoolDep, request: Request, post_id: str, body: dict):
    await ensure_posts(pool)
    mid = actor_member(request, None)
    text = (body.get("content") or "").strip()
    if not await member_exists(pool, mid or ""):
        raise HTTPException(status_code=401, detail="Member authentication required")
    if not text:
        raise HTTPException(status_code=400, detail="Comment content is required")
    cid = uuid4_str()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO post_comments (comment_id, post_id, author_id, content) VALUES (%s,%s,%s,%s)",
                [cid, post_id, mid, text],
            )
    await refresh_counters(pool, post_id)

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT c.comment_id, c.post_id, c.author_id, c.content, c.created_at, m.first_name, m.last_name, m.headline
               FROM post_comments c JOIN members m ON m.member_id=c.author_id WHERE c.comment_id=%s""",
                [cid],
            )
            row = await cur.fetchone()

    cm = {
        "id": row["comment_id"],
        "postId": row["post_id"],
        "authorId": row["author_id"],
        "content": row["content"],
        "createdAt": row["created_at"],
        "author": {
            "id": row["author_id"],
            "name": f"{row['first_name']} {row['last_name']}".strip(),
            "headline": row["headline"] or "LinkedIn Member",
        },
        "canDelete": True,
    }
    return JSONResponse({"comment": jsonable_row(cm)}, status_code=201)


@router.delete("/{post_id}/comments/{comment_id}")
async def delete_comment(pool: MysqlPoolDep, request: Request, post_id: str, comment_id: str):
    await ensure_posts(pool)
    mid = actor_member(request, None)
    if not await member_exists(pool, mid or ""):
        raise HTTPException(status_code=401, detail="Member authentication required")

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT c.comment_id, c.author_id, p.author_id AS post_owner_id
               FROM post_comments c JOIN posts p ON p.post_id=c.post_id
               WHERE c.comment_id=%s AND c.post_id=%s""",
                [comment_id, post_id],
            )
            r = await cur.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Comment not found")
    if r["author_id"] != mid and r["post_owner_id"] != mid:
        raise HTTPException(status_code=403, detail="Not allowed to delete this comment")

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM post_comments WHERE comment_id=%s", [comment_id])
    lk, cc = await refresh_counters(pool, post_id)

    return {"deleted": True, "likesCount": lk, "commentsCount": cc}
