from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.redis import get_redis
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.base import BaseResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[object, Depends(get_redis)]


@router.post("/register", response_model=BaseResponse[TokenResponse])
async def register(
    req: RegisterRequest,
    db: DbDep,
    redis: RedisDep,
) -> BaseResponse[TokenResponse]:
    service = AuthService(db, redis)
    token = await service.register(req)
    return BaseResponse(data=token, message="注册成功")


@router.post("/login", response_model=BaseResponse[TokenResponse])
async def login(
    req: LoginRequest,
    db: DbDep,
    redis: RedisDep,
) -> BaseResponse[TokenResponse]:
    service = AuthService(db, redis)
    token = await service.login(req)
    return BaseResponse(data=token, message="登录成功")
