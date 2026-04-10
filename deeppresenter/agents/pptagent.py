import asyncio
from pathlib import Path

from deeppresenter.agents.agent import Agent
from deeppresenter.utils.typings import InputRequest


class PPTAgent(Agent):
    async def loop(self, req: InputRequest, markdown_file: str):
        while True:
            agent_message = await self.action(
                markdown_file=markdown_file, prompt=req.pptagent_prompt
            )
            yield agent_message
            outcome = await self.execute(self.chat_history[-1].tool_calls)
            
            # 检查是否有PPTX文件并生成预览图片
            try:
                pptx_files = list(self.workspace.glob("*.pptx"))
                if pptx_files:
                    # 找到最新的PPTX文件
                    latest_pptx = max(pptx_files, key=lambda p: p.stat().st_mtime)
                    
                    # 生成预览图片
                    preview_images = await self._generate_preview_images(latest_pptx)
                    if preview_images:
                        yield {
                            "type": "slide_preview",
                            "slide_count": len(preview_images),
                            "images": preview_images,
                            "mode": "pptagent",
                        }
            except Exception as e:
                # 如果生成预览失败，不影响主流程
                pass
            
            if isinstance(outcome, list):
                for item in outcome:
                    yield item
            else:
                yield outcome
                break
    
    async def _generate_preview_images(self, pptx_path: Path) -> list[str]:
        """
        将PPTX文件转换为base64编码的图片列表
        
        Returns:
            list[str]: base64编码的图片列表
        """
        try:
            from pptx import Presentation
            import base64
            import io
            
            # 检查pptx文件是否有效
            if not pptx_path.exists() or pptx_path.stat().st_size == 0:
                return []
            
            # 尝试使用LibreOffice转换为PDF，再转为图片
            # 这需要系统安装LibreOffice
            import subprocess
            import tempfile
            
            pdf_path = pptx_path.with_suffix('.pdf')
            
            # 使用LibreOffice转换
            result = subprocess.run(
                [
                    'libreoffice',
                    '--headless',
                    '--convert-to', 'pdf',
                    '--outdir', str(pptx_path.parent),
                    str(pptx_path)
                ],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0 or not pdf_path.exists():
                return []
            
            # 将PDF转为图片
            try:
                from pdf2image import convert_from_path
                
                images = convert_from_path(
                    str(pdf_path),
                    dpi=100,  # 降低分辨率以提高性能
                    fmt='jpeg'
                )
                
                # 转为base64
                base64_images = []
                for img in images:
                    buffered = io.BytesIO()
                    img.save(buffered, format='JPEG', quality=70)
                    img_str = base64.b64encode(buffered.getvalue()).decode()
                    base64_images.append(f"data:image/jpeg;base64,{img_str}")
                
                return base64_images
            except ImportError:
                # 如果没有pdf2image，尝试使用pdfplumber
                try:
                    import pdfplumber
                    from PIL import Image
                    
                    base64_images = []
                    with pdfplumber.open(pdf_path) as pdf:
                        for page in pdf.pages:
                            img = page.to_image(resolution=100).original
                            buffered = io.BytesIO()
                            img.save(buffered, format='JPEG', quality=70)
                            img_str = base64.b64encode(buffered.getvalue()).decode()
                            base64_images.append(f"data:image/jpeg;base64,{img_str}")
                    
                    return base64_images
                except (ImportError, Exception):
                    return []
            
        except Exception as e:
            print(f"Failed to generate preview images: {e}")
            return []
