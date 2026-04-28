import enum


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    MLOPS = "mlops"
    ENGINEER = "engineer"
    ANNOTATOR = "annotator"
