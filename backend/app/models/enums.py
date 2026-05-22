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
    DEV_ENVIRONMENT_IMAGE = "dev_environment_image"
    TRAINING_JOB = "training_job"
    MODEL = "model"
    ANNOTATION_PROJECT = "annotation_project"


class BuildStatus(enum.StrEnum):
    PENDING = "pending"
    BUILDING = "building"
    PUSHING = "pushing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TrainingJobStatus(enum.StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    INITIALIZING = "initializing"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"


class ModelVersionStatus(enum.StrEnum):
    UPLOADING = "uploading"
    AVAILABLE = "available"
    FAILED = "failed"


class InferenceServiceStatus(enum.StrEnum):
    PENDING = "pending"
    DEPLOYING = "deploying"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"


class AnnotationType(enum.StrEnum):
    IMAGE_CLASSIFICATION = "image_classification"
    OBJECT_DETECTION = "object_detection"
    IMAGE_SEGMENTATION = "image_segmentation"
    TEXT_CLASSIFICATION = "text_classification"


class AnnotationProjectStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class AnnotationCallbackStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AnnotationTaskStatus(enum.StrEnum):
    UNASSIGNED = "unassigned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class DevEnvironmentStatus(enum.StrEnum):
    PENDING = "pending"
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class EnvironmentType(enum.StrEnum):
    JUPYTER = "jupyter"
    VSCODE = "vscode"
    RSTUDIO = "rstudio"
