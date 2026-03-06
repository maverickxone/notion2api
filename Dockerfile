# 使用官方 Python 3.11 slim 镜像作为基础镜像
FROM python:3.11-slim

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser && useradd -r -g appuser appuser

# 设置工作目录
WORKDIR /app

# 将 requirements.txt 复制到工作目录并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 将项目的源代码和前端文件复制到容器内
COPY app /app/app
COPY frontend /app/frontend
COPY main.py /app/main.py

# 创建数据目录并设置权限
RUN mkdir -p /app/data && \
    chown -R appuser:appuser /app

# 切换到非 root 用户
USER appuser

# 暴露 FastAPI 运行端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令（支持环境变量配置）
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
