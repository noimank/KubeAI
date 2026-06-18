# MLflow Tracking Server with PostgreSQL driver pre-installed
# Build: docker build -t hub.uimpcloud.com/kubeai/kubeai-mlflow:v3.12.0 -f infra/images/mlflow/Dockerfile .
#
# Why custom image instead of ghcr.io/mlflow/mlflow:
# - Official image does NOT include psycopg2-binary (optional [db] extra)
# - Avoiding runtime "pip install psycopg2-binary" eliminates:
#   1. Requirement for outbound internet from cluster nodes
#   2. Failure risk when PyPI is unreachable
#   3. ~5-15s startup delay per container restart
#   4. Unpinned dependency version drift

FROM ghcr.io/mlflow/mlflow:v3.12.0

RUN pip install --no-cache-dir psycopg2-binary
