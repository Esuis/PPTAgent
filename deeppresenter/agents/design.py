from pathlib import Path

from deeppresenter.agents.agent import Agent
from deeppresenter.utils.typings import InputRequest


class Design(Agent):
    async def _check_and_push_changed_slides(self, slide_mtimes: dict[str, float]):
        """检查slide HTML文件变化，推送修改过的幻灯片预览

        Args:
            slide_mtimes: 记录每个文件上次推送时的mtime，会被原地更新
        """
        slide_files = sorted((self.workspace / "slides").glob("slide_*.html"))
        if not slide_files:
            return

        for idx, slide_file in enumerate(slide_files):
            try:
                current_mtime = slide_file.stat().st_mtime
                last_mtime = slide_mtimes.get(slide_file.name, 0.0)

                if current_mtime > last_mtime:
                    html_content = slide_file.read_text(encoding="utf-8")
                    yield {
                        "type": "slide_preview",
                        "slide_number": idx + 1,
                        "html_content": html_content,
                        "mode": "design",
                        "total_slides": len(slide_files),
                    }
                    slide_mtimes[slide_file.name] = current_mtime
            except Exception:
                # 如果读取失败，不影响主流程
                pass

    async def loop(self, req: InputRequest, markdown_file: str):
        (self.workspace / "slides").mkdir(exist_ok=True)
        slide_mtimes: dict[str, float] = {}  # 记录每个slide文件上次推送时的mtime

        while True:
            agent_message = await self.action(
                markdown_file=markdown_file, prompt=req.designagent_prompt
            )
            yield agent_message

            # action后检查文件变化并推送
            async for preview_msg in self._check_and_push_changed_slides(slide_mtimes):
                yield preview_msg

            outcome = await self.execute(self.chat_history[-1].tool_calls)

            if isinstance(outcome, list):
                for item in outcome:
                    yield item

            # execute后检查文件变化并推送（工具执行可能修改了已有slide）
            # 放在outcome之后，保证工具执行结果消息先于预览推送
            async for preview_msg in self._check_and_push_changed_slides(slide_mtimes):
                yield preview_msg

            if not isinstance(outcome, list):
                break

        yield outcome
