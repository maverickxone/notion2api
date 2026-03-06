#!/bin/bash
# ==========================================
# Notion-AI 服务管理脚本
# ==========================================

case "$1" in
    start)
        echo "🚀 启动服务..."
        docker-compose up -d
        ;;
    stop)
        echo "🛑 停止服务..."
        docker-compose down
        ;;
    restart)
        echo "🔄 重启服务..."
        docker-compose restart
        ;;
    status)
        echo "📊 服务状态："
        docker-compose ps
        echo ""
        echo "🏥 健康检查："
        curl -s http://localhost:8000/health | jq . 2>/dev/null || curl -s http://localhost:8000/health
        ;;
    logs)
        echo "📝 查看日志（Ctrl+C 退出）："
        docker-compose logs -f
        ;;
    build)
        echo "🔨 重新构建镜像..."
        docker-compose build --no-cache
        ;;
    update)
        echo "🔄 更新并重启服务..."
        docker-compose down
        docker-compose build --no-cache
        docker-compose up -d
        ;;
    clean)
        echo "🧹 清理容器和镜像..."
        docker-compose down -v
        docker system prune -f
        ;;
    backup)
        echo "💾 备份数据库..."
        BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$BACKUP_DIR"
        cp data/conversations.db "$BACKUP_DIR/"
        echo "✅ 备份完成: $BACKUP_DIR"
        ;;
    restore)
        if [ -z "$2" ]; then
            echo "❌ 请指定备份目录，例如: ./manage.sh restore backups/20240306_120000"
            exit 1
        fi
        echo "📥 恢复数据库..."
        cp "$2/conversations.db" data/
        echo "✅ 恢复完成，请重启服务: ./manage.sh restart"
        ;;
    shell)
        echo "🐚 进入容器 Shell..."
        docker-compose exec notion-opus /bin/bash
        ;;
    test)
        echo "🧪 测试 API..."
        echo "发送测试请求..."
        curl -X POST http://localhost:8000/v1/chat/completions \
            -H "Content-Type: application/json" \
            -d '{
                "model": "notion-opus",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": false
            }'
        ;;
    *)
        echo "=========================================="
        echo "  Notion-AI 服务管理脚本"
        echo "=========================================="
        echo "用法: ./manage.sh {command}"
        echo ""
        echo "命令:"
        echo "  start     - 启动服务"
        echo "  stop      - 停止服务"
        echo "  restart   - 重启服务"
        echo "  status    - 查看状态"
        echo "  logs      - 查看日志"
        echo "  build     - 重新构建镜像"
        echo "  update    - 更新并重启服务"
        echo "  clean     - 清理容器和镜像"
        echo "  backup    - 备份数据库"
        echo "  restore   - 恢复数据库 (需要指定备份目录)"
        echo "  shell     - 进入容器 Shell"
        echo "  test      - 测试 API"
        echo ""
        echo "示例:"
        echo "  ./manage.sh start"
        echo "  ./manage.sh logs"
        echo "  ./manage.sh backup"
        echo "  ./manage.sh restore backups/20240306_120000"
        echo "=========================================="
        exit 1
        ;;
esac
