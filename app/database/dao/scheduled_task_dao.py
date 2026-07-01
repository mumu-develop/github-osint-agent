"""定时任务 DAO - Agent 生成的定时任务数据访问层。"""

import json
import aiomysql
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.database.base import get_db_pool, parse_json_field, to_json_str, get_logger
from app.models import ScheduledTask, ScheduledTaskExecution

logger = get_logger("scheduled_task_dao")


class ScheduledTaskDAO:
    """定时任务 DAO。"""

    @staticmethod
    async def create(task_data: Dict[str, Any]) -> int:
        """创建定时任务。

        Args:
            task_data: 任务数据字典

        Returns:
            任务 ID
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO scheduled_task (
                        name, description, target_type, target_name,
                        prompt, cron_expression, dimensions, alert_threshold,
                        alert_channels, alert_channel_ids,
                        status, enabled, created_by, conversation_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    task_data.get("name"),
                    task_data.get("description"),
                    task_data.get("target_type"),
                    task_data.get("target_name"),
                    task_data.get("prompt"),
                    task_data.get("cron_expression"),
                    to_json_str(task_data.get("dimensions")),
                    task_data.get("alert_threshold", "HIGH"),
                    to_json_str(task_data.get("alert_channels")),
                    to_json_str(task_data.get("alert_channel_ids")),
                    task_data.get("status", "active"),
                    task_data.get("enabled", True),
                    task_data.get("created_by", "agent"),
                    task_data.get("conversation_id"),
                ))
                task_id = cur.lastrowid
                logger.info("scheduled_task_created", task_id=task_id, name=task_data.get("name"))
                return task_id

    @staticmethod
    async def get_by_id(task_id: int) -> Optional[ScheduledTask]:
        """根据 ID 获取任务。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM scheduled_task WHERE id = %s
                """, (task_id,))
                row = await cur.fetchone()
                if row:
                    return ScheduledTask(
                        id=row["id"],
                        name=row["name"],
                        description=row["description"],
                        target_type=row["target_type"],
                        target_name=row["target_name"],
                        prompt=row["prompt"],
                        cron_expression=row["cron_expression"],
                        dimensions=parse_json_field(row["dimensions"]),
                        alert_threshold=row["alert_threshold"],
                        alert_channels=parse_json_field(row["alert_channels"]),
                        alert_channel_ids=parse_json_field(row["alert_channel_ids"]),
                        status=row["status"],
                        enabled=row["enabled"],
                        created_by=row["created_by"],
                        conversation_id=row["conversation_id"],
                        last_run_id=row["last_run_id"],
                        last_run_at=row["last_run_at"],
                        last_run_status=row["last_run_status"],
                        next_run_at=row["next_run_at"],
                        run_count=row["run_count"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                return None

    @staticmethod
    async def list_active() -> List[ScheduledTask]:
        """获取所有活跃的定时任务。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM scheduled_task
                    WHERE status = 'active' AND enabled = TRUE
                    ORDER BY next_run_at ASC
                """)
                rows = await cur.fetchall()
                return [
                    ScheduledTask(
                        id=row["id"],
                        name=row["name"],
                        description=row["description"],
                        target_type=row["target_type"],
                        target_name=row["target_name"],
                        prompt=row["prompt"],
                        cron_expression=row["cron_expression"],
                        dimensions=parse_json_field(row["dimensions"]),
                        alert_threshold=row["alert_threshold"],
                        status=row["status"],
                        enabled=row["enabled"],
                        created_by=row["created_by"],
                        conversation_id=row["conversation_id"],
                        last_run_id=row["last_run_id"],
                        last_run_at=row["last_run_at"],
                        last_run_status=row["last_run_status"],
                        next_run_at=row["next_run_at"],
                        run_count=row["run_count"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    for row in rows
                ]

    @staticmethod
    async def list_all(
        target_type: Optional[str] = None,
        target_name: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[ScheduledTask]:
        """获取任务列表（支持筛选）。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                where_clauses = []
                params = []

                if target_type:
                    where_clauses.append("target_type = %s")
                    params.append(target_type)
                if target_name:
                    where_clauses.append("target_name = %s")
                    params.append(target_name)
                if status:
                    where_clauses.append("status = %s")
                    params.append(status)

                where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

                await cur.execute(f"""
                    SELECT * FROM scheduled_task {where_sql}
                    ORDER BY created_at DESC
                """, params)
                rows = await cur.fetchall()
                return [
                    ScheduledTask(
                        id=row["id"],
                        name=row["name"],
                        description=row["description"],
                        target_type=row["target_type"],
                        target_name=row["target_name"],
                        prompt=row["prompt"],
                        cron_expression=row["cron_expression"],
                        dimensions=parse_json_field(row["dimensions"]),
                        alert_threshold=row["alert_threshold"],
                        status=row["status"],
                        enabled=row["enabled"],
                        created_by=row["created_by"],
                        conversation_id=row["conversation_id"],
                        last_run_id=row["last_run_id"],
                        last_run_at=row["last_run_at"],
                        last_run_status=row["last_run_status"],
                        next_run_at=row["next_run_at"],
                        run_count=row["run_count"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    for row in rows
                ]

    @staticmethod
    async def update(task_id: int, updates: Dict[str, Any]) -> bool:
        """更新任务。"""
        if not updates:
            return False

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                set_clauses = []
                params = []

                json_fields = ["dimensions", "alert_channels", "alert_channel_ids"]

                for key, value in updates.items():
                    if key in json_fields:
                        set_clauses.append(f"{key} = %s")
                        params.append(to_json_str(value))
                    elif key in ["next_run_at", "last_run_at"]:
                        set_clauses.append(f"{key} = %s")
                        params.append(value)
                    else:
                        set_clauses.append(f"{key} = %s")
                        params.append(value)

                params.append(task_id)
                await cur.execute(f"""
                    UPDATE scheduled_task SET {', '.join(set_clauses)} WHERE id = %s
                """, params)
                logger.info("scheduled_task_updated", task_id=task_id, updates=list(updates.keys()))
                return cur.rowcount > 0

    @staticmethod
    async def update_run_start(task_id: int, run_id: str, started_at: datetime) -> bool:
        """更新任务开始执行状态。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE scheduled_task
                    SET last_run_id = %s,
                        last_run_at = %s,
                        last_run_status = 'running',
                        run_count = run_count + 1,
                        next_run_at = NULL
                    WHERE id = %s
                """, (run_id, started_at, task_id))
                return cur.rowcount > 0

    @staticmethod
    async def update_run_complete(task_id: int, status: str, error: str = None) -> bool:
        """更新任务执行完成状态。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE scheduled_task
                    SET last_run_status = %s,
                        next_run_at = NULL
                    WHERE id = %s
                """, (status, task_id))
                return cur.rowcount > 0

    @staticmethod
    async def delete(task_id: int) -> bool:
        """删除任务。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM scheduled_task WHERE id = %s", (task_id,))
                logger.info("scheduled_task_deleted", task_id=task_id)
                return cur.rowcount > 0

    @staticmethod
    async def pause(task_id: int) -> bool:
        """暂停任务。

        同时清除 next_run_at，避免调度器再次调度。
        """
        return await ScheduledTaskDAO.update(task_id, {
            "status": "paused",
            "next_run_at": None  # 清除下次执行时间
        })

    @staticmethod
    async def resume(task_id: int) -> bool:
        """恢复任务。

        恢复后调度器会在下次 tick 时重新计算 next_run_at。
        """
        return await ScheduledTaskDAO.update(task_id, {"status": "active"})


class ScheduledTaskExecutionDAO:
    """定时任务执行记录 DAO。"""

    @staticmethod
    async def create(execution_data: Dict[str, Any]) -> int:
        """创建执行记录。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO scheduled_task_execution (
                        scheduled_task_id, run_id, status, started_at,
                        steps, total_findings, high_severity_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    execution_data.get("scheduled_task_id"),
                    execution_data.get("run_id"),
                    execution_data.get("status", "running"),
                    execution_data.get("started_at"),
                    to_json_str(execution_data.get("steps")),
                    execution_data.get("total_findings", 0),
                    execution_data.get("high_severity_count", 0),
                ))
                return cur.lastrowid

    @staticmethod
    async def update(execution_id: int, updates: Dict[str, Any]) -> bool:
        """更新执行记录。"""
        if not updates:
            return False

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                set_clauses = []
                params = []

                json_fields = ["steps", "tool_calls"]

                for key, value in updates.items():
                    if key in json_fields:
                        set_clauses.append(f"{key} = %s")
                        params.append(to_json_str(value))
                    else:
                        set_clauses.append(f"{key} = %s")
                        params.append(value)

                params.append(execution_id)
                await cur.execute(f"""
                    UPDATE scheduled_task_execution SET {', '.join(set_clauses)} WHERE id = %s
                """, params)
                return cur.rowcount > 0

    @staticmethod
    async def update_step(run_id: str, steps: List[Dict]) -> bool:
        """更新执行步骤。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE scheduled_task_execution
                    SET steps = %s
                    WHERE run_id = %s
                """, (to_json_str(steps), run_id))
                return cur.rowcount > 0

    @staticmethod
    async def complete(run_id: str, status: str, total_findings: int = 0,
                       high_severity_count: int = 0, error: str = None,
                       error_detail: str = None, tool_calls: List[Dict] = None,
                       steps: List[Dict] = None,
                       agent_output: str = None, execution_log: str = None) -> bool:
        """标记执行完成。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                completed_at = datetime.now()

                # 限制数据长度，避免超出 TEXT 字段限制（约 65KB）
                MAX_TEXT_LENGTH = 60000

                # 截断 execution_log
                if execution_log and len(execution_log) > MAX_TEXT_LENGTH:
                    execution_log = execution_log[:MAX_TEXT_LENGTH] + "\n...[日志过长已截断]"

                # 截断 error_detail
                if error_detail and len(error_detail) > MAX_TEXT_LENGTH:
                    error_detail = error_detail[:MAX_TEXT_LENGTH] + "\n...[堆栈过长已截断]"

                # 截断 agent_output
                if agent_output and len(agent_output) > MAX_TEXT_LENGTH:
                    agent_output = agent_output[:MAX_TEXT_LENGTH] + "\n...[输出过长已截断]"

                # 截断 steps（保留最近的步骤）
                if steps and len(json.dumps(steps, default=str)) > MAX_TEXT_LENGTH:
                    # 保留最后 50 个步骤
                    steps = steps[-50:] if len(steps) > 50 else steps
                    steps_str = json.dumps(steps, default=str)
                    if len(steps_str) > MAX_TEXT_LENGTH:
                        # 进一步截断每个步骤的 message
                        steps = [{"name": s.get("name", "")[:50],
                                  "status": s.get("status", ""),
                                  "message": str(s.get("message", ""))[:200],
                                  "timestamp": s.get("timestamp", "")}
                                 for s in steps[-30:]]

                # 截断 tool_calls
                if tool_calls and len(json.dumps(tool_calls, default=str)) > MAX_TEXT_LENGTH:
                    tool_calls = tool_calls[-20:] if len(tool_calls) > 20 else tool_calls
                    tool_calls_str = json.dumps(tool_calls, default=str)
                    if len(tool_calls_str) > MAX_TEXT_LENGTH:
                        tool_calls = [{"tool": t.get("tool", "")[:50],
                                       "status": t.get("status", ""),
                                       "output": str(t.get("output", ""))[:500],
                                       "timestamp": t.get("timestamp", "")}
                                      for t in tool_calls[-10:]]

                await cur.execute("""
                    UPDATE scheduled_task_execution
                    SET status = %s,
                        completed_at = %s,
                        total_findings = %s,
                        high_severity_count = %s,
                        error_message = %s,
                        error_detail = %s,
                        tool_calls = %s,
                        steps = %s,
                        agent_output = %s,
                        execution_log = %s,
                        duration_seconds = TIMESTAMPDIFF(SECOND, started_at, %s)
                    WHERE run_id = %s
                """, (status, completed_at, total_findings, high_severity_count,
                      error, error_detail, to_json_str(tool_calls), to_json_str(steps),
                      agent_output, execution_log, completed_at, run_id))
                return cur.rowcount > 0

    @staticmethod
    async def get_by_run_id(run_id: str) -> Optional[ScheduledTaskExecution]:
        """根据 run_id 获取执行记录。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM scheduled_task_execution WHERE run_id = %s
                """, (run_id,))
                row = await cur.fetchone()
                if row:
                    return ScheduledTaskExecution(
                        id=row["id"],
                        scheduled_task_id=row["scheduled_task_id"],
                        run_id=row["run_id"],
                        status=row["status"],
                        started_at=row["started_at"],
                        completed_at=row["completed_at"],
                        error_message=row["error_message"],
                        error_detail=row.get("error_detail"),
                        steps=parse_json_field(row["steps"]),
                        tool_calls=parse_json_field(row.get("tool_calls")),
                        agent_output=row.get("agent_output"),
                        execution_log=row.get("execution_log"),
                        total_findings=row["total_findings"],
                        high_severity_count=row["high_severity_count"],
                        duration_seconds=row["duration_seconds"],
                        created_at=row["created_at"],
                    )
                return None

    @staticmethod
    async def list_by_task(task_id: int, limit: int = 20) -> List[ScheduledTaskExecution]:
        """获取任务的执行历史。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM scheduled_task_execution
                    WHERE scheduled_task_id = %s
                    ORDER BY started_at DESC
                    LIMIT %s
                """, (task_id, limit))
                rows = await cur.fetchall()
                return [
                    ScheduledTaskExecution(
                        id=row["id"],
                        scheduled_task_id=row["scheduled_task_id"],
                        run_id=row["run_id"],
                        status=row["status"],
                        started_at=row["started_at"],
                        completed_at=row["completed_at"],
                        error_message=row["error_message"],
                        error_detail=row.get("error_detail"),
                        steps=parse_json_field(row["steps"]),
                        tool_calls=parse_json_field(row.get("tool_calls")),
                        agent_output=row.get("agent_output"),
                        execution_log=row.get("execution_log"),
                        total_findings=row["total_findings"],
                        high_severity_count=row["high_severity_count"],
                        duration_seconds=row["duration_seconds"],
                        created_at=row["created_at"],
                    )
                    for row in rows
                ]