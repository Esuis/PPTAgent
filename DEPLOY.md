# DeepPresenter 部署指南

## 🚀 一键启动

```bash
docker compose up -d
```

访问：
- 前端：http://localhost:3000
- 后端：http://localhost:8000

---

## 📦 完整流程

### 在线机器（构建）

```bash
# 1. 构建镜像
docker compose build

# 2. 测试启动
docker compose up -d

# 3. 验证正常后停止
docker compose down
```

### 导出镜像（离线迁移）

```bash
# 运行导出脚本
./export-images.sh

# 生成文件：
# ./docker-images/deeppresenter-backend.tar.gz   (~3.2GB)
# ./docker-images/deeppresenter-frontend.tar.gz  (~26MB)
```

### 离线机器（运行）

```bash
# 1. 加载镜像
gunzip -c deeppresenter-backend.tar.gz | docker load
gunzip -c deeppresenter-frontend.tar.gz | docker load

# 2. 启动服务
docker compose up -d

# 3. 验证
docker compose ps
curl http://localhost:8000/docs
```

---

## 🔧 文件说明

### 保留的核心文件

```
Dockerfile.backend.offline   # 后端镜像（基于deeppresenter-host:0.1.0）
Dockerfile.frontend.prod     # 前端镜像（Nginx + Vue）
docker-compose.yml           # 服务编排
export-images.sh             # 导出镜像脚本
verify-offline.sh            # 验证离线可用性
```

### 配置文件

```
.env                         # 环境变量
deeppresenter/config.yaml    # 应用配置
deeppresenter/mcp.json       # MCP配置
```

---

## ❓ 常见问题

### Q: 如何更新代码？

```bash
# 在线机器
docker compose build
./export-images.sh
# 传输到离线机器，重新加载
```

### Q: 如何验证离线可用？

```bash
./verify-offline.sh
```

### Q: 如何查看日志？

```bash
docker compose logs -f
docker compose logs -f backend
docker compose logs -f frontend
```

### Q: 如何停止服务？

```bash
docker compose down
```

---

## 📊 架构说明

```
前端 (Nginx:80)          后端 (FastAPI:8000)
     ↓                          ↓
Vue静态文件              Python + /opt/.venv
端口: 3000               端口: 8000
镜像: ~95MB              镜像: ~11GB
                         基于: deeppresenter-host:0.1.0
```

**关键**：
- ✅ 使用基础镜像的 `/opt/.venv`（已包含所有依赖）
- ✅ 只安装 pptagent 包本身（`--no-deps`）
- ✅ 运行时直接使用 `/opt/.venv/bin/python`，不下载任何东西

---

## ✅ 检查清单

### 构建前
- [ ] Docker已安装并运行
- [ ] 基础镜像存在：`docker images | grep deeppresenter-host`
- [ ] 配置文件就绪：`.env`, `config.yaml`

### 构建后
- [ ] 镜像构建成功：`docker images`
- [ ] 服务启动成功：`docker compose up -d`
- [ ] 前端可访问：http://localhost:3000
- [ ] 后端可访问：http://localhost:8000/docs

### 离线部署
- [ ] 镜像已导出：`./export-images.sh`
- [ ] 文件已传输到离线机器
- [ ] 镜像已加载：`docker load`
- [ ] 服务启动成功：`docker compose up -d`
- [ ] 无网络下载：`docker compose logs | grep -i download`
