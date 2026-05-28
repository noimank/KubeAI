# Harbor - 容器镜像仓库

KubeAI 使用 Harbor 管理自定义镜像构建和推送。

> Harbor 资源消耗较大 (~2Gi 内存)，开发环境可不安装。

## 部署

```bash
kubectl apply -f infra/k8s/harbor/harbor.yaml
```

> `harbor.yaml` 由 `helm template` 从 harbor-1.16.0 生成，包含 Core、Registry、Portal、JobService 及所有依赖服务。
> 默认配置: Ingress `harbor.kubeai.local`, 管理员 `admin/Harbor12345`, HTTP 模式。

## 访问

配置本地 hosts:

```
127.0.0.1 harbor.kubeai.local
```

访问 `http://harbor.kubeai.local`，默认账号 `admin / Harbor12345`。

## 与 Backend 集成

部署后在 `backend-config.yaml` Secret 中修改:

```yaml
HARBOR_URL: "http://harbor-core.kubeai.svc.cluster.local:80"
HARBOR_USERNAME: "admin"
HARBOR_PASSWORD: "Harbor12345"
```

## 验证

```bash
kubectl get pods -n kubeai -l app.kubernetes.io/instance=harbor
```

## 卸载

```bash
kubectl delete -f infra/k8s/harbor/harbor.yaml
```
