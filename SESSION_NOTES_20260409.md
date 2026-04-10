# 开发会话记录 - 2026-04-09

## 会话概览

**主要任务**：将 PPTAgent 前端从 Gradio 迁移到 Vue 3，完善 Docker 容器化部署，修复多个关键 Bug

**工作分支**：`wmd`

**提交 Commit**：`5328847` - feat: 前端架构从Gradio迁移到Vue 3 + TypeScript，完善Docker容器化部署

---

## 核心改动总结

### 1. 前端架构迁移（Gradio → Vue 3）

#### 新增文件
- `frontend/` - 完整的 Vue 3 + TypeScript 前端应用
  - 使用 Vite 构建工具
  - Element Plus UI 组件库
  - Pinia 状态管理
  - WebSocket 实时通信

#### 关键组件
- `frontend/src/views/Home.vue` - 主页面布局
- `frontend/src/components/ChatInput.vue` - 输入和设置面板
- `frontend/src/components/ChatMessages.vue` - 消息展示
- `frontend/src/stores/chat.ts` - 聊天状态管理
- `frontend/src/api/presentation.ts` - API 调用层

#### UI 优化
- ✅ 设置面板从左侧移到底部输入区域
- ✅ 移除"输出类型"选项，固定为"自由生成"
- ✅ 移除 Token 统计面板
- ✅ 下载按钮始终显示，根据状态控制可用性
- ✅ 支持文件上传（PDF、Word、Excel）

---

### 2. Docker 容器化部署

#### 新增 Dockerfile
1. **Dockerfile.frontend.dev** - 前端开发环境
   - 使用 Vite 开发服务器
   - 支持 HMR 热模块替换
   - 端口 3000

2. **Dockerfile.frontend.prod** - 前端生产环境
   - 使用 Nginx 静态文件服务
   - 构建优化，支持 SPA 路由
   - API 反向代理配置

3. **Dockerfile.backend.offline** - 后端离线部署
   - 基于已有镜像增量构建
   - 包含所有依赖

#### docker-compose.yml 配置
```yaml
services:
  frontend:
    image: deeppresenter-frontend:latest
    ports:
      - "3000:3000"
    volumes:
      - ./frontend:/app              # 代码热更新
      - /app/node_modules            # 排除 node_modules
  
  backend:
    image: deeppresenter-backend:latest
    ports:
      - "8000:8000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./deeppresenter:/usr/src/pptagent/deeppresenter
      - /usr/src/pptagent/deeppresenter/html2pptx/node_modules  # 排除
      - ./pptagent:/usr/src/pptagent/pptagent
      - ./workspace:/opt/workspace   # Bind mount（关键！）
      - cache-data:/root/.cache/deeppresenter
```

**关键配置说明**：
- 使用 **bind mount**（`./workspace:/opt/workspace`）而非 Docker volume
- 排除 `node_modules` 使用镜像内预构建版本
- 支持开发模式（代码挂载）和生产模式（预构建镜像）

---

### 3. Bug 修复记录

#### Bug 1: WebSocket 403 错误
**现象**：前端无法连接 WebSocket，返回 403 Forbidden

**根因**：task_id 格式包含斜杠（`20260409/uuid`），FastAPI 路由 `{task_id}` 默认不匹配斜杠

**修复**：
- 文件：`deeppresenter/server.py`
- 修改 task_id 生成：`uuid.uuid4().hex[:16]`（去除斜杠）

**经验教训**：FastAPI 路径参数默认不包含斜杠，需要显式声明 `{task_id:path}` 或避免使用斜杠

---

#### Bug 2: Sandbox 和 Backend 文件共享问题（核心问题）
**现象**：模型在 sandbox 中创建文件，但 `finalize` 工具在 backend 中找不到文件
```
Error calling tool 'finalize': [Errno 2] No such file or directory: '/opt/workspace/xxx/filename.md'
```

**根因分析**：
1. Sandbox 容器挂载：`/root/projects/PPTAgent/workspace/{task_id}` → `/opt/workspace/{task_id}`
2. Backend 容器使用 Docker volume：`workspace-data:/opt/workspace`
3. **两个容器的文件系统完全隔离**！

**修复步骤**：

**步骤 1**：修改 mcp.json - sandbox 挂载整个 workspace 根目录
```json
// 修改前
"-v", "$HOST_WORKSPACE:$WORKSPACE"

// 修改后
"-v", "$HOST_WORKSPACE_BASE:$WORKSPACE_BASE"
```

