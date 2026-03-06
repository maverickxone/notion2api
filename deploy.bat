@echo off
REM ==========================================
REM Notion-AI Docker 部署脚本 (Windows)
REM ==========================================

echo ==========================================
echo   Notion-AI Docker 部署脚本
echo ==========================================
echo.

REM 检查 Docker 是否安装
docker --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker 未安装，请先安装 Docker Desktop
    pause
    exit /b 1
)

REM 检查 .env 文件是否存在
if not exist .env (
    echo ⚠️  .env 文件不存在，正在从 .env.example 创建...
    if exist .env.example (
        copy .env.example .env >nul
        echo ✅ 已创建 .env 文件
        echo 📝 请编辑 .env 文件，填入你的 Notion 账号信息
        echo    编辑完成后，再次运行此脚本
        pause
        exit /b 0
    ) else (
        echo ❌ .env.example 文件不存在
        pause
        exit /b 1
    )
)

REM 创建必要的目录
echo 📁 创建数据目录...
if not exist data mkdir data
if not exist logs mkdir logs

REM 构建镜像
echo 🔨 构建 Docker 镜像...
docker-compose build --no-cache

REM 启动服务
echo 🚀 启动服务...
docker-compose up -d

REM 等待服务启动
echo ⏳ 等待服务启动...
timeout /t 5 /nobreak >nul

REM 检查服务状态
echo.
echo 📊 服务状态：
docker-compose ps

REM 检查健康状态
echo.
echo 🏥 健康检查：
curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo ❌ 服务启动失败，请查看日志：
    echo    docker-compose logs
) else (
    echo ✅ 服务运行正常！
    echo.
    echo 🌐 访问地址：
    echo    - Web 界面: http://localhost:8000
    echo    - API 文档: http://localhost:8000/docs
    echo    - 健康检查: http://localhost:8000/health
    echo.
    echo 📝 查看日志：
    echo    docker-compose logs -f
    echo.
    echo 🛑 停止服务：
    echo    docker-compose down
)

echo.
echo ==========================================
echo   部署完成！
echo ==========================================
pause
