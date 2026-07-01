"""告警渠道管理 API 路由。"""

import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional, List

from app.database import AlertChannelDAO, init_business_tables
from app.log_utils import get_logger

logger = get_logger("channel_routes")

router = APIRouter(prefix="/api/channel", tags=["channel"])


# ==================== 渠道管理 ====================

@router.get("/list")
async def list_channels(channel_type: Optional[str] = None) -> Dict[str, Any]:
    """列出告警渠道。"""
    await init_business_tables()

    channels = await AlertChannelDAO.list_all(channel_type=channel_type)

    return {
        "code": 0,
        "data": {
            "count": len(channels),
            "channels": [
                {
                    "id": c.id,
                    "name": c.name,
                    "channel_type": c.channel_type,
                    "webhook_url": c.webhook_url,
                    "secret": c.secret,
                    "description": c.description,
                    "enabled": c.enabled,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None
                }
                for c in channels
            ]
        }
    }


@router.get("/enabled")
async def list_enabled_channels() -> Dict[str, Any]:
    """获取所有启用的渠道（用于任务绑定选择）。"""
    await init_business_tables()

    channels = await AlertChannelDAO.list_enabled()

    return {
        "code": 0,
        "data": {
            "count": len(channels),
            "channels": [
                {
                    "id": c.id,
                    "name": c.name,
                    "channel_type": c.channel_type,
                    "description": c.description,
                }
                for c in channels
            ]
        }
    }


@router.post("/create")
async def create_channel(channel_data: Dict[str, Any]) -> Dict[str, Any]:
    """创建告警渠道。

    channel_data 格式:
    {
        "name": "钉钉-安全组",
        "channel_type": "dingtalk",
        "webhook_url": "https://oapi.dingtalk.com/...",
        "secret": "SECxxx",
        "description": "安全组专用钉钉机器人",
        "enabled": true
    }
    """
    await init_business_tables()

    # 校验必填字段
    if not channel_data.get("name"):
        raise HTTPException(status_code=400, detail="渠道名称不能为空")
    if not channel_data.get("channel_type"):
        raise HTTPException(status_code=400, detail="渠道类型不能为空")
    if not channel_data.get("webhook_url"):
        raise HTTPException(status_code=400, detail="Webhook URL 不能为空")

    # 校验渠道类型
    valid_types = ["dingtalk", "feishu", "slack", "discord", "email", "webhook"]
    if channel_data.get("channel_type") not in valid_types:
        raise HTTPException(status_code=400, detail=f"渠道类型必须是: {', '.join(valid_types)}")

    channel_id = await AlertChannelDAO.create(channel_data)

    logger.info("channel_created", channel_id=channel_id, name=channel_data.get("name"))

    return {
        "code": 0,
        "data": {
            "message": "告警渠道创建成功",
            "channel_id": channel_id,
            "name": channel_data.get("name")
        }
    }


@router.get("/{channel_id}")
async def get_channel(channel_id: int) -> Dict[str, Any]:
    """获取渠道详情。"""
    await init_business_tables()

    channel = await AlertChannelDAO.get_by_id(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"告警渠道 {channel_id} 不存在")

    return {
        "code": 0,
        "data": {
            "id": channel.id,
            "name": channel.name,
            "channel_type": channel.channel_type,
            "webhook_url": channel.webhook_url,
            "secret": channel.secret,
            "description": channel.description,
            "enabled": channel.enabled,
            "created_at": channel.created_at.isoformat() if channel.created_at else None,
            "updated_at": channel.updated_at.isoformat() if channel.updated_at else None
        }
    }