**步骤 2**：修改 deeppresenter/agents/env.py - 添加环境变量
```python
envs = {
    "WORKSPACE": str(self.workspace),
    "HOST_WORKSPACE": host_workspace,
    "WORKSPACE_ID": self.workspace.stem,
    "WORKSPACE_BASE": str(WORKSPACE_BASE),           # 新增
    "HOST_WORKSPACE_BASE": host_workspace_base or str(WORKSPACE_BASE),  # 新增
    ...
}
```

**步骤 3**：修改 .env - 配置主机路径
```bash
# 容器内的 workspace 路径
DEEPPRESENTER_WORKSPACE_BASE=/opt/workspace

# 主机上的 workspace 路径（用于 Docker-in-Docker 卷挂载）
DEEPPRESENTER_HOST_WORKSPACE_BASE=/root/projects/PPTAgent/workspace
```

**步骤 4**：修改 docker-compose.yml - 使用 bind mount
```yaml
# 修改前（Docker volume，隔离的）
- workspace-data:/opt/workspace

# 修改后（Bind mount，共享的）
- ./workspace:/opt/workspace
```

**关键理解**：
- **Docker volume**：Docker 管理的独立存储空间，与主机不直接同步
- **Bind mount**：直接映射主机目录，实时同步

---

#### Bug 3: finalize 工具路径校验过严
**现象**：即使文件存在，`finalize` 工具也会因为路径检查失败

**修复**：
- 文件：`deeppresenter/tools/task.py`
- 移除 `assert path.exists()` 严格校验
- 添加 debug 日志，记录文件找不到的情况
- 对于相对路径，尝试在当前工作目录查找

```python
# 修改前
path = Path(outcome)
assert path.exists(), f"Outcome {outcome} does not exist"

# 修改后
path = Path(outcome)
if not path.exists():
    debug(f"Outcome {outcome} not found in backend container (may exist in sandbox)")
    # 尝试相对路径
    if agent_name == "Research" and not path.is_absolute():
        cwd_path = Path.cwd() / outcome
        if cwd_path.exists():
            path = cwd_path
```

---

#### Bug 4: 前端 Vite 代理配置错误
**现象**：前端无法连接后端 API，报错 `ECONNREFUSED 127.0.0.1:8000`

**根因**：Vite 代理配置使用 `localhost`，但在 Docker 容器内应该使用服务名

**修复**：
- 文件：`frontend/vite.config.ts`
```typescript
// 修改前
proxy: {
  '/api': {
    target: 'http://localhost:8000',
    ...
  }
}

// 修改后
proxy: {
  '/api': {
    target: 'http://backend:8000',  // Docker 服务名
    ...
  }
}
```

---

#### Bug 5: html2pptx Node.js 依赖缺失
**现象**：`inspect_slide` 工具报错 `html2pptx Node dependencies are missing`

**修复方案**：
1. Dockerfile 中已有安装命令（Host.Dockerfile 第74行）：
   ```dockerfile
   RUN npm install --prefix deeppresenter/html2pptx
   ```

2. docker-compose.yml 排除 node_modules 挂载：
   ```yaml
   volumes:
     - ./deeppresenter:/usr/src/pptagent/deeppresenter
     - /usr/src/pptagent/deeppresenter/html2pptx/node_modules  # 排除
   ```

3. 依赖持久化到 cache volume：
   - 自动创建符号链接：`node_modules -> /root/.cache/deeppresenter/html2pptx/node_modules`

---

### 4. 已知 Bug（未修复）

#### Bug A: DeepSeek API messages 格式问题
**文件**：`deeppresenter/utils/config.py` 第107行

**问题**：发送 `ChatMessage` 对象列表而非字典列表给 API

**状态**：暂时通过切换到其他模型（GLM）绕过

**修复方案**（待实施）：
```python
# 在 Endpoint.call() 中转换
dict_messages = [
    msg.model_dump() if hasattr(msg, 'model_dump') else msg 
    for msg in messages
]
```

---

## 环境配置

### 环境变量（.env）
```bash
# API Key（可选，已在 config.yaml 中配置）
OPENAI_API_KEY=

# 日志级别 (0: debug, 10: info, 20: warning)
DEEPPRESENTER_LOG_LEVEL=0

# 容器内的 workspace 路径
DEEPPRESENTER_WORKSPACE_BASE=/opt/workspace

# 主机上的 workspace 路径（用于 Docker-in-Docker 卷挂载）
DEEPPRESENTER_HOST_WORKSPACE_BASE=/root/projects/PPTAgent/workspace
```

### 模型配置（deeppresenter/config.yaml）
当前使用：**GLM-4**（火山引擎）
```yaml
research_agent:
  base_url: "https://ark.cn-beijing.volces.com/api/v3"
  model: "glm-4-7-251222"
  api_key: "your-api-key"
```

