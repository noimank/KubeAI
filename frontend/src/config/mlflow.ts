/**
 * MLflow UI 直链配置.
 *
 * - 本地开发默认走 NodePort 30500 (infra/helm/kubeai/values-dev.yaml)
 * - 生产默认走 APISIX /mlflow 反向代理 (infra/k8s/ingress/ingress.yaml)
 * - 可通过环境变量 VITE_MLFLOW_UI_BASE_URL 覆盖
 */
export const MLFLOW_UI_BASE_URL: string =
  (import.meta.env.VITE_MLFLOW_UI_BASE_URL as string | undefined) ??
  (import.meta.env.DEV ? 'http://localhost:30500' : '/mlflow')
