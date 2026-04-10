"""FastAPI server for DeepPresenter Vue frontend"""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
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


# Pydantic模型
class GenerateResponse(BaseModel):
    task_id: str
    status: str
    message: str


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
):
    """启动PPT生成任务"""
    if config is None:
        return GenerateResponse(
            task_id="",
            status="failed",
            message="Configuration not loaded",
        )
    
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
    active_tasks[task_id] = {
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
    }
    
    # 在后台启动任务
    asyncio.create_task(run_generation_task(task_id))
    
    return GenerateResponse(
        task_id=task_id,
        status="pending",
        message="Task started",
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
        await websocket.close()


async def run_generation_task(task_id: str):
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
                # 处理聊天消息
                # 提取文本内容（ChatMessage.content 可能是数组格式）
                content_text = yield_msg.text if hasattr(yield_msg, 'text') else (yield_msg.content or "")
                
                msg_data = {
                    "type": "message",
                    "role": str(yield_msg.role),
                    "content": content_text,
                }
                
                if yield_msg.tool_calls:
                    msg_data["tool_calls"] = [
                        {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                        for tc in yield_msg.tool_calls
                    ]
                
                task_info["messages"].append(msg_data)
                task_info["websocket_queue"].append(msg_data)
                
                # 更新进度
                if yield_msg.role == Role.SYSTEM:
                    task_info["progress"] = yield_msg.content
    
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        task_info["status"] = "failed"
        task_info["error"] = str(e)
        task_info["websocket_queue"].append({
            "type": "error",
            "message": str(e),
        })


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