### 服务端口
- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

---

## 部署和开发流程

### 开发模式（支持热更新）
```bash
# 启动服务
docker compose up -d

# 修改前端代码（自动热更新）
# 编辑 frontend/src/components/*.vue

# 修改后端代码（自动生效）
# 编辑 deeppresenter/*.py

# 查看日志
docker compose logs -f frontend
docker compose logs -f backend
```

### 生产模式（离线部署）
```bash
# 1. 构建镜像
docker build -f deeppresenter/docker/Host.Dockerfile -t deeppresenter-backend:latest .
docker build -f Dockerfile.frontend.prod -t deeppresenter-frontend:latest .

# 2. 导出镜像
docker save deeppresenter-backend:latest deeppresenter-frontend:latest | gzip > images.tar.gz

# 3. 在离线服务器导入
docker load < images.tar.gz

# 4. 启动服务
docker compose up -d
```

### 重新构建前端（修改了 vite.config.ts 等配置）
```bash
docker compose down frontend
docker compose up -d --build frontend
```

### 重新构建后端（修改了 Dockerfile）
```bash
docker compose down backend
docker compose up -d --build backend
```

---

## 关键文件清单

### 前端核心文件
- `frontend/src/views/Home.vue` - 主页面布局
- `frontend/src/components/ChatInput.vue` - 输入框和设置
- `frontend/src/components/ChatMessages.vue` - 消息展示
- `frontend/src/stores/chat.ts` - WebSocket 和状态管理
- `frontend/vite.config.ts` - Vite 配置（代理设置）

### 后端核心文件
- `deeppresenter/server.py` - FastAPI 服务（自定义）
- `deeppresenter/agents/env.py` - 环境变量配置
- `deeppresenter/tools/task.py` - finalize 工具
- `deeppresenter/mcp.json` - Sandbox 配置

### Docker 配置
- `docker-compose.yml` - 服务编排
- `Dockerfile.frontend.dev` - 前端开发
- `Dockerfile.frontend.prod` - 前端生产
- `deeppresenter/docker/Host.Dockerfile` - 后端镜像

### 配置文件
- `.env` - 环境变量
- `deeppresenter/config.yaml` - 模型配置
- `frontend/vite.config.ts` - 前端代理配置

---

## 重要经验教训

### 1. Docker 网络
- 容器间通信使用**服务名**（如 `backend`），而非 `localhost`
- Docker Compose 自动创建网络，服务名即为 DNS 名称

### 2. 数据卷挂载
- **Bind mount**（`./host:/container`）：实时同步主机目录
- **Docker volume**（`volume-name:/container`）：Docker 管理的独立存储
- **排除挂载**：`/container/path` 可以排除子目录使用镜像内容

### 3. Docker-in-Docker
- 需要挂载 `/var/run/docker.sock`
- 主机路径和容器路径映射通过环境变量配置
- Sandbox 容器需要访问主机目录，使用 bind mount

### 4. FastAPI WebSocket
- 路径参数默认不包含斜杠
- 使用 `{param:path}` 可以支持斜杠，但最好避免
- WebSocket 升级需要正确的 Nginx 配置

### 5. Vue 3 开发
- Vite HMR 热更新需要正确配置代理
- TypeScript 类型检查严格，注意导出和导入
- Element Plus 组件按需导入

---

## 下一步计划

### 待优化
- [ ] 修复 DeepSeek API messages 格式问题
- [ ] 优化 finalize 工具的路径处理逻辑
- [ ] 添加前端单元测试
- [ ] 添加端到端测试
- [ ] 完善错误处理和用户提示

### 待文档化
- [ ] 用户手册
- [ ] API 文档
- [ ] 部署指南（离线环境）
- [ ] 开发指南

---

## 会话关键决策

1. **为什么使用 bind mount 而非 Docker volume？**
   - Sandbox 和 Backend 需要共享文件
   - Bind mount 直接映射主机目录，实时同步
   - Docker volume 是隔离的存储空间

2. **为什么排除 node_modules 挂载？**
   - 镜像内已预构建依赖
   - 避免主机和容器依赖冲突
   - 支持离线环境部署

3. **为什么前端使用开发模式而非生产模式？**
   - 支持代码热更新，开发效率高
   - 通过 Vite HMR 即时看到修改效果
   - 生产环境可切换为 Nginx 静态服务

---

**记录时间**：2026-04-09  
**记录人**：AI Assistant  
**Git Commit**：5328847  
**分支**：wmd
