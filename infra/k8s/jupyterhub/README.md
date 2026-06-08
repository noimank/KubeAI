# JupyterHub - 交互式开发环境

KubeAI 使用 JupyterHub 管理用户 Notebook 开发环境，包含自定义 KubeAI Authenticator 和 Spawner Options。

## 文件清单

| 文件 | 作用 |
|---|---|
| `jupyterhub.yaml` | `helm template` 渲染产物,包含所有 JupyterHub 资源 (ServiceAccount, RBAC, ConfigMap, **Secret/hub 嵌 token**, Deployment, Service, NetworkPolicy 等) |

> ⚠️ 之前讨论过把 token 抽到独立 `Secret/hub-credentials` 然后让 backend 挂载,但**不可行**:
> - `Secret/hub` 是 chart 渲染的,token 嵌在 `data.values.yaml` 字段的 base64 串里
> - chart 的 `existingSecret` 机制在静态 `helm template` 输出 + `kubectl apply` 模式下不会生效
> - 让 backend 解析 `data.values.yaml` base64 + YAML 反序列化再取 key 太脆弱
>
> 所以**两处 token 必须手动同步**,靠注释 + 部署 SOP 保证。

## 部署 (静态 YAML 方式)

### 1. 前置条件

- 节点标签 `kubeai-jupyterhub=true` 已设置 (KubeSpawner + user-scheduler 需要):
  ```bash
  kubectl label node <node-name> kubeai-jupyterhub=true
  ```
- 节点标签 `kubeai=true` 已设置 (后端 pod 用):
  ```bash
  kubectl label node <node-name> kubeai=true
  ```
- `infra/k8s/backend-rbac.yaml` 已 apply (后端 SA 权限)
- 后端镜像 `kubeai-backend:0.1.0` 已推到节点 (或镜像仓库)

### 2. 生成 API Token

```bash
TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "TOKEN=$TOKEN"
```

### 3. 两处替换为同一个 token

`JUPYTERHUB_API_TOKEN` 在两处必须一致 (不同文件,不同 YAML key):

1. `jupyterhub.yaml` 第 594 行 `hub.services.kubeai.apiToken` — JupyterHub hub 进程的 service token
2. `infra/k8s/backend-config.yaml` `JUPYTERHUB_API_TOKEN` — 后端调 JupyterHub API 的 token

```bash
sed -i "s|a3ViZWFpLWRldi1qdXB5dGVyaHViLXRva2Vu|$TOKEN|g" \
  infra/k8s/jupyterhub/jupyterhub.yaml
sed -i "s|JUPYTERHUB_API_TOKEN: \".*\"|JUPYTERHUB_API_TOKEN: \"$TOKEN\"|" \
  infra/k8s/backend-config.yaml
```

### 4. 部署顺序

```bash
# 1. 后端基础 (RBAC + Config/Secret + Deployment)
kubectl apply -f infra/k8s/backend-rbac.yaml
kubectl apply -f infra/k8s/backend-config.yaml
kubectl apply -f infra/k8s/backend/deployment.yaml
kubectl rollout status deployment/backend -n kubeai

# 2. JupyterHub
kubectl apply -f infra/k8s/jupyterhub/jupyterhub.yaml
kubectl rollout status deployment/hub -n kubeai

# 3. 重启后端读新 token
kubectl rollout restart deployment/backend -n kubeai
```

## 验证

### 1. 两个 Secret 中 token 一致

```bash
HUB=$(kubectl get secret -n kubeai hub -o jsonpath='{.data.hub\.services\.kubeai\.apiToken}' | base64 -d)
BE=$(kubectl get secret -n kubeai backend-secret -o jsonpath='{.data.JUPYTERHUB_API_TOKEN}' | base64 -d)
[ "$HUB" = "$BE" ] && echo "✓ 两处一致" || echo "✗ 不一致"
```

### 2. Token 可用

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  -H "Authorization: token $HUB" \
  http://hub.kubeai.svc.cluster.local:8081/hub/api/users
