"""钉钉推送工具 - 用于 Agent 调用。"""

import os
from langchain_core.tools import tool
from app.alert.dingtalk import DingTalkNotifier
from app.log_utils import get_logger

logger = get_logger("dingtalk_tools")


@tool
async def dingtalk_send(message: str) -> str:
    """发送消息到钉钉 Webhook。

    Args:
        message: 要发送的消息内容（支持 Markdown 格式）

    Returns:
        发送结果状态
    """
    webhook_url = os.getenv("DINGTALK_WEBHOOK")
    secret = os.getenv("DINGTALK_SECRET")

    if not webhook_url:
        logger.warning("dingtalk_webhook_not_configured")
        return "钉钉 Webhook 未配置，消息未发送"

    notifier = DingTalkNotifier(webhook_url, secret)

    try:
        # 发送 Markdown 消息
        title = message.split('\n')[0][:50]  # 第一行作为标题
        success = await notifier.send_markdown(title, message)

        if success:
            logger.info("dingtalk_message_sent", message_preview=message[:100])
            return "消息已成功发送到钉钉"
        else:
            return "消息发送失败，请检查 Webhook 配置"

    except Exception as e:
        logger.error("dingtalk_send_error", error=str(e))
        return f"发送失败: {str(e)}"
    finally:
        await notifier.close()


__all__ = ["dingtalk_send"]