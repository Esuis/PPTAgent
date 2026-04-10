#!/bin/bash

echo "========================================="
echo "  导出Docker镜像（用于离线迁移）"
echo "========================================="
echo ""

# 创建导出目录
EXPORT_DIR="./docker-images"
mkdir -p $EXPORT_DIR

echo "导出目录: $EXPORT_DIR"
echo ""

# 导出后端镜像
echo "步骤 1/2: 导出后端镜像 (~11GB)..."
docker save deeppresenter-backend:latest | gzip > $EXPORT_DIR/deeppresenter-backend.tar.gz
echo "✓ 后端镜像已导出: $EXPORT_DIR/deeppresenter-backend.tar.gz"
ls -lh $EXPORT_DIR/deeppresenter-backend.tar.gz
echo ""

# 导出前端镜像
echo "步骤 2/2: 导出前端镜像 (~95MB)..."
docker save deeppresenter-frontend:latest | gzip > $EXPORT_DIR/deeppresenter-frontend.tar.gz
echo "✓ 前端镜像已导出: $EXPORT_DIR/deeppresenter-frontend.tar.gz"
ls -lh $EXPORT_DIR/deeppresenter-frontend.tar.gz
echo ""

echo "========================================="
echo "  导出完成！"
echo "========================================="
echo ""
echo "文件列表："
ls -lh $EXPORT_DIR/*.tar.gz
echo ""
echo "传输到离线机器："
echo "  scp $EXPORT_DIR/*.tar.gz user@offline-server:/path/to/"
echo ""
echo "离线机器加载："
echo "  gunzip -c deeppresenter-backend.tar.gz | docker load"
echo "  gunzip -c deeppresenter-frontend.tar.gz | docker load"
echo ""
