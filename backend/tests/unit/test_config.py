import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults():
    # Isolate from the local .env so we assert the *code* defaults, not whatever
    # the dev machine happens to override at runtime.
    s = Settings(_env_file=None, SECRET_KEY="a" * 64)
    assert s.APP_NAME == "KubeAI"
    assert s.APP_VERSION == "0.1.0"
    assert s.DEBUG is False
    assert s.API_PREFIX == "/api"
    assert "postgresql+asyncpg" in s.DATABASE_URL
    assert "redis" in s.REDIS_URL
    assert s.DB_POOL_SIZE == 20
    assert s.DB_MAX_OVERFLOW == 10
    assert s.REDIS_MAX_CONNECTIONS == 20
    assert s.ALLOW_USER_REGISTRATION is True


def test_settings_reject_default_secret_in_production():
    # 代码默认值与 k8s 清单占位符均为公开字符串, DEBUG=false 下使用即拒绝启动
    for insecure in ("change-me-in-production", "change-me-to-a-random-32-char-string"):
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            Settings(_env_file=None, SECRET_KEY=insecure)


def test_settings_allows_default_secret_in_debug():
    # DEBUG=true (本地开发) 放行默认密钥, 避免阻塞 uvicorn --reload 工作流
    s = Settings(_env_file=None, DEBUG=True, SECRET_KEY="change-me-in-production")
    assert s.SECRET_KEY == "change-me-in-production"