@router.put("/{channel_id}")
async def update_channel(channel_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    """更新渠道配置。"""
    await init_business_tables()

    channel = await AlertChannelDAO.get_by_id(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"告警渠道 {channel_id} 不存在")

    # 校验渠道类型（如果更新）
    if "channel_type" in updates:
        valid_types = ["dingtalk", "feishu", "slack", "discord", "email", "webhook"]
        if updates["channel_type"] not in valid_types:
            raise HTTPException(status_code=400, detail=f"渠道类型必须是: {', '.join(valid_types)}")

    success = await AlertChannelDAO.update(channel_id, updates)
    if not success:
        raise HTTPException(status_code=500, detail="更新失败")

    logger.info("channel_updated", channel_id=channel_id, updates=list(updates.keys()))

    return {
        "code": 0,
        "data": {
            "message": "告警渠道配置已更新",
            "channel_id": channel_id
        }
    }


@router.delete("/{channel_id}")
async def delete_channel(channel_id: int) -> Dict[str, Any]:
    """删除渠道。"""
    await init_business_tables()

    success = await AlertChannelDAO.delete(channel_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"告警渠道 {channel_id} 不存在")

    logger.info("channel_deleted", channel_id=channel_id)

    return {
        "code": 0,
        "data": {"message": f"告警渠道 {channel_id} 已删除"}
    }


@router.post("/{channel_id}/enable")
async def enable_channel(channel_id: int) -> Dict[str, Any]:
    """启用渠道。"""
    await init_business_tables()

    success = await AlertChannelDAO.enable(channel_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"告警渠道 {channel_id} 不存在")

    return {
        "code": 0,
        "data": {"message": f"告警渠道 {channel_id} 已启用", "enabled": True}
    }


@router.post("/{channel_id}/disable")
async def disable_channel(channel_id: int) -> Dict[str, Any]:
    """禁用渠道。"""
    await init_business_tables()

    success = await AlertChannelDAO.disable(channel_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"告警渠道 {channel_id} 不存在")

    return {
        "code": 0,
        "data": {"message": f"告警渠道 {channel_id} 已禁用", "enabled": False}
    }


@router.post("/{channel_id}/test")
async def test_channel(channel_id: int) -> Dict[str, Any]:
    """测试渠道（发送测试消息）。"""
    await init_business_tables()

    channel = await AlertChannelDAO.get_by_id(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"告警渠道 {channel_id} 不存在")

    # 根据渠道类型发送测试消息
    try:
        if channel.channel_type == "dingtalk":
            from app.alert.dingtalk import DingTalkNotifier
            notifier = DingTalkNotifier(webhook_url=channel.webhook_url, secret=channel.secret)
            success = await notifier.send_markdown(
                "测试消息",
                f"## 测试消息\n\n告警渠道 **{channel.name}** 测试成功\n\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await notifier.close()
            if success:
                return {"code": 0, "data": {"message": "测试消息已发送到钉钉"}}
            else:
                return {"code": 1, "data": {"message": "发送失败，请检查 Webhook 配置"}}

        elif channel.channel_type == "feishu":
            from app.alert.feishu import FeishuNotifier
            notifier = FeishuNotifier(webhook_url=channel.webhook_url)
            success = await notifier.send_text(
                f"测试消息: 告警渠道 {channel.name} 测试成功\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await notifier.close()
            if success:
                return {"code": 0, "data": {"message": "测试消息已发送到飞书"}}
            else:
                return {"code": 1, "data": {"message": "发送失败，请检查 Webhook 配置"}}

        elif channel.channel_type == "slack":
            from app.alert.slack import SlackNotifier
            notifier = SlackNotifier(webhook=channel.webhook_url)
            success = await notifier.send(
                "测试消息",
                f"告警渠道 **{channel.name}** 测试成功\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "INFO"
            )
            await notifier.close()
            if success:
                return {"code": 0, "data": {"message": "测试消息已发送到 Slack"}}
            else:
                return {"code": 1, "data": {"message": "发送失败，请检查 Webhook 配置"}}

        elif channel.channel_type == "discord":
            from app.alert.discord import DiscordNotifier
            notifier = DiscordNotifier(webhook=channel.webhook_url)
            success = await notifier.send(
                "测试消息",
                f"告警渠道 **{channel.name}** 测试成功\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "INFO"
            )
            await notifier.close()
            if success:
                return {"code": 0, "data": {"message": "测试消息已发送到 Discord"}}
            else:
                return {"code": 1, "data": {"message": "发送失败，请检查 Webhook 配置"}}

        elif channel.channel_type == "email":
            # Email 需要额外配置 SMTP，这里简化处理
            return {"code": 0, "data": {"message": "Email 渠道配置已保存，请通过实际任务验证"}}

        else:
            # webhook 类型，简单发送 POST 请求
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(channel.webhook_url, json={
                    "message": f"测试消息: 告警渠道 {channel.name} 测试成功",
                    "time": datetime.now().isoformat()
                }) as resp:
                    if resp.status == 200:
                        return {"code": 0, "data": {"message": "测试消息已发送"}}
                    else:
                        return {"code": 1, "data": {"message": f"发送失败，状态码: {resp.status}"}}

    except Exception as e:
        logger.error("channel_test_failed", channel_id=channel_id, error=str(e))
        return {"code": 1, "data": {"message": f"测试失败: {str(e)}"}}


# ==================== 任务绑定渠道 ====================

@router.put("/bind-task/{task_id}")
async def bind_channels_to_task(task_id: int, channel_ids: Dict[str, List[int]]) -> Dict[str, Any]:
    """绑定渠道到定时任务。

    channel_ids 格式: {"channel_ids": [1, 2, 3]}
    """
    await init_business_tables()

    from app.database import ScheduledTaskDAO

    task = await ScheduledTaskDAO.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")

    ids = channel_ids.get("channel_ids", [])
    if not ids:
        # 清空绑定
        success = await ScheduledTaskDAO.update(task_id, {"alert_channel_ids": []})
        return {"code": 0, "data": {"message": "已清除渠道绑定", "task_id": task_id, "channel_ids": []}}

    # 校验渠道是否存在
    for channel_id in ids:
        channel = await AlertChannelDAO.get_by_id(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail=f"告警渠道 {channel_id} 不存在")
        if not channel.enabled:
            raise HTTPException(status_code=400, detail=f"告警渠道 {channel_id} 已禁用")

    success = await ScheduledTaskDAO.update(task_id, {"alert_channel_ids": ids})
    if not success:
        raise HTTPException(status_code=500, detail="绑定失败")

    logger.info("channels_bound_to_task", task_id=task_id, channel_ids=ids)

    return {
        "code": 0,
        "data": {
            "message": "渠道绑定成功",
            "task_id": task_id,
            "channel_ids": ids
        }
    }