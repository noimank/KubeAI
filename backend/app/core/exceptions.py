class AppException(Exception):
    def __init__(self, message: str = "服务内部错误", status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundException(AppException):
    def __init__(self, message: str = "资源不存在") -> None:
        super().__init__(message=message, status_code=404)


class BadRequestException(AppException):
    def __init__(self, message: str = "请求参数错误") -> None:
        super().__init__(message=message, status_code=400)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "未授权访问") -> None:
        super().__init__(message=message, status_code=401)


class ForbiddenException(AppException):
    def __init__(self, message: str = "权限不足") -> None:
        super().__init__(message=message, status_code=403)


class ConflictException(AppException):
    def __init__(self, message: str = "资源冲突") -> None:
        super().__init__(message=message, status_code=409)


class QuotaExceededException(AppException):
    def __init__(self, message: str = "配额已超出") -> None:
        super().__init__(message=message, status_code=422)


class ExternalServiceException(AppException):
    def __init__(self, message: str = "外部服务异常") -> None:
        super().__init__(message=message, status_code=502)
