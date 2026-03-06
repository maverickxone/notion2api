#!/bin/bash
# ==========================================
# Notion-AI Docker 部署脚本
# ==========================================

set -e  # 遇到错误立即退出

echo "=========================================="
echo "  Notion-AI Docker 部署脚本"
echo "=========================================="

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi

# 检查 Docker Compose 是否安装
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose 未安装，请先安装 Docker Compose"
    exit 1
fi

# 检查 .env 文件是否存在
if [ ! -f .env ]; then
    echo "⚠️  .env 文件不存在，正在从 .env.example 创建..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ 已创建 .env 文件"
        echo "📝 请编辑 .env 文件，填入你的 Notion 账号信息"
        echo "   编辑完成后，再次运行此脚本"
        exit 0
    else
        echo "❌ .env.example 文件不存在"
        exit 1
    fi
fi

# 创建必要的目录
echo "📁 创建数据目录..."
mkdir -p data logs

# 构建镜像
echo "🔨 构建 Docker 镜像..."
docker-compose build --no-cache

# 启动服务
echo "🚀 启动服务..."
docker-compose up -d

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 检查服务状态
echo ""
echo "📊 服务状态："
docker-compose ps

# 检查健康状态
echo ""
echo "🏥 健康检查："
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ 服务运行正常！"
    echo ""
    echo "🌐 访问地址："
    echo "   - Web 界面: http://localhost:8000"
    echo "   - API 文档: http://localhost:8000/docs"
    echo "   - 健康检查: http://localhost:8000/health"
    echo ""
    echo "📝 查看日志："
    echo "   docker-compose logs -f"
    echo ""
    echo "🛑 停止服务："
    echo "   docker-compose down"
else
    echo "❌ 服务启动失败，请查看日志："
    echo "   docker-compose logs"
fi

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
