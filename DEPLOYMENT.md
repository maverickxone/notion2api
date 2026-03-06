# Notion-AI 服务器部署指南

本文档详细介绍如何将 Notion-AI 项目部署到服务器上。

## 📋 目录

1. [服务器要求](#服务器要求)
2. [部署准备](#部署准备)
3. [快速部署](#快速部署)
4. [管理命令](#管理命令)
5. [Nginx 反向代理](#nginx-反向代理)
6. [故障排查](#故障排查)
7. [安全建议](#安全建议)

---

## 🖥️ 服务器要求

### 最低配置

- **CPU**: 1 核心
- **内存**: 512MB
- **硬盘**: 10GB 可用空间
- **操作系统**: Linux (Ubuntu 20.04+, Debian 11+, CentOS 8+)

### 推荐配置

- **CPU**: 2 核心
- **内存**: 2GB
- **硬盘**: 20GB 可用空间
- **网络**: 稳定的互联网连接

### 软件要求

- **Docker**: 20.10+
- **Docker Compose**: 1.29+ 或 Docker Compose V2
- **Nginx**: 1.18+ (可选，用于反向代理)

---

## 📦 部署准备

### 1. 安装 Docker

#### Ubuntu/Debian

```bash
# 更新包索引
sudo apt-get update

# 安装依赖
sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# 添加 Docker 官方 GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# 添加 Docker 仓库
echo \
  "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装 Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker --version
docker-compose --version
```

#### CentOS/RHEL

```bash
# 安装 Docker
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install -y docker-ce docker-ce-cli containerd.io

# 启动 Docker
sudo systemctl start docker
sudo systemctl enable docker

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. 配置防火墙

```bash
# Ubuntu/Debian (UFW)
sudo ufw allow 8000/tcp
sudo ufw reload

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### 3. 上传项目文件

```bash
# 在本地打包项目
tar -czf notion-ai.tar.gz \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='data' \
    --exclude='*.pyc' \
    .

# 上传到服务器
scp notion-ai.tar.gz user@your-server:/home/user/

# 在服务器上解压
ssh user@your-server
cd /home/user
tar -xzf notion-ai.tar.gz
cd notion-ai
```

或者使用 Git：

```bash
# 在服务器上克隆仓库
git clone https://your-repo-url/notion-ai.git
cd notion-ai
```

---

## 🚀 快速部署

### 方法 1: 使用部署脚本（推荐）

```bash
# 给脚本添加执行权限
chmod +x deploy.sh

# 运行部署脚本
./deploy.sh
```

### 方法 2: 手动部署

```bash
# 1. 复制环境变量文件
cp .env.example .env

# 2. 编辑 .env 文件，填入你的 Notion 账号信息
nano .env

# 3. 创建必要的目录
mkdir -p data logs

# 4. 构建并启动服务
docker-compose up -d

# 5. 查看服务状态
docker-compose ps

# 6. 查看日志
docker-compose logs -f
```

### 验证部署

```bash
# 检查服务健康状态
curl http://localhost:8000/health

# 预期输出：
# {
#   "status": "ok",
#   "accounts": 1,
#   "accounts_total": 1,
#   "accounts_cooling": 0,
#   "uptime": 123
# }
```

---

## 🎛️ 管理命令

### 使用管理脚本

```bash
# 给脚本添加执行权限
chmod +x manage.sh

# 查看所有命令
./manage.sh

# 常用命令
./manage.sh start      # 启动服务
./manage.sh stop       # 停止服务
./manage.sh restart    # 重启服务
./manage.sh status     # 查看状态
./manage.sh logs       # 查看日志
./manage.sh backup     # 备份数据库
./manage.sh update     # 更新并重启
```

### 直接使用 Docker Compose

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f

# 查看服务状态
docker-compose ps

# 进入容器
docker-compose exec notion-opus /bin/bash

# 重新构建镜像
docker-compose build --no-cache
```

---

## 🌐 Nginx 反向代理

如果你有自己的域名，可以使用 Nginx 提供 HTTPS 支持。

### 1. 安装 Nginx

```bash
sudo apt-get install -y nginx
```

### 2. 获取 SSL 证书（使用 Let's Encrypt）

```bash
# 安装 Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com
```

### 3. 配置 Nginx

创建配置文件 `/etc/nginx/sites-available/notion-ai`：

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 证书配置
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # 日志
    access_log /var/log/nginx/notion-ai-access.log;
    error_log /var/log/nginx/notion-ai-error.log;

    # 反向代理
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 支持流式输出
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        chunked_transfer_encoding on;
    }

    # WebSocket 支持（如果需要）
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

### 4. 启用配置

```bash
# 创建符号链接
sudo ln -s /etc/nginx/sites-available/notion-ai /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx
```

---

## 🔍 故障排查

### 服务无法启动

```bash
# 查看详细日志
docker-compose logs -f

# 检查容器状态
docker-compose ps

# 检查端口占用
sudo netstat -tlnp | grep 8000
```

### 数据库问题

```bash
# 检查数据库文件权限
ls -la data/conversations.db

# 修复权限
chmod 644 data/conversations.db

# 检查数据库完整性
sqlite3 data/conversations.db "PRAGMA integrity_check;"
```

### 内存不足

```bash
# 查看容器资源使用情况
docker stats

# 调整资源限制（编辑 docker-compose.yml）
# 修改 deploy.resources.limits.memory
```

### 网络连接问题

```bash
# 测试 Notion API 连接
docker-compose exec notion-opus curl -I https://www.notion.so

# 检查 DNS 解析
docker-compose exec notion-opus nslookup notion.so
```

---

## 🔒 安全建议

### 1. 设置 API Key

在 `.env` 文件中设置强密码：

```bash
# 生成随机字符串
openssl rand -hex 32

# 设置 API_KEY
API_KEY=your-random-string-here
```

### 2. 限制访问频率

编辑 `app/limiter.py`，调整速率限制：

```python
limiter.limit("10/minute")  # 每分钟最多 10 次请求
```

### 3. 定期备份数据

```bash
# 添加到 crontab
crontab -e

# 每天凌晨 2 点自动备份
0 2 * * * cd /home/user/notion-ai && ./manage.sh backup
```

### 4. 更新系统

```bash
# 定期更新系统
sudo apt-get update && sudo apt-get upgrade -y

# 定期更新 Docker 镜像
docker-compose pull
docker-compose up -d
```

### 5. 监控日志

```bash
# 设置日志轮转
sudo nano /etc/logrotate.d/notion-ai

# 添加以下内容
/home/user/notion-ai/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

---

## 📞 获取帮助

如果遇到问题：

1. 查看 [GitHub Issues](https://github.com/your-repo/notion-ai/issues)
2. 查看项目日志: `docker-compose logs -f`
3. 检查服务状态: `curl http://localhost:8000/health`

---

## 📝 更新日志

### v1.0.0 (2025-03-06)
- 初始部署文档
- 添加 Docker 支持
- 添加自动化部署脚本
- 添加 Nginx 反向代理配置
