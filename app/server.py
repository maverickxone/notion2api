import time
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
from app.config import ACCOUNTS, API_KEY
from app.account_pool import AccountPool
from app.conversation import ConversationManager
from app.api.chat import router as chat_router
from app.api.models import router as models_router
from app.logger import logger
from app.limiter import limiter

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化状态
    app.state.account_pool = AccountPool(ACCOUNTS)
    app.state.conversation_manager = ConversationManager()
    app.state.start_time = time.time()
    logger.info("Service starting up", extra={"request_info": {"event": "startup", "accounts": len(ACCOUNTS)}})
    yield
    # 关闭时清理
    logger.info("Service shutting down", extra={"request_info": {"event": "shutdown"}})

app = FastAPI(
    title="Notion Opus API",
    description="A FastAPI wrapper providing an OpenAI-compatible interface for Notion's Claude Opus backend.",
    version="1.0.0",
    lifespan=lifespan
)

# 允许跨域（配合本地前端）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注入 Limiter
app.state.limiter = limiter

# 自定义 429 速率限制响应
def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "请求过于频繁，请稍后再试"}
    )
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled application exception",
        exc_info=True,
        extra={
            "request_info": {
                "event": "unhandled_exception",
                "method": request.method,
                "path": request.url.path,
            }
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "Internal server error",
                "type": "server_error",
            }
        },
    )

# 结构化日志中间件
@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    start_time = time.time()
    
    # 跳过 /health 的高频日志打印，避免刷屏
    is_health = request.url.path == "/health"
    
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        status_code = 500
        logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
        raise
    finally:
        process_time = time.time() - start_time
        client_ip = request.client.host if request.client else "unknown"
        
        if not is_health:
            log_level = logger.error if status_code >= 400 else logger.info
            log_level(
                "Request processed",
                extra={
                    "request_info": {
                        "method": request.method,
                        "path": request.url.path,
                        "ip": client_ip,
                        "status_code": status_code,
                        "duration_ms": round(process_time * 1000, 2)
                    }
                }
            )
            
    return response

# 简易 API Key 鉴权中间件
@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    # 如果环境配置中未设置 API_KEY，则全局不验证
    if API_KEY:
        # 跳过 OPTIONS 请求和非受保护的静态路由（如果以后有的话）
        if request.url.path.startswith("/v1") and request.method != "OPTIONS":
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer ") or auth_header.split(" ")[1] != API_KEY:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "message": "Error: API KEY doesn't match.",
                            "type": "invalid_request_error",
                            "code": "invalid_api_key"
                        }
                    }
                )
    return await call_next(request)

# 挂载路由，前缀统一为 /v1
app.include_router(chat_router, prefix="/v1")
app.include_router(models_router, prefix="/v1")

# 挂载健康检查
@app.get("/health", tags=["system"])
def health_check(request: Request):
    uptime = time.time() - request.app.state.start_time
    pool = request.app.state.account_pool
    status = pool.get_status_summary()
    return {
        "status": "ok",
        "accounts": status["active"],
        "accounts_total": status["total"],
        "accounts_cooling": status["cooling"],
        "uptime": int(uptime)
    }

# 挂载静态前端到根目录
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
