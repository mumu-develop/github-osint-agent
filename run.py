import os
import uvicorn
from dotenv import load_dotenv

# 最先加载环境变量和日志配置
load_dotenv()

# 初始化统一日志配置（必须在所有其他模块导入前）
from app.log_utils import get_logger, LOG_LEVEL

logger = get_logger("run")
logger.info("application_starting")

if __name__ == "__main__":
    logger.info("server_starting", host="127.0.0.1", port=8000)
    # 使用 app.run() 方式避免 PyCharm debugger 的 asyncio 兼容性问题
    from app.main import app
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level=LOG_LEVEL.lower()
    )