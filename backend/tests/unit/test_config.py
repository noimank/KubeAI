from app.core.config import Settings


def test_settings_defaults():
    s = Settings()
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
