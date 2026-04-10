# DeepPresenter Vue前端

这是DeepPresenter的Vue 3前端项目，提供现代化的用户界面。

## 快速开始

### 1. 安装依赖

```bash
cd /root/projects/PPTAgent/frontend
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

前端将在 http://localhost:3000 启动

### 3. 启动后端API服务

在另一个终端：

```bash
cd /root/projects/PPTAgent
uv run uvicorn deeppresenter.server:app --reload --port 8000
```

后端API将在 http://localhost:8000 启动

### 4. 访问应用

浏览器打开 http://localhost:3000

Vite会自动将 `/api` 请求代理到后端 http://localhost:8000

## 构建生产版本

```bash
npm run build
```

构建后的文件会输出到 `dist/` 目录，可以被后端服务器直接提供。

## 项目结构

```
frontend/
├── src/
│   ├── types/          # TypeScript类型定义
│   │   └── index.ts
│   ├── App.vue         # 根组件
│   └── main.ts         # 入口文件
├── index.html
├── package.json
├── vite.config.ts      # Vite配置（包含API代理）
└── tsconfig.json       # TypeScript配置
```

## 技术栈

- Vue 3 + Composition API
- TypeScript
- Vite
- Element Plus (UI组件库)
- Pinia (状态管理)
- Axios (HTTP客户端)

## 开发说明

### API代理配置

`vite.config.ts` 中已配置API代理：

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      ws: true,  // WebSocket支持
    },
  },
}
```

所有 `/api/*` 请求会自动转发到后端，无需配置CORS。

### 环境变量

可以创建 `.env` 文件配置环境变量：

```env
VITE_API_URL=http://localhost:8000
```

## Docker部署

也可以使用Docker运行前端：

```bash
# 开发模式
docker compose --profile dev up -d

# 访问 http://localhost:3000
```

详细说明请查看项目根目录的 [DOCKER.md](../DOCKER.md)
