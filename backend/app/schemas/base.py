from pydantic import BaseModel


class BaseResponse[T](BaseModel):
    success: bool = True
    message: str = "操作成功"
    data: T | None = None


class PageData[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class PageResponse[T](BaseResponse[list[T]]):
    data: PageData[T] | None = None


class PageRequest(BaseModel):
    page: int = 1
    page_size: int = 20
