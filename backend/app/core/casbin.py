import os

import casbin
from casbin_sqlalchemy_adapter import Adapter


class CasbinEnforcer:
    _enforcer: casbin.Enforcer | None = None

    @classmethod
    def initialize(cls, database_url: str) -> None:
        sync_url = database_url.replace("+asyncpg", "")
        adapter = Adapter(sync_url)
        model_path = os.path.join(os.path.dirname(__file__), "rbac_model.conf")
        cls._enforcer = casbin.Enforcer(model_path, adapter)
        cls._seed_policies()
        cls._enforcer.load_policy()

    @classmethod
    def get_enforcer(cls) -> casbin.Enforcer:
        if cls._enforcer is None:
            raise RuntimeError("Casbin enforcer not initialized")
        return cls._enforcer

    @classmethod
    def enforce(cls, sub: str, obj: str, act: str) -> bool:
        return cls.get_enforcer().enforce(sub, obj, act)

    @classmethod
    def _seed_policies(cls) -> None:
        from app.core.permissions import SEED_POLICIES, SEED_ROLE_INHERITANCE

        enforcer = cls.get_enforcer()

        for policy in SEED_POLICIES:
            if not enforcer.has_policy(*policy):
                enforcer.add_policy(*policy)

        for role_def in SEED_ROLE_INHERITANCE:
            if not enforcer.has_grouping_policy(*role_def):
                enforcer.add_grouping_policy(*role_def)