# 期望 200
```

### 3. Pod 状态

```bash
kubectl get pods -n kubeai -l app.kubernetes.io/instance=jupyterhub
kubectl get pods -n kubeai -l app.kubernetes.io/name=backend
```

### 4. 创建开发环境

在 UI 触发,**期望不再出现 401/403/504**。

## 自定义配置

### 修改 Hub 资源、镜像、副本数等

1. 准备 values 文件:
   ```bash
   helm show values jupyterhub/jupyterhub > jupyterhub-values.yaml
   # 编辑需要的字段
   ```
2. 重新渲染:
   ```bash
   helm template jupyterhub jupyterhub/jupyterhub \
     -n kubeai \
     -f jupyterhub-values.yaml \
     > /tmp/jupyterhub.yaml.new

   # 关键: 还原手动修改的 token 行
   sed -i 's|hub.services.kubeai.apiToken: ".*"|hub.services.kubeai.apiToken: "YOUR_PRODUCTION_TOKEN"|' \
     /tmp/jupyterhub.yaml.new
   ```
3. diff 确认无意外变更:
   ```bash
   diff infra/k8s/jupyterhub/jupyterhub.yaml /tmp/jupyterhub.yaml.new
   ```
4. 替换并 apply:
   ```bash
   mv /tmp/jupyterhub.yaml.new infra/k8s/jupyterhub/jupyterhub.yaml
   kubectl apply -f infra/k8s/jupyterhub/jupyterhub.yaml
   ```

### Backend ConfigMap 对接字段

| 字段 | 值 | 用途 |
|---|---|---|
| `JUPYTERHUB_API_URL` | `http://hub.kubeai.svc.cluster.local:8081/hub/api` | JupyterHub Hub API 地址 |
| `JUPYTERHUB_BASE_URL` | `http://proxy.kubeai.svc.cluster.local:80` | 用户访问入口 (chp proxy) |
| `JUPYTERHUB_HUB_SERVICE_ACCOUNT` | `hub` | JupyterHub 内部使用的 K8s SA |
| `JUPYTERHUB_API_TOKEN` | (随机字符串) | Hub Service API token,与 jupyterhub.yaml 中一致 |
| `DEV_ENV_OPEN_TICKET_EXPIRE_SECONDS` | `60` | 单次访问票据有效期 |

## 常见问题

### 后端调 JupyterHub 报 401

两处 token 不一致。逐个 `base64 -d` 对照,确认是同一个明文。

### 创建开发环境 504 Gateway Timeout

nginx-ingress 默认 60s 超时,创建环境涉及 JupyterHub 同步等 Pod ready,需要单独建长超时:

```bash
# 方案 1: 全局调 (简单粗暴,影响所有接口)
kubectl annotate ingress -n kubeai kubeai \
  nginx.ingress.kubernetes.io/proxy-read-timeout=600 \
  nginx.ingress.kubernetes.io/proxy-send-timeout=600

# 方案 2: 拆分 Ingress (推荐,只对重型接口生效)
# 新建 ingress-long-running.yaml,只路由 /api/dev-environments 等路径
```

### `cannot update resource "networkpolicies/secrets/configmaps/resourcequotas" 403`

后端 RBAC 缺 `update` 权限。`infra/k8s/backend-rbac.yaml` 必须为这些资源加上 `update` (而非仅 `create` + `delete`):

```yaml
- apiGroups: [""]
  resources: [secrets]
  verbs: [get, list, watch, create, update, delete]
- apiGroups: [""]
  resources: [configmaps]
  verbs: [get, list, watch, create, update, delete]
- apiGroups: [""]
  resources: [resourcequotas]
  verbs: [get, list, create, update, delete]
- apiGroups: [networking.k8s.io"]
  resources: [networkpolicies]
  verbs: [get, list, create, update, delete]
```

### user-scheduler 一直 Pending

节点缺 `kubeai-jupyterhub=true` 标签 (见上文)。

### singleuser Pod ImagePullBackOff

- `singleuser.image.tag` 用了 `:latest` (生产禁止)
- 镜像需要从 Harbor 拉,确认 Harbor 已就绪

## 卸载

```bash
kubectl delete -f infra/k8s/jupyterhub/jupyterhub.yaml
```

## 安全

- `JUPYTERHUB_API_TOKEN` 视为生产密钥,推荐:
  - SealedSecret / SOPS / External Secrets 加密后提交
  - 90 天轮换一次,轮换顺序: 先改 `jupyterhub.yaml` apply → 等 hub ready → 再改 `backend-config.yaml` apply → rollout restart backend
- 节点标签 `kubeai-jupyterhub=true` 只在专用节点上打
