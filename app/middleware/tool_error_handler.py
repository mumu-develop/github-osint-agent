"""工具异常处理中间件。

捕获工具执行中的异常，返回包含错误信息的 ToolMessage，
而不是让整个流程崩溃。
"""

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from typing import Any


class ToolErrorHandlerMiddleware(AgentMiddleware):
    """工具异常处理中间件。

    捕获所有工具执行异常，返回包含错误信息的 ToolMessage。
    Agent 可以根据错误信息决定下一步操作（跳过、记录、重试等）。
    """

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Any,
    ) -> ToolMessage:
        """同步版本：捕获异常并返回错误 ToolMessage。"""
        try:
            return handler(request)
        except Exception as e:
            return ToolMessage(
                content=f"工具执行错误: {type(e).__name__}: {str(e)}",
                name=request.tool_call["name"],
                tool_call_id=request.tool_call["id"],
                status="error",
            )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Any,
    ) -> ToolMessage:
        """异步版本：捕获异常并返回错误 ToolMessage。"""
        try:
            return await handler(request)
        except Exception as e:
            return ToolMessage(
                content=f"工具执行错误: {type(e).__name__}: {str(e)}",
                name=request.tool_call["name"],
                tool_call_id=request.tool_call["id"],
                status="error",
            )