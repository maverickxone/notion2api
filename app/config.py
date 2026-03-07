import os
import json
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量（override=True 确保 .env 优先于系统环境变量）
load_dotenv(override=True)

REQUIRED_ACCOUNT_FIELDS = {"token_v2", "space_id", "user_id"}

def load_accounts():
    """从环境变量中加载 Notion 账号配置列表"""
    accounts_json = os.getenv("NOTION_ACCOUNTS")
    if not accounts_json:
        raise ValueError("环境变量 NOTION_ACCOUNTS 未设置或为空，请检查 .env 文件。")
    
    try:
        accounts = json.loads(accounts_json)
        if not isinstance(accounts, list) or len(accounts) == 0:
            raise ValueError("NOTION_ACCOUNTS 格式不正确，应提供非空的 JSON 数组。")
        for idx, account in enumerate(accounts):
            if not isinstance(account, dict):
                raise ValueError(f"NOTION_ACCOUNTS[{idx}] 必须是对象。")
            missing = sorted(field for field in REQUIRED_ACCOUNT_FIELDS if not account.get(field))
            if missing:
                raise ValueError(f"NOTION_ACCOUNTS[{idx}] 缺少必要字段: {', '.join(missing)}")
        return accounts
    except json.JSONDecodeError as e:
        raise ValueError(f"解析 NOTION_ACCOUNTS 失败: {e}")

# 全局配置对象
ACCOUNTS = load_accounts()

# FastAPI 服务配置
API_KEY = os.getenv("API_KEY", "")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

def get_default_account():
    """获取默认账号（列表中的第一个账号）"""
    return ACCOUNTS[0]
