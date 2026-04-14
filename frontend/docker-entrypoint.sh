#!/bin/bash
set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 初始构建
log_info "执行初始构建..."
cd /app/frontend
npm run build
log_info "初始构建完成"

# 复制构建产物到 Nginx 目录
cp -r /app/frontend/dist/* /usr/share/nginx/html/
log_info "静态文件已部署到 Nginx"

# 启动 Nginx（后台运行）
log_info "启动 Nginx..."
nginx -g 'daemon on;'

# 文件监听函数
watch_and_build() {
    log_info "开始监听文件变化..."
    
    inotifywait -m -r -e modify,create,delete,move \
        --exclude 'node_modules|dist|\.git' \
        /app/frontend/src \
        /app/frontend/public \
        /app/frontend/index.html \
        /app/frontend/vite.config.ts \
        /app/frontend/package.json \
        2>/dev/null | while read path action file; do
            
            log_warn "检测到文件变化: $path$file ($action)"
            log_info "开始重新构建..."
            
            # 执行构建
            if npm run build; then
                log_info "构建成功，更新静态文件..."
                cp -r /app/frontend/dist/* /usr/share/nginx/html/
                log_info "静态文件更新完成"
            else
                log_error "构建失败，请检查错误日志"
            fi
        done
}

# 捕获退出信号
trap 'log_warn "收到退出信号，停止服务..."; kill $(jobs -p) 2>/dev/null; exit 0' SIGTERM SIGINT

# 启动文件监听
watch_and_build &

# 保持容器运行
log_info "前端服务已启动（生产模式 + 文件监听）"
log_info "访问地址: http://localhost:80"

# 等待所有后台进程
wait
