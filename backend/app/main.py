from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.endpoints.router import api_router
from app.core.config import settings
from app.core.events import on_shutdown, on_startup
from app.core.exceptions import AppException
from app.middleware.error_handler import app_exception_handler, unhandled_exception_handler
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.tenant import TenantMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await on_startup()
    yield
    await on_shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(TenantMiddleware)

app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router, prefix=settings.API_PREFIX)
