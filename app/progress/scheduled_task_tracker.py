"""定时任务进度追踪器 - SSE 进度推送。"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from app.log_utils import get_logger

logger = get_logger("scheduled_task_tracker")

# 全局进度队列（按 task_id 分）
_scheduled_task_queues: Dict[int, asyncio.Queue] = {}


def get_scheduled_task_queue(task_id: int) -> asyncio.Queue:
    """获取指定任务的进度队列。"""
    if task_id not in _scheduled_task_queues:
        _scheduled_task_queues[task_id] = asyncio.Queue()
    return _scheduled_task_queues[task_id]


def remove_scheduled_task_queue(task_id: int):
    """移除进度队列。"""
    if task_id in _scheduled_task_queues:
        del _scheduled_task_queues[task_id]


class ScheduledTaskProgressTracker:
    """定时任务进度追踪器 - 推送 SSE。"""

    def __init__(self, task_id: int, run_id: str):
        self.task_id = task_id
        self.run_id = run_id
        self.queue = get_scheduled_task_queue(task_id)
        self.steps: List[Dict] = []
        self._current_tool: Optional[str] = None

    async def _push(self, event_type: str, data: Dict[str, Any]):
        """推送 SSE 事件。"""
        event = {
            "type": event_type,
            "data": {
                "task_id": self.task_id,
                "run_id": self.run_id,
                "timestamp": datetime.now().isoformat(),
                **data
            }
        }
        await self.queue.put(event)

        # 同时存入数据库（用户离线时可查看）
        from app.database import ScheduledTaskExecutionDAO
        await ScheduledTaskExecutionDAO.update_step(self.run_id, self.steps)

        logger.debug("sse_event_pushed", task_id=self.task_id, event_type=event_type)

    async def start(self):
        """开始执行。"""
        self.steps.append({
            "name": "init",
            "status": "done",
            "time": datetime.now().isoformat()
        })
        await self._push("start", {
            "status": "running",
            "message": "任务开始执行"
        })
        logger.info("task_start", task_id=self.task_id, run_id=self.run_id)

    async def tool_start(self, tool_name: str):
        """工具开始调用。"""
        self._current_tool = tool_name

        # 工具名称转换
        tool_display = {
            "batch_cve_check": "正在扫描 CVE 漏洞...",
            "batch_secret_scan": "正在扫描敏感信息...",
            "batch_license_check": "正在检查许可证...",
            "batch_community_check": "正在检查社区健康度...",
            "dingtalk_send": "正在推送钉钉...",
        }

        message = tool_display.get(tool_name, f"正在执行 {tool_name}...")

        self.steps.append({
            "tool": tool_name,
            "status": "running",
            "message": message,
            "time": datetime.now().isoformat()
        })

        await self._push("tool_start", {
            "tool": tool_name,
            "message": message
        })

    async def tool_end(self, tool_name: str, output: Any):
        """工具调用结束。"""
        self._current_tool = None

        # 提取结果摘要
        result_summary = self._summarize_output(tool_name, output)

        # 更新步骤
        for step in self.steps:
            if step.get("tool") == tool_name and step.get("status") == "running":
                step["status"] = "done"
                step["result"] = result_summary
                step["end_time"] = datetime.now().isoformat()
                break

        await self._push("tool_end", {
            "tool": tool_name,
            "message": f"{tool_name} 完成",
            "result": result_summary
        })

    async def repo_start(self, repo_full_name: str, dimension: str = None):
        """仓库开始扫描。"""
        await self._push("repo_start", {
            "repo": repo_full_name,
            "dimension": dimension,
            "status": "scanning",
            "message": f"正在扫描 {repo_full_name}..."
        })

    async def repo_done(self, repo_full_name: str, dimension: str = None, findings_count: int = 0):
        """仓库扫描完成。"""
        await self._push("repo_done", {
            "repo": repo_full_name,
            "dimension": dimension,
            "status": "done",
            "findings_count": findings_count,
            "message": f"{repo_full_name} 扫描完成，发现 {findings_count} 个问题"
        })

    async def complete(self, result: Dict = None):
        """任务完成。"""
        self.steps.append({
            "name": "done",
            "status": "done",
            "result": result,
            "time": datetime.now().isoformat()
        })

        await self._push("done", {
            "status": "completed",
            "message": "任务执行完成",
            "steps": self.steps,
            "result": result
        })

        logger.info("task_done", task_id=self.task_id, run_id=self.run_id)

    async def fail(self, error: str):
        """任务失败。"""
        self.steps.append({
            "name": "failed",
            "status": "failed",
            "error": error,
            "time": datetime.now().isoformat()
        })

        await self._push("error", {
            "status": "failed",
            "error": error,
            "message": f"任务执行失败: {error}"
        })

        logger.error("task_failed", task_id=self.task_id, run_id=self.run_id, error=error)

    def _summarize_output(self, tool_name: str, output: Any) -> Dict:
        """提取工具输出摘要。"""
        if isinstance(output, dict):
            return {
                "findings_count": output.get("findings_count", 0),
                "high_severity_count": output.get("high_severity_count", 0),
                "repos_scanned": output.get("repos_scanned", 0)
            }
        elif isinstance(output, str):
            return {"output_preview": output[:100] if len(output) > 100 else output}
        return {}