from pathlib import Path

from deeppresenter.agents.agent import Agent
from deeppresenter.utils.typings import InputRequest


class Design(Agent):
    async def loop(self, req: InputRequest, markdown_file: str):
        (self.workspace / "slides").mkdir(exist_ok=True)
        last_slide_count = 0  # 记录上次推送的幻灯片数量
        
        while True:
            agent_message = await self.action(
                markdown_file=markdown_file, prompt=req.designagent_prompt
            )
            yield agent_message
            
            # 检查是否有新生成的slide HTML文件，推送预览
            slide_files = sorted((self.workspace / "slides").glob("slide_*.html"))
            if slide_files and len(slide_files) > last_slide_count:
                # 只推送新生成的幻灯片（从last_slide_count开始）
                for idx in range(last_slide_count, len(slide_files)):
                    slide_file = slide_files[idx]
                    try:
                        html_content = slide_file.read_text(encoding="utf-8")
                        yield {
                            "type": "slide_preview",
                            "slide_number": idx + 1,
                            "html_content": html_content,
                            "mode": "design",
                            "total_slides": len(slide_files),
                        }
                    except Exception as e:
                        # 如果读取失败，不影响主流程
                        pass
                
                # 更新已推送的幻灯片数量
                last_slide_count = len(slide_files)
            
            outcome = await self.execute(self.chat_history[-1].tool_calls)
            if isinstance(outcome, list):
                for item in outcome:
                    yield item
            else:
                break

        yield outcome
