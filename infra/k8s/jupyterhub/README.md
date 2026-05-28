# JupyterHub - 交互式开发环境

KubeAI 使用 JupyterHub 管理用户 Notebook 开发环境，包含自定义 KubeAI Authenticator 和 Spawner Options。

## 部署

```bash
kubectl apply -f infra/k8s/jupyterhub/jupyterhub.yaml
```

> `jupyterhub.yaml` 由 `helm template` 从 jupyterhub-4.3.5 生成，包含 Hub、Proxy、image-puller、user-scheduler 及所有 RBAC/NetworkPolicy。
> 已内置 KubeAI 自定义配置: ForcedLoginAuthenticator + apply_user_options + NetworkPolicy 允许访问租户命名空间。

## 验证

```bash
kubectl get pods -n kubeai -l app.kubernetes.io/instance=jupyterhub
```

## 访问

| 环境 | 地址 |
|-----|------|
| Dev | `http://<node-ip>:30801` |

## 与 Backend 集成

`backend-config.yaml` 中配置:

ConfigMap:
```yaml
JUPYTERHUB_API_URL: "http://hub.kubeai.svc.cluster.local:8081/hub/api"
JUPYTERHUB_BASE_URL: "http://proxy.kubeai.svc.cluster.local:80"
JUPYTERHUB_HUB_SERVICE_ACCOUNT: "hub"
```

Secret:
```yaml
JUPYTERHUB_API_TOKEN: "kubeai-dev-jupyterhub-token"
```

## 自定义配置

如需修改 JupyterHub 配置 (Hub 资源、Proxy 副本数、单用户镜像等):
1. 创建 values 文件，参考 `infra/helm/kubeai/values.yaml` 中的 `jupyterhub` 段落
2. 重新渲染: `helm template jupyterhub jupyterhub/jupyterhub --namespace kubeai -f your-values.yaml > infra/k8s/jupyterhub/jupyterhub.yaml`
3. 重新部署: `kubectl apply -f infra/k8s/jupyterhub/jupyterhub.yaml`

## 卸载

```bash
kubectl delete -f infra/k8s/jupyterhub/jupyterhub.yaml
```
