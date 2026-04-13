# PPT生成排队功能设计方案

## 一、功能概述

为避免过多用户同时请求导致服务器资源耗尽，设计排队机制限制同时生成PPT的用户数量。

## 二、核心配置

| 配置项 | 值 | 说明 |
|-------|-----|------|
| Cookie名称 | `JSESSIONID` | 用于识别用户身份 |
| 持久化 | 不需要 | 服务重启后队列清空 |
| VIP优先 | 无 | 所有用户平等排队 |
| 同用户多任务 | 禁止 | 同一用户只能有1个任务 |
| 最大排队人数 | 无限制 | 任何用户都可进入队列 |
| 排队时机 | 发送指令后 | 点击发送才进入队列 |
| 任务超时 | 不设置 | 生成时间无上限 |
| 并发执行数 | 可配置 | 默认2个，通过配置文件设置 |

## 三、用户标识获取流程

```
优先级：URL Token > Cookie > localStorage

1. 检查 URL 参数 ?guwpToken=xxx → 作为 userId
2. 如果没有，检查 Cookie 中的 JSESSIONID → 作为 userId  
3. 如果没有，检查 localStorage 中的 pptagent_user_id
4. 如果都没有，生成 UUID 存入 localStorage，key: pptagent_user_id
```

## 四、后端队列数据结构

```python
# 配置项
MAX_CONCURRENT_TASKS = 2  # 可配置，最大并发执行数

# 数据结构
active_users: dict[str, dict] = {}      # 正在生成的用户 {userId: task_info}
waiting_queue: deque[tuple[str, dict]]  # 排队队列 [(userId, request_data), ...]
user_websockets: dict[str, WebSocket]   # 用户WebSocket连接 {userId: ws}
```

## 五、核心流程

```
用户点击发送
    ↓
前端获取 userId
    ↓
调用 POST /api/generate (携带 X-User-Id)
    ↓
后端判断：
├── 该 userId 在 active_users 中 → 拒绝，返回"您已有任务正在执行中"
├── 该 userId 在 waiting_queue 中 → 拒绝，返回"您已在排队中"
├── len(active_users) < MAX_CONCURRENT_TASKS → 直接执行
└── len(active_users) >= MAX_CONCURRENT_TASKS → 进入队列排队
    ↓
前端根据响应：
├── 直接执行 → 正常流程
└── 进入队列 → 弹窗显示排队位置，监听WebSocket更新
```

## 六、API设计

### 请求

```http
POST /api/generate
Headers: X-User-Id: <userId>
Body: FormData (instruction, files, num_pages, ...)
```

### 响应 - 直接执行

```json
{
    "task_id": "abc123",
    "status": "running",
    "queue_position": null
}
```

### 响应 - 进入排队

```json
{
    "task_id": null,
    "status": "queued",
    "queue_position": 3
}
```

### 响应 - 拒绝（已有任务）

```json
{
    "task_id": null,
    "status": "rejected",
    "message": "您已有任务正在执行中，请等待完成后再提交"
}
```

## 七、WebSocket 消息扩展

| 类型 | 说明 | 数据 |
|------|------|------|
| `queue_update` | 排队位置更新 | `{"type": "queue_update", "position": 2}` |
| `queue_started` | 轮到用户，开始执行 | `{"type": "queue_started", "task_id": "xxx"}` |
| `queue_cancelled` | 排队被取消 | `{"type": "queue_cancelled", "reason": "..."}` |

## 八、异常处理

| 场景 | 处理方式 |
|------|---------|
| 用户关闭页面/断开WebSocket | 从队列中移除该用户 |
| 用户主动取消排队 | 从队列中移除，发送 `queue_cancelled` |
| 任务完成/失败 | 从 `active_users` 移除，检查队列是否有等待用户 |
| 服务重启 | 队列清空（不持久化） |

## 九、配置文件设计

在 `config.yaml` 中添加：

```yaml
queue:
  max_concurrent_tasks: 2  # 同时最多执行的用户数
```

## 十、涉及的文件修改

| 文件 | 修改内容 |
|------|---------|
| `deeppresenter/server.py` | 添加队列管理逻辑、用户标识校验、WebSocket消息扩展 |
| `deeppresenter/utils/config.py` | 添加队列配置项 |
| `frontend/src/stores/chat.ts` | 添加userId获取、排队状态管理 |
| `frontend/src/api/presentation.ts` | 请求携带 X-User-Id 头部 |
| `frontend/src/views/Home.vue` | 添加排队弹窗 |
| `frontend/src/components/QueueDialog.vue` | 新建排队弹窗组件 |

## 十一、前端弹窗设计

```
┌─────────────────────────────────────┐
│  ⏳ 正在排队等待                      │
├─────────────────────────────────────┤
│                                     │
│  当前位置：第 3 位                    │
│                                     │
│  [取消排队]                          │
│                                     │
└─────────────────────────────────────┘
```

- 弹窗需支持实时更新位置
- 提供"取消排队"按钮
- 轮到用户时自动关闭弹窗，进入正常生成流程
