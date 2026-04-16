"""FastAPI server for DeepPresenter Vue frontend"""

import asyncio
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from deeppresenter.main import AgentLoop
from deeppresenter.utils.config import DeepPresenterConfig
from deeppresenter.utils.constants import WORKSPACE_BASE
from deeppresenter.utils.log import create_logger
from deeppresenter.utils.log import _context_logger  # 导入上下文日志变量
from deeppresenter.utils.typings import ChatMessage, ConvertType, InputRequest, Role

# 导入 pptagent 中的 ContextVar，用于任务取消后清理
from pptagent.response.outline import _empty_images
from pptagent.response.induct import _allowed_contents
from pptagent.document.doc_utils import _allowed_headings
from pptagent import PPTAgentServer

app = FastAPI(title="DeepPresenter API", version="1.0.0")

# CORS配置 - 开发环境允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 日志配置
timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
logger = create_logger(
    "DeepPresenterAPI",
    log_file=str(Path.home() / f".cache/deeppresenter/logs/{timestamp}-api.log"),
)

# 配置加载
try:
    config = DeepPresenterConfig.load_from_file()
except Exception as e:
    logger.warning(f"Failed to load config: {e}, using default config")
    config = None

# 任务管理
active_tasks: dict[str, dict[str, Any]] = {}

# 排队管理
active_users: dict[str, dict[str, Any]] = {}  # 正在生成的用户 {userId: task_info}
waiting_queue: deque[tuple[str, dict[str, Any]]] = deque()  # 排队队列 [(userId, request_data), ...]
user_websockets: dict[str, WebSocket] = {}  # 用户WebSocket连接 {userId: ws}

# 正在运行的任务句柄，用于取消任务
running_tasks: dict[str, asyncio.Task] = {}  # {task_id: asyncio.Task}

# process_queue 锁，防止并发执行
_process_queue_lock = asyncio.Lock()


def _log_queue_state(context: str = ""):
    """打印当前正在生成的 task ID 和排队中的 task ID"""
    active_task_ids = [info["task_id"] for info in active_users.values()]
    queued_task_ids = [data["task_id"] for _, data in waiting_queue]
    prefix = f"[{context}] " if context else ""
    logger.info(f"{prefix}正在生成的 task: {active_task_ids}, 排队中的 task: {queued_task_ids}")


# Pydantic模型
class GenerateResponse(BaseModel):
    task_id: str | None
    status: str  # running, queued, rejected
    message: str
    queue_position: int | None = None


class TaskStatus(BaseModel):
    task_id: str
    status: str  # pending, running, completed, failed
    progress: str | None = None
    result_file: str | None = None
    error: str | None = None


class TemplateList(BaseModel):
    templates: list[str]


# API端点
@app.get("/api/templates", response_model=TemplateList)
async def get_templates():
    """获取可用的模板列表"""
    try:
        templates = PPTAgentServer.list_templates()
        return TemplateList(templates=templates)
    except Exception as e:
        logger.error(f"Failed to list templates: {e}")
        return TemplateList(templates=[])


