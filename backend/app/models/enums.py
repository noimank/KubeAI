import enum


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    MLOPS = "mlops"
    ENGINEER = "engineer"
    ANNOTATOR = "annotator"


class TenantStatus(enum.StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
