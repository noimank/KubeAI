import uuid

from app.models.user import User


def test_user_table_name():
    assert User.__tablename__ == "users"


def test_user_model_fields():
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
        is_active=True,
        failed_login_attempts=0,
        locked_until=None,
    )
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.hashed_password == "hashed"
    assert user.is_active is True
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_user_default_values():
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
    )
    assert user.is_active is True
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_user_inherits_mixins():
    assert hasattr(User, "created_at")
    assert hasattr(User, "updated_at")
    assert hasattr(User, "deleted_at")


def test_user_id_is_uuid():
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
    )
    assert isinstance(user.id, uuid.UUID)
