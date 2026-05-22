{{- define "kubeai.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "kubeai.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "kubeai.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "kubeai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "kubeai.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kubeai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "kubeai.backend.fullname" -}}
{{- printf "%s-backend" (include "kubeai.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "kubeai.frontend.fullname" -}}
{{- printf "%s-frontend" (include "kubeai.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "kubeai.databaseUrl" -}}
{{- if .Values.backend.secrets.DATABASE_URL }}
{{- .Values.backend.secrets.DATABASE_URL }}
{{- else if .Values.postgresql.enabled }}
{{- printf "postgresql+asyncpg://%s:%s@%s-postgresql.%s.svc.cluster.local:5432/%s" "postgres" .Values.postgresql.auth.postgresPassword (include "kubeai.fullname" .) .Release.Namespace .Values.postgresql.auth.database }}
{{- end }}
{{- end }}

{{- define "kubeai.redisUrl" -}}
{{- if .Values.backend.secrets.REDIS_URL }}
{{- .Values.backend.secrets.REDIS_URL }}
{{- else if .Values.redis.enabled }}
{{- printf "redis://%s-redis.%s.svc.cluster.local:6379/0" (include "kubeai.fullname" .) .Release.Namespace }}
{{- end }}
{{- end }}

{{- define "kubeai.minioEndpoint" -}}
{{- if .Values.backend.secrets.MINIO_ENDPOINT }}
{{- .Values.backend.secrets.MINIO_ENDPOINT }}
{{- else if .Values.minio.enabled }}
{{- printf "%s-minio.%s.svc.cluster.local:9000" (include "kubeai.fullname" .) .Release.Namespace }}
{{- end }}
{{- end }}

{{- define "kubeai.prometheusUrl" -}}
{{- if .Values.backend.secrets.PROMETHEUS_URL }}
{{- .Values.backend.secrets.PROMETHEUS_URL }}
{{- else if .Values.prometheus.enabled }}
{{- printf "http://%s-kube-prometheus-prometheus.%s.svc.cluster.local:9090" (include "kubeai.fullname" .) .Release.Namespace }}
{{- end }}
{{- end }}

{{- define "kubeai.mlflowTrackingUri" -}}
{{- if .Values.backend.secrets.MLFLOW_TRACKING_URI }}
{{- .Values.backend.secrets.MLFLOW_TRACKING_URI }}
{{- else if .Values.mlflow.enabled }}
{{- printf "http://%s-mlflow.%s.svc.cluster.local:5000" (include "kubeai.fullname" .) .Release.Namespace }}
{{- end }}
{{- end }}

{{- define "kubeai.mlflowBackendStoreUri" -}}
{{- printf "postgresql://postgres:%s@%s-postgresql.%s.svc.cluster.local:5432/mlflow" .Values.postgresql.auth.postgresPassword (include "kubeai.fullname" .) .Release.Namespace }}
{{- end }}

{{- define "kubeai.mlflowArtifactRoot" -}}
{{- if .Values.mlflow.persistence.enabled }}
{{- printf "/mlflow/artifacts" }}
{{- else }}
{{- printf "./mlflow/artifacts" }}
{{- end }}
{{- end }}

{{- define "kubeai.labelStudioUrl" -}}
{{- if .Values.backend.secrets.LABEL_STUDIO_URL }}
{{- .Values.backend.secrets.LABEL_STUDIO_URL }}
{{- else if .Values.labelstudio.enabled }}
{{- printf "http://%s-labelstudio.%s.svc.cluster.local:8080" (include "kubeai.fullname" .) .Release.Namespace }}
{{- end }}
{{- end }}

{{- define "kubeai.jupyterhubApiUrl" -}}
{{- if .Values.backend.secrets.JUPYTERHUB_API_URL }}
{{- .Values.backend.secrets.JUPYTERHUB_API_URL }}
{{- else if .Values.jupyterhub.enabled }}
{{- printf "http://%s-hub.%s.svc.cluster.local:8081/hub/api" (include "kubeai.fullname" .) .Release.Namespace }}
{{- end }}
{{- end }}

{{- define "kubeai.jupyterhubBaseUrl" -}}
{{- if .Values.backend.secrets.JUPYTERHUB_BASE_URL }}
{{- .Values.backend.secrets.JUPYTERHUB_BASE_URL }}
{{- else if and .Values.jupyterhub.enabled .Values.jupyterhub.ingress.enabled }}
{{- printf "https://%s" (index .Values.jupyterhub.ingress.hosts 0) }}
{{- else if .Values.jupyterhub.enabled }}
{{- printf "http://%s-proxy.%s.svc.cluster.local:80" (include "kubeai.fullname" .) .Release.Namespace }}
{{- end }}
{{- end }}

{{- define "kubeai.jupyterhubHubServiceAccount" -}}
{{- if .Values.backend.secrets.JUPYTERHUB_HUB_SERVICE_ACCOUNT }}
{{- .Values.backend.secrets.JUPYTERHUB_HUB_SERVICE_ACCOUNT }}
{{- else if and .Values.jupyterhub.hub.serviceAccount .Values.jupyterhub.hub.serviceAccount.name }}
{{- .Values.jupyterhub.hub.serviceAccount.name }}
{{- else if and (kindIs "string" .Values.jupyterhub.fullnameOverride) .Values.jupyterhub.fullnameOverride }}
{{- printf "%s-hub" .Values.jupyterhub.fullnameOverride }}
{{- else }}
{{- "hub" }}
{{- end }}
{{- end }}
