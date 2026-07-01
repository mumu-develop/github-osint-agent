from langchain_core.tools import tool
from app.tools.report import report_tools


@tool
async def save_memory(key: str, value: str) -> str:
    """保存一条长期记忆，供未来所有会话使用"""
    return f"记忆已保存: {key}"


@tool
async def get_memory(key: str) -> str:
    """检索一条长期记忆"""
    return f"记忆内容待检索"


# 导出分组（包含记忆工具和报告工具）
common_tools = [save_memory, get_memory] + report_tools