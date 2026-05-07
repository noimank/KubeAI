import enum


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    MLOPS = "mlops"
    ENGINEER = "engineer"
    ANNOTATOR = "annotator"


class TenantStatus(enum.StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class InvitationStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AuditAction(enum.StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    REGISTER = "register"
    ENABLE = "enable"
    DISABLE = "disable"
    INVITE = "invite"
    ACCEPT_INVITE = "accept_invite"
    CANCEL_INVITE = "cancel_invite"
    UPDATE_ROLE = "update_role"
    ADD_MEMBER = "add_member"
    REMOVE_MEMBER = "remove_member"
    UPDATE_QUOTA = "update_quota"
    UPLOAD = "upload"
    BUILD = "build"
    REBUILD = "rebuild"


class ResourceType(enum.StrEnum):
    TENANT = "tenant"
    USER = "user"
    QUOTA = "quota"
    MEMBERSHIP = "membership"
    INVITATION = "invitation"
    CREDENTIAL = "credential"
    DATASET = "dataset"
    IMAGE = "image"


class BuildStatus(enum.StrEnum):
    PENDING = "pending"
    BUILDING = "building"
    PUSHING = "pushing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
