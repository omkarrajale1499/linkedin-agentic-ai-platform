from typing import Annotated

import aiomysql
import redis.asyncio as redis_ai
from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase


def pool_dep(req: Request) -> aiomysql.Pool:
    return req.app.state.mysql_pool


def mongo_dep(req: Request) -> AsyncIOMotorDatabase:
    return req.app.state.mongo_db


def redis_dep(req: Request) -> redis_ai.Redis:
    return req.app.state.redis_cache


MysqlPoolDep = Annotated[aiomysql.Pool, Depends(pool_dep)]
MongoDep = Annotated[AsyncIOMotorDatabase, Depends(mongo_dep)]
RedisDep = Annotated[redis_ai.Redis, Depends(redis_dep)]
