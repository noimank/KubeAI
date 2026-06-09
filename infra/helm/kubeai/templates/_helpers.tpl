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