@app.get("/api/tasks/{task_id}/status", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """查询任务状态"""
    if task_id not in active_tasks:
        return TaskStatus(
            task_id=task_id,
            status="not_found",
            error="Task not found",
        )
    
    task_info = active_tasks[task_id]
    return TaskStatus(
        task_id=task_id,
        status=task_info["status"],
        progress=task_info.get("progress"),
        result_file=task_info.get("result_file"),
        error=task_info.get("error"),
    )


@app.post("/api/generate", response_model=GenerateResponse)
async def generate_presentation(
    instruction: str = Form(...),
    num_pages: str = Form("auto"),
    convert_type: str = Form("freeform"),
    template: str = Form("auto"),
    files: list[UploadFile] = File([]),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
):
    """启动PPT生成任务"""
    if config is None:
        return GenerateResponse(
            task_id=None,
            status="failed",
            message="Configuration not loaded",
        )

    # 获取用户标识
    user_id = x_user_id or "anonymous"

    # 检查用户是否已有任务在执行中
    if user_id in active_users:
        return GenerateResponse(
            task_id=None,
            status="rejected",
            message="您已有任务正在执行中，请等待完成后再提交",
        )

    # 检查用户是否已在排队中
    for idx, (uid, _) in enumerate(waiting_queue):
        if uid == user_id:
            return GenerateResponse(
                task_id=None,
                status="rejected",
                message="您已在排队中，请勿重复提交",
            )

    # 获取最大并发数
    max_concurrent = config.queue.max_concurrent_tasks if config else 2

    # 生成任务ID（不使用斜杠，避免WebSocket路由问题）
    task_id = uuid.uuid4().hex[:16]

    # 校验上传文件类型
    ALLOWED_EXTENSIONS = {'.txt', '.md', '.docx', '.pdf'}
    if files:
        for file in files:
            if file.filename:
                ext = Path(file.filename).suffix.lower()
                if ext not in ALLOWED_EXTENSIONS:
                    return GenerateResponse(
                        task_id=None,
                        status="failed",
                        message=f"不支持的文件格式: {ext}，仅支持 .txt、.md、.docx、.pdf 格式",
                    )

    # 保存上传的文件
    attachments = []
    if files:
        upload_dir = WORKSPACE_BASE / "uploads" / task_id.replace("/", "_")
        upload_dir.mkdir(parents=True, exist_ok=True)

        for file in files:
            file_path = upload_dir / file.filename
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
            attachments.append(str(file_path))

    # 创建任务信息
    task_data = {
        "status": "pending",
        "progress": None,
        "result_file": None,
        "error": None,
        "instruction": instruction,
        "num_pages": num_pages,
        "convert_type": convert_type,
        "template": template,
        "attachments": attachments,
        "messages": [],
        "token_stats": None,
        "user_id": user_id,
    }
    active_tasks[task_id] = task_data

    # 检查是否可以立即执行
    if len(active_users) < max_concurrent:
        # 直接执行
        active_users[user_id] = {"task_id": task_id, **task_data}
        task_data["status"] = "pending"
        
        # 启动任务并保存句柄
        task = asyncio.create_task(run_generation_task(task_id, user_id))
        running_tasks[task_id] = task
        logger.info(f"[Generate] Task started: task_id={task_id}, user_id={user_id}, active={len(active_users)}, running={len(running_tasks)}")
        _log_queue_state("Generate")
        
        return GenerateResponse(
            task_id=task_id,
            status="running",
            message="Task started",
            queue_position=None,
        )
    else:
        # 进入排队队列
        waiting_queue.append((user_id, {"task_id": task_id, **task_data}))
        queue_position = len(waiting_queue)
        _log_queue_state("Generate-Queued")
        return GenerateResponse(
            task_id=None,
            status="queued",
            message=f"排队中，当前位置：第{queue_position}位",
            queue_position=queue_position,
        )


@app.get("/api/download/{task_id}")
async def download_file(task_id: str):
    """下载生成的文件"""
    if task_id not in active_tasks:
        return {"error": "Task not found"}

    task_info = active_tasks[task_id]
    result_file = task_info.get("result_file")

    if not result_file or not Path(result_file).exists():
        return {"error": "File not found"}

    return FileResponse(
        path=result_file,
        filename=Path(result_file).name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@app.post("/api/queue/cancel")
async def cancel_queue(x_user_id: str | None = Header(None, alias="X-User-Id")):
    """取消排队"""
    if x_user_id is None:
        return {"success": False, "message": "User ID is required"}

    user_id = x_user_id

    # 从等待队列中移除
    for idx, (uid, task_data) in enumerate(waiting_queue):
        if uid == user_id:
            task_id = task_data.get("task_id")
            # 从队列中移除
            del waiting_queue[idx]
            # 如果有对应的任务，也删除任务记录
            if task_id and task_id in active_tasks:
                del active_tasks[task_id]

            # 更新其他用户的排队位置
            for new_idx, (remaining_uid, _) in enumerate(waiting_queue):
                if remaining_uid in user_websockets:
                    try:
                        asyncio.create_task(user_websockets[remaining_uid].send_json({
                            "type": "queue_update",
                            "position": new_idx + 1,
                        }))
                    except Exception as e:
                        logger.error(f"Failed to send queue_update to {remaining_uid}: {e}")

            # 通知用户取消成功
            if user_id in user_websockets:
                try:
                    asyncio.create_task(user_websockets[user_id].send_json({
                        "type": "queue_cancelled",
                        "reason": "用户主动取消排队",
                    }))
                except Exception:
                    pass
            return {"success": True, "message": "排队已取消"}

    return {"success": False, "message": "未找到排队记录"}


@app.websocket("/api/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket端点 - 流式推送生成进度
    
    注意：此函数只负责推送进度和触发取消，不负责资源清理
    """
    logger.info(f"[WebSocket] Connection attempt: task_id={task_id}")
    
    # 提前获取 task_info 和 user_id（避免后续访问时 task_info 可能不存在）
    task_info = active_tasks.get(task_id)
    user_id = task_info.get("user_id") if task_info else None
    
    try:
        # 尝试接受连接
        await websocket.accept()
        logger.info(f"[WebSocket] Accepted: task_id={task_id}")
        
        # 检查任务是否存在
        if task_info is None:
            await websocket.send_json({
                "type": "error",
                "message": "Task not found",
            })
            logger.warning(f"[WebSocket] Task not found: task_id={task_id}")
            return
        
        # 发送历史消息
        for msg in task_info.get("messages", []):
            await websocket.send_json(msg)
        
        # 发送token统计
        if task_info.get("token_stats"):
            await websocket.send_json({
                "type": "token_stats",
                "data": task_info["token_stats"],
            })
        
        # 发送当前状态
        if task_info["status"] == "completed":
            await websocket.send_json({
                "type": "completed",
                "file": task_info["result_file"],
            })
        elif task_info["status"] == "failed":
            await websocket.send_json({
                "type": "error",
                "message": task_info.get("error", "Unknown error"),
            })
        elif task_info["status"] == "cancelled":
            await websocket.send_json({
                "type": "error",
                "message": "任务已取消",
            })
        
        # 主循环：推送进度
        while True:
            # 发送队列中的消息
            if "websocket_queue" in task_info:
                while task_info["websocket_queue"]:
                    msg = task_info["websocket_queue"].pop(0)
                    await websocket.send_json(msg)
            
            # 检查任务是否结束
            if task_info["status"] in ["completed", "failed", "cancelled"]:
                logger.info(f"[WebSocket] Task finished: task_id={task_id}, status={task_info['status']}")
                break
            
            await asyncio.sleep(0.1)
    
    except WebSocketDisconnect:
        logger.info(f"[WebSocket] Disconnected: task_id={task_id}, user_id={user_id}")
    except Exception as e:
        logger.error(f"[WebSocket] Error: task_id={task_id}, error={type(e).__name__}: {e}")
    finally:
        # ⭐⭐⭐ 只触发取消，不清理资源 ⭐⭐⭐
        
        # 如果任务还在运行，请求取消
        # 注意：需要同时检查 running_tasks 和 task.done()
        # 因为任务可能已完成（task_info["status"] 已变为 completed）
        # 但 run_generation_task 的 finally 还没来得及清理 running_tasks
        if task_id in running_tasks:
            task = running_tasks[task_id]
            if not task.done():
                # 再次确认任务状态，避免对已完成的任务发送取消
                if task_info and task_info.get("status") in ["completed", "failed", "cancelled"]:
                    logger.info(f"[WebSocket] Task already finished (status={task_info['status']}), skip cancel: task_id={task_id}")
                else:
                    logger.info(f"[WebSocket] Requesting cancel: task_id={task_id}")
                    # 设置取消标志（让任务在下一个循环检查点退出）
                    if task_info:
                        task_info["cancelled"] = True
                    # 发送取消信号（触发 CancelledError）
                    task.cancel()
                    # 等待任务处理取消（让它的 finally 执行清理）
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
                        logger.info(f"[WebSocket] Task cancelled gracefully: task_id={task_id}")
                    except asyncio.CancelledError:
                        logger.info(f"[WebSocket] Task cancelled (CancelledError): task_id={task_id}")
                    except asyncio.TimeoutError:
                        logger.warning(f"[WebSocket] Task cancel timeout: task_id={task_id}")
            else:
                logger.info(f"[WebSocket] Task already done: task_id={task_id}")
        else:
            logger.info(f"[WebSocket] Task not in running_tasks: task_id={task_id}")
        
        # 关闭 WebSocket
        try:
            await websocket.close()
        except Exception:
            pass
        
        logger.info(f"[WebSocket] Endpoint finished: task_id={task_id}")


@app.websocket("/api/ws/queue/{user_id}")
async def queue_websocket_endpoint(websocket: WebSocket, user_id: str):
    """队列状态WebSocket端点 - 接收排队位置更新"""
    try:
        await websocket.accept()
    except Exception as e:
        logger.error(f"Failed to accept queue websocket for {user_id}: {e}")
        return

    # 保存连接到 user_websockets
    user_websockets[user_id] = websocket

    try:
        # 保持连接，等待消息
        while True:
            try:
                # 接收消息（通常不需要，客户端主要接收服务器推送）
                data = await websocket.receive_json()
                logger.info(f"Received message from queue websocket {user_id}: {data}")
            except Exception:
                # 如果接收失败，可能是连接已关闭
                break
    except WebSocketDisconnect:
        logger.info(f"Queue WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"Queue WebSocket error for user {user_id}: {e}")
    finally:
        # 清理：用户断开连接时，从队列中移除
        if user_id in user_websockets:
            del user_websockets[user_id]

        # 如果用户在排队中，从队列中移除
        user_removed = False
        for idx, (uid, task_data) in enumerate(waiting_queue):
            if uid == user_id:
                task_id = task_data.get("task_id")
                del waiting_queue[idx]
                if task_id and task_id in active_tasks:
                    del active_tasks[task_id]
                logger.info(f"Removed user {user_id} from queue due to WebSocket disconnect")
                _log_queue_state("QueueWS-Disconnect")
                user_removed = True
                break

        # 如果用户被移除，更新其他用户的排队位置
        if user_removed:
            for new_idx, (remaining_uid, _) in enumerate(waiting_queue):
                if remaining_uid in user_websockets:
                    try:
                        asyncio.create_task(user_websockets[remaining_uid].send_json({
                            "type": "queue_update",
                            "position": new_idx + 1,
                        }))
                    except Exception as e:
                        logger.error(f"Failed to send queue_update to {remaining_uid}: {e}")


async def run_generation_task(task_id: str, user_id: str):
    """后台运行生成任务
    
    注意：此函数的 finally 块是唯一的资源清理入口
    """
    logger.info(f"[Task] Starting: task_id={task_id}, user_id={user_id}")
    
    # 初始化 task_info 为 None，确保 finally 块中可以安全访问
    task_info = None

    try:
        # 获取任务信息（如果不存在则抛出 KeyError）
        task_info = active_tasks[task_id]
        task_info["status"] = "running"
        task_info["websocket_queue"] = []
        task_info["cancelled"] = False  # 取消标志
        # 创建InputRequest
        convert_type_enum = ConvertType.DEEPPRESENTER
        if task_info["convert_type"] == "template" or "模版" in task_info["convert_type"]:
            convert_type_enum = ConvertType.PPTAGENT

        selected_num_pages = (
            None if task_info["num_pages"] == "auto" else task_info["num_pages"]
        )
        template_value = (
            None if task_info["template"] == "auto" else task_info["template"]
        )

        request = InputRequest(
            instruction=task_info["instruction"],
            attachments=task_info["attachments"],
            num_pages=str(selected_num_pages) if selected_num_pages else "auto",
            convert_type=convert_type_enum,
        )

        # 创建AgentLoop
        loop = AgentLoop(
            config=config,
            session_id=task_id,
        )

        # 运行生成
        async for yield_msg in loop.run(request):
            # 检查取消标志
            if task_info.get("cancelled"):
                logger.info(f"[Task] Cancelled by flag: task_id={task_id}")
                task_info["status"] = "cancelled"
                task_info["error"] = "任务已取消"
                task_info["websocket_queue"].append({
                    "type": "error",
                    "message": "任务已取消",
                })
                break
            
            if isinstance(yield_msg, (str, Path)):
                # 生成完成
                result_file = str(yield_msg)
                task_info["result_file"] = result_file
                task_info["status"] = "completed"
                task_info["progress"] = "生成完成"

                # 收集token统计
                token_stats = collect_token_stats(loop)
                task_info["token_stats"] = token_stats

                # 发送到WebSocket队列
                task_info["websocket_queue"].append({
                    "type": "file_ready",
                    "file": result_file,
                })
                task_info["websocket_queue"].append({
                    "type": "token_stats",
                    "data": token_stats,
                })
                task_info["websocket_queue"].append({
                    "type": "completed",
                    "file": result_file,
                })

            elif isinstance(yield_msg, ChatMessage):
                # 提取文本内容（ChatMessage.content 可能是数组格式）
                content_text = yield_msg.text if hasattr(yield_msg, 'text') else (yield_msg.content or "")

                # 过滤内部工具调用（think/thinking等模型内部推理）
                internal_tool_names = {"think", "thinking", "thought", "reflection"}
                filtered_tool_calls = None
                if yield_msg.tool_calls:
                    filtered_tool_calls = [
                        {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                        for tc in yield_msg.tool_calls
                        if tc.function.name not in internal_tool_names
                    ]
                    if not filtered_tool_calls:
                        filtered_tool_calls = None

                # 如果tool消息来自内部工具（如 Tool `think` not found），跳过
                if yield_msg.role == Role.TOOL and content_text:
                    skip_msg = any(
                        content_text.startswith(f"Tool `{internal_name}")
                        for internal_name in internal_tool_names
                    )
                    if skip_msg:
                        continue

                msg_data = {
                    "type": "message",
                    "role": str(yield_msg.role),
                    "content": content_text,
                }

                if filtered_tool_calls:
                    msg_data["tool_calls"] = filtered_tool_calls

                # 如果assistant消息只有内部工具调用且无文本内容，跳过
                if yield_msg.role == Role.ASSISTANT and not filtered_tool_calls and not content_text.strip():
                    if yield_msg.tool_calls:  # 有tool_calls但都是内部工具
                        continue

                task_info["messages"].append(msg_data)
                task_info["websocket_queue"].append(msg_data)

                # 为系统消息添加阶段标识
                if yield_msg.role == Role.SYSTEM:
                    task_info["progress"] = content_text
                    # 提取阶段标识
                    if "启动任务" in content_text or "准备" in content_text:
                        msg_data["stage"] = "init"
                    elif "研究" in content_text:
                        msg_data["stage"] = "research"
                    elif "模板" in content_text or "PPTAgent" in content_text.upper():
                        msg_data["stage"] = "pptagent"
                    elif "设计" in content_text:
                        msg_data["stage"] = "design"
                    elif "转换" in content_text:
                        msg_data["stage"] = "convert"

            elif isinstance(yield_msg, dict) and yield_msg.get("type") == "slide_preview":
                # 处理幻灯片预览消息
                task_info["websocket_queue"].append(yield_msg)

    except asyncio.CancelledError:
        logger.info(f"[Task] Cancelled by asyncio: task_id={task_id}")
        task_info["status"] = "cancelled"
        task_info["error"] = "任务已取消"
        task_info["websocket_queue"].append({
            "type": "error",
            "message": "任务已取消",
        })
        # 不重新抛出，让 finally 正常执行清理

    except Exception as e:
        logger.error(f"[Task] Failed: task_id={task_id}, error={type(e).__name__}: {e}")
        task_info["status"] = "failed"
        task_info["error"] = str(e)
        task_info["websocket_queue"].append({
            "type": "error",
            "message": str(e),
        })

    finally:
        # ⭐⭐⭐ 唯一的资源清理入口 ⭐⭐⭐
        final_status = task_info.get("status", "unknown") if task_info else "unknown"
        logger.info(f"[Task] Cleanup: task_id={task_id}, user_id={user_id}, status={final_status}")
        
        # 1. 清理 running_tasks
        if task_id in running_tasks:
            del running_tasks[task_id]
            logger.info(f"[Task] Removed from running_tasks: task_id={task_id}, remaining={len(running_tasks)}")
        
        # 2. 清理 active_users
        if user_id in active_users:
            del active_users[user_id]
            logger.info(f"[Task] Removed from active_users: user_id={user_id}, remaining_active={len(active_users)}")
        
        # 3. 清理所有 ContextVar（避免后续任务继承旧的上下文）
        _context_logger.set(None)
        _empty_images.set(False)  # 重置为默认值
        _allowed_contents.set([])  # 重置为空列表
        _allowed_headings.set([])  # 重置为空列表
        
        # 4. 触发队列处理（启动下一个等待的任务）
        logger.info(f"[Task] Triggering queue processing")
        _log_queue_state("Task-Cleanup")
        asyncio.create_task(process_queue())


async def process_queue():
    """处理排队队列
    
    使用锁保护，防止多个 process_queue 实例并发执行
    使用 running_tasks 判断运行中的任务数，更准确反映并发状态
    """
    if not waiting_queue:
        return

    # 尝试获取锁，如果已被锁定则直接返回（避免重复处理）
    if _process_queue_lock.locked():
        logger.info(f"[Queue] Another process_queue is running, skipping")
        return

    async with _process_queue_lock:
        # 再次检查队列（可能在等待锁时已被处理）
        if not waiting_queue:
            logger.info(f"[Queue] Queue is empty after acquiring lock")
            return

        max_concurrent = config.queue.max_concurrent_tasks if config else 2
        logger.info(f"[Queue] Processing started: waiting={len(waiting_queue)}, running={len(running_tasks)}, max={max_concurrent}")

        started_count = 0
        while waiting_queue and len(running_tasks) < max_concurrent:
            user_id, task_data = waiting_queue.popleft()
            task_id = task_data["task_id"]
            
            logger.info(f"[Queue] Dequeuing: task_id={task_id}, user_id={user_id}, running_before={len(running_tasks)}")

            # 将任务信息更新到 active_tasks 中
            if task_id in active_tasks:
                active_tasks[task_id]["status"] = "pending"
            active_users[user_id] = task_data

            # 通知用户开始执行
            if user_id in user_websockets:
                try:
                    await user_websockets[user_id].send_json({
                        "type": "queue_started",
                        "task_id": task_id,
                    })
                    logger.info(f"[Queue] Notified user: user_id={user_id}")
                except Exception as e:
                    logger.error(f"[Queue] Failed to notify user: user_id={user_id}, error={e}")

            # 启动任务并保存句柄
            task = asyncio.create_task(run_generation_task(task_id, user_id))
            running_tasks[task_id] = task
            started_count += 1
            logger.info(f"[Queue] Task started: task_id={task_id}, running_after={len(running_tasks)}")

            # 更新队列中其他用户的等待位置
            for idx, (uid, _) in enumerate(waiting_queue):
                if uid in user_websockets:
                    try:
                        await user_websockets[uid].send_json({
                            "type": "queue_update",
                            "position": idx + 1,
                        })
                    except Exception as e:
                        logger.error(f"[Queue] Failed to update position: user_id={uid}, error={e}")
        
        logger.info(f"[Queue] Processing done: started={started_count}, waiting={len(waiting_queue)}, running={len(running_tasks)}")
        _log_queue_state("Queue-Done")


def collect_token_stats(loop: AgentLoop) -> dict:
    """收集所有agents的token统计"""
    all_agent_costs = {}
    
    if hasattr(loop, "research_agent") and loop.research_agent:
        all_agent_costs["Research Agent"] = {
            "prompt": getattr(loop.research_agent.cost, "prompt", 0),
            "completion": getattr(loop.research_agent.cost, "completion", 0),
            "total": getattr(loop.research_agent.cost, "total", 0),
            "model": loop.config.research_agent.model_name,
        }
    
    if hasattr(loop, "designagent") and loop.designagent:
        all_agent_costs["Design Agent"] = {
            "prompt": getattr(loop.designagent.cost, "prompt", 0),
            "completion": getattr(loop.designagent.cost, "completion", 0),
            "total": getattr(loop.designagent.cost, "total", 0),
            "model": loop.config.design_agent.model_name,
        }
    elif hasattr(loop, "pptagent") and loop.pptagent:
        all_agent_costs["PPT Agent"] = {
            "prompt": getattr(loop.pptagent.cost, "prompt", 0),
            "completion": getattr(loop.pptagent.cost, "completion", 0),
            "total": getattr(loop.pptagent.cost, "total", 0),
            "model": loop.config.research_agent.model_name,
        }
    
    total_prompt = 0
    total_completion = 0
    total_all = 0
    
    stats_list = []
    for agent_name, cost_info in all_agent_costs.items():
        prompt = cost_info.get("prompt", 0)
        completion = cost_info.get("completion", 0)
        total = cost_info.get("total", 0)
        model = cost_info.get("model", "N/A")
        total_prompt += prompt
        total_completion += completion
        total_all += total
        
        stats_list.append({
            "agent_name": agent_name,
            "model": model,
            "prompt": prompt,
            "completion": completion,
            "total": total,
        })
    
    return {
        "agents": stats_list,
        "total_prompt": total_prompt,
        "total_completion": total_completion,
        "total_all": total_all,
    }


# 挂载workspace目录，用于访问HTML幻灯片中的本地图片
# 注意：必须在挂载 "/" 之前，否则会被 "/" 的StaticFiles拦截
app.mount(
    "/workspace",
    StaticFiles(directory=str(WORKSPACE_BASE), check_dir=False),
    name="workspace",
)

# 生产环境：挂载静态文件
# 如果frontend/dist存在，则提供静态文件服务
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(frontend_dist), html=True),
        name="static",
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "deeppresenter.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
