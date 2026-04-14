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
from deeppresenter.utils.typings import ChatMessage, ConvertType, InputRequest, Role
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
        asyncio.create_task(run_generation_task(task_id, user_id))
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
    """WebSocket端点 - 流式推送生成进度"""
    # 打印调试信息
    print(f"\n=== WebSocket Connection Attempt ===")
    print(f"Task ID: {task_id}")
    print(f"Client: {websocket.client}")
    print(f"Headers: {dict(websocket.headers)}")
    print(f"Scope: {websocket.scope.get('type')}")
    print(f"===================================\n")
    
    # 尝试接受连接
    try:
        await websocket.accept()
        print(f"✓ WebSocket accepted for {task_id}")
    except Exception as e:
        print(f"✗ WebSocket accept failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return
    
    if task_id not in active_tasks:
        await websocket.send_json({
            "type": "error",
            "message": "Task not found",
        })
        await websocket.close()
        return
    
    task_info = active_tasks[task_id]
    
    try:
        # 发送历史消息（如果任务已经在运行）
        for msg in task_info.get("messages", []):
            await websocket.send_json(msg)
        
        # 发送token统计（如果有）
        if task_info.get("token_stats"):
            await websocket.send_json({
                "type": "token_stats",
                "data": task_info["token_stats"],
            })
        
        # 如果任务已完成，发送结果
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
        
        # 保持连接，等待新消息
        while True:
            # 检查是否有新消息
            if "websocket_queue" in task_info:
                while task_info["websocket_queue"]:
                    msg = task_info["websocket_queue"].pop(0)
                    await websocket.send_json(msg)
            
            # 检查任务状态
            if task_info["status"] in ["completed", "failed"]:
                break
            
            await asyncio.sleep(0.1)
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task {task_id}")
    except Exception as e:
        logger.error(f"WebSocket error for task {task_id}: {e}")
    finally:
        # 用户断开连接时，从 active_users 移除并触发队列处理
        user_id = task_info.get("user_id")
        if user_id and user_id in active_users:
            del active_users[user_id]
            # 触发队列处理，启动下一个任务
            asyncio.create_task(process_queue())
        await websocket.close()


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
    """后台运行生成任务"""
    task_info = active_tasks[task_id]
    task_info["status"] = "running"
    task_info["websocket_queue"] = []

    try:
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

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        task_info["status"] = "failed"
        task_info["error"] = str(e)
        task_info["websocket_queue"].append({
            "type": "error",
            "message": str(e),
        })
    finally:
        # 任务完成后，从 active_users 中移除，并触发队列处理
        if user_id in active_users:
            del active_users[user_id]
        # 触发队列处理，启动下一个任务
        asyncio.create_task(process_queue())


async def process_queue():
    """处理排队队列"""
    if not waiting_queue:
        return

    max_concurrent = config.queue.max_concurrent_tasks if config else 2

    while waiting_queue and len(active_users) < max_concurrent:
        user_id, task_data = waiting_queue.popleft()
        task_id = task_data["task_id"]

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
            except Exception as e:
                logger.error(f"Failed to send queue_started to {user_id}: {e}")

        # 启动任务
        asyncio.create_task(run_generation_task(task_id, user_id))

        # 更新队列中其他用户的等待位置
        for idx, (uid, _) in enumerate(waiting_queue):
            if uid in user_websockets:
                try:
                    await user_websockets[uid].send_json({
                        "type": "queue_update",
                        "position": idx + 1,
                    })
                except Exception as e:
                    logger.error(f"Failed to send queue_update to {uid}: {e}")


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
