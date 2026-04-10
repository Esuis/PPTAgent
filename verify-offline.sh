#!/bin/bash

echo "========================================="
echo "  验证镜像是否可以在离线环境运行"
echo "========================================="
echo ""

echo "测试后端（禁用网络）..."
docker run --rm --network none deeppresenter-backend:latest bash -c "
    /opt/.venv/bin/python -c '
import sys
print(\"Python版本:\", sys.version)
try:
    import pptagent
    print(\"✓ pptagent\")
except Exception as e:
    print(\"✗ pptagent失败:\", e)
    
try:
    import gradio
    print(\"✓ gradio:\", gradio.__version__)
except Exception as e:
    print(\"✗ gradio失败:\", e)
    
try:
    import openai
    print(\"✓ openai:\", openai.__version__)
except Exception as e:
    print(\"✗ openai失败:\", e)
    
try:
    import fastapi
    print(\"✓ fastapi:\", fastapi.__version__)
except Exception as e:
    print(\"✗ fastapi失败:\", e)
    
print(\"\\n=========================================\")
print(\"如果所有包都显示✓，说明可以离线运行！\")
print(\"=========================================\")
'
"

echo ""
echo "测试前端（禁用网络）..."
docker run --rm --network none deeppresenter-frontend:latest nginx -v 2>&1 && echo "✓ Nginx可用"

echo ""
echo "========================================="
echo "  验证完成！"
echo "========================================="
