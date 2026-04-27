from app.core.exceptions import (
    AppException,
    BadRequestException,
    ConflictException,
    ExternalServiceException,
    ForbiddenException,
    NotFoundException,
    QuotaExceededException,
    UnauthorizedException,
)


def test_app_exception_base():
    exc = AppException()
    assert exc.status_code == 500
    assert exc.message == "服务内部错误"


def test_app_exception_custom():
    exc = AppException(message="自定义错误", status_code=999)
    assert exc.message == "自定义错误"
    assert exc.status_code == 999


def test_not_found():
    exc = NotFoundException()
    assert exc.status_code == 404
    assert "不存在" in exc.message


def test_bad_request():
    exc = BadRequestException()
    assert exc.status_code == 400


def test_unauthorized():
    exc = UnauthorizedException()
    assert exc.status_code == 401


def test_forbidden():
    exc = ForbiddenException()
    assert exc.status_code == 403


def test_conflict():
    exc = ConflictException()
    assert exc.status_code == 409


def test_quota_exceeded():
    exc = QuotaExceededException()
    assert exc.status_code == 422


def test_external_service():
    exc = ExternalServiceException()
    assert exc.status_code == 502


def test_inheritance_chain():
    assert issubclass(NotFoundException, AppException)
    assert issubclass(BadRequestException, AppException)
    assert issubclass(UnauthorizedException, AppException)
    assert issubclass(ForbiddenException, AppException)
    assert issubclass(ConflictException, AppException)
    assert issubclass(QuotaExceededException, AppException)
    assert issubclass(ExternalServiceException, AppException)


def test_custom_message():
    exc = NotFoundException(message="用户不存在")
    assert exc.message == "用户不存在"
