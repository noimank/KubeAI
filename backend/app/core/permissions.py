import enum


class RESOURCE(enum.StrEnum):
    USERS = "users"
    TENANTS = "tenants"
    QUOTAS = "quotas"
    DATASETS = "datasets"
    ANNOTATIONS = "annotations"
    TRAINING_JOBS = "training_jobs"
    EXPERIMENTS = "experiments"
    MODELS = "models"
    INFERENCE_SERVICES = "inference_services"
    IMAGES = "images"
    DEV_ENVIRONMENTS = "dev_environments"
    DEV_ENVIRONMENT_IMAGES = "dev_environment_images"
    MONITORING = "monitoring"
    AUDIT_LOGS = "audit_logs"
    NOTIFICATIONS = "notifications"
    DASHBOARD = "dashboard"
    ALGORITHMS = "algorithms"
    ANNOTATION_TEMPLATES = "annotation_templates"
    DATA_EXPLORE = "data_explore"
    BUSINESS_CONFIGS = "business_configs"
    TUNING = "tuning"


class ACTION(enum.StrEnum):
    READ = "read"
    WRITE = "write"
    MANAGE = "manage"
    BUILD = "build"


# (sub, obj, act)
SEED_POLICIES: list[tuple[str, str, str]] = [
    # annotator
    ("annotator", "dashboard", "read"),
    ("annotator", "datasets", "read"),
    ("annotator", "annotations", "read"),
    ("annotator", "annotations", "write"),
    ("annotator", "annotation_templates", "read"),
    ("annotator", "notifications", "read"),
    ("annotator", "notifications", "write"),
    ("annotator", "business_configs", "read"),
    # engineer
    ("engineer", "dashboard", "read"),
    ("engineer", "datasets", "read"),
    ("engineer", "training_jobs", "read"),
    ("engineer", "training_jobs", "write"),
    ("engineer", "experiments", "read"),
    ("engineer", "experiments", "write"),
    ("engineer", "models", "read"),
    ("engineer", "images", "read"),
    ("engineer", "images", "build"),
    ("engineer", "dev_environments", "read"),
    ("engineer", "dev_environments", "write"),
    ("engineer", "dev_environment_images", "read"),
    ("engineer", "inference_services", "read"),
    ("engineer", "tenants", "read"),
    ("engineer", "algorithms", "read"),
    ("engineer", "algorithms", "write"),
    ("engineer", "annotation_templates", "read"),
    ("engineer", "annotation_templates", "write"),
    ("engineer", "business_configs", "read"),
    ("engineer", "business_configs", "write"),
    ("engineer", "tuning", "read"),
    ("engineer", "tuning", "write"),
    # mlops (inherits engineer + additional)
    ("mlops", "dashboard", "read"),
    ("mlops", "annotations", "manage"),
    ("mlops", "datasets", "write"),
    ("mlops", "training_jobs", "manage"),
    ("mlops", "models", "write"),
    ("mlops", "inference_services", "manage"),
    ("mlops", "images", "read"),
    ("mlops", "images", "build"),
    ("mlops", "dev_environments", "manage"),
    ("mlops", "dev_environment_images", "manage"),
    ("mlops", "monitoring", "read"),
    ("mlops", "audit_logs", "read"),
    ("mlops", "users", "read"),
    ("mlops", "experiments", "manage"),
    ("mlops", "algorithms", "manage"),
    ("mlops", "annotation_templates", "manage"),
    ("mlops", "business_configs", "manage"),
    ("mlops", "tuning", "manage"),
    # admin (inherits mlops + additional)
    ("admin", "dashboard", "read"),
    ("admin", "tenants", "manage"),
    ("admin", "users", "manage"),
    ("admin", "quotas", "manage"),
    ("admin", "monitoring", "manage"),
    ("admin", "audit_logs", "manage"),
    ("admin", "datasets", "manage"),
    ("admin", "annotations", "manage"),
    ("admin", "training_jobs", "manage"),
    ("admin", "models", "manage"),
    ("admin", "inference_services", "manage"),
    ("admin", "images", "manage"),
    ("admin", "dev_environments", "manage"),
    ("admin", "dev_environment_images", "manage"),
    ("admin", "experiments", "manage"),
    ("admin", "algorithms", "manage"),
    ("admin", "annotation_templates", "manage"),
    ("admin", "business_configs", "manage"),
    # data_explore
    ("annotator", "data_explore", "read"),
    ("engineer", "data_explore", "read"),
    ("engineer", "data_explore", "write"),
    ("mlops", "data_explore", "manage"),
    ("admin", "data_explore", "manage"),
]

# (parent_role, child_role)
SEED_ROLE_INHERITANCE: list[tuple[str, str]] = [
    ("engineer", "annotator"),
    ("mlops", "engineer"),
    ("admin", "mlops"),
]
