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
    TRANSFER_QUOTA = "transfer_quota"
    UPLOAD = "upload"
    BUILD = "build"
    REBUILD = "rebuild"
    CLEANUP_JOB = "cleanup_job"
    DOWNLOAD = "download"


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
    ALGORITHM = "algorithm"


class BuildStatus(enum.StrEnum):
    PENDING = "pending"
    BUILDING = "building"
    PUSHING = "pushing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ImageCategory(enum.StrEnum):
    TRAINING = "training"
    INFERENCE = "inference"
    OTHER = "other"


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


class AnnotationTaskStatus(enum.StrEnum):
    UNASSIGNED = "unassigned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class DevEnvironmentStatus(enum.StrEnum):
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class EnvironmentType(enum.StrEnum):
    JUPYTER = "jupyter"
    VSCODE = "vscode"
    RSTUDIO = "rstudio"


class NotificationType(enum.StrEnum):
    TRAINING_JOB = "training_job"
    QUOTA_ALERT = "quota_alert"
    ANNOTATION_TASK = "annotation_task"
    INFERENCE_SERVICE = "inference_service"


class NotificationPriority(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AlgorithmSourceType(enum.StrEnum):
    UPLOAD = "upload"
    GIT = "git"


class AlgorithmStatus(enum.StrEnum):
    AVAILABLE = "available"
    ARCHIVED = "archived"
    ERROR = "error"
