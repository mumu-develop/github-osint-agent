"""数据库表结构初始化。

包含:
- 表创建语句
- 字段迁移语句
- 索引优化语句
"""

import aiomysql
from app.database.base import get_db_pool, get_logger

logger = get_logger("database_tables")


async def init_business_tables():
    """初始化业务数据表。"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # ==================== 告警渠道配置表 ====================
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS alert_channel (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL COMMENT '渠道名称（用户自定义）',
                    channel_type VARCHAR(20) NOT NULL COMMENT '渠道类型: dingtalk|feishu|webhook',
                    webhook_url VARCHAR(500) NOT NULL COMMENT 'Webhook URL',
                    secret VARCHAR(200) COMMENT '签名密钥（钉钉可选）',
                    description TEXT COMMENT '渠道描述',
                    enabled BOOLEAN DEFAULT TRUE COMMENT '是否启用',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_channel_type (channel_type),
                    INDEX idx_enabled (enabled)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警渠道配置'
            """)
            logger.info("table_alert_channel_created")

            # ==================== 新架构：Agent 生成的定时任务 ====================

            # 定时任务配置表（Agent 创建）
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_task (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL COMMENT '任务名称',
                    description TEXT COMMENT '任务描述（Agent生成的）',
                    target_type VARCHAR(20) NOT NULL COMMENT 'org | repo',
                    target_name VARCHAR(200) NOT NULL COMMENT 'org_name 或 repo_full_name',
                    prompt TEXT NOT NULL COMMENT 'Agent 执行的 prompt',
                    cron_expression VARCHAR(50) NOT NULL COMMENT 'cron表达式',
                    dimensions JSON COMMENT '扫描维度: [cve, secret, license, community]',
                    alert_threshold VARCHAR(20) DEFAULT 'HIGH' COMMENT '告警阈值',
                    alert_channels JSON COMMENT '告警渠道配置（旧格式，兼容）',
                    alert_channel_ids JSON COMMENT '绑定的告警渠道ID列表',
                    status VARCHAR(20) DEFAULT 'active' COMMENT 'active | paused | disabled',
                    enabled BOOLEAN DEFAULT TRUE COMMENT '是否启用',
                    created_by VARCHAR(50) DEFAULT 'agent' COMMENT '创建者: agent | manual',
                    conversation_id VARCHAR(50) COMMENT '关联的对话ID',
                    last_run_id VARCHAR(50) COMMENT '上次执行的 run_id',
                    last_run_at TIMESTAMP NULL COMMENT '上次执行时间',
                    last_run_status VARCHAR(20) COMMENT '上次执行状态',
                    next_run_at TIMESTAMP NULL COMMENT '下次执行时间',
                    run_count INT DEFAULT 0 COMMENT '累计执行次数',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_target (target_type, target_name),
                    INDEX idx_status (status, enabled),
                    INDEX idx_next_run (next_run_at),
                    INDEX idx_created_by (created_by)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent生成的定时任务配置'
            """)
            logger.info("table_scheduled_task_created")

            # 定时任务执行记录表
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_task_execution (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    scheduled_task_id INT NOT NULL COMMENT '关联的定时任务ID',
                    run_id VARCHAR(50) NOT NULL COMMENT '执行ID',
                    status VARCHAR(20) NOT NULL COMMENT 'running | completed | failed',
                    started_at TIMESTAMP NOT NULL COMMENT '开始时间',
                    completed_at TIMESTAMP NULL COMMENT '完成时间',
                    error_message TEXT COMMENT '错误信息',
                    error_detail TEXT COMMENT '详细错误信息（含堆栈）',
                    steps JSON COMMENT '执行步骤记录',
                    tool_calls JSON COMMENT '工具调用详细记录',
                    agent_output TEXT COMMENT 'Agent 最终输出内容',
                    execution_log TEXT COMMENT '执行过程日志',
                    total_findings INT DEFAULT 0 COMMENT '发现数量',
                    high_severity_count INT DEFAULT 0 COMMENT '高危数量',
                    duration_seconds INT DEFAULT 0 COMMENT '执行耗时',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_task_id (scheduled_task_id),
                    INDEX idx_run_id (run_id),
                    INDEX idx_status (status),
                    INDEX idx_started_at (started_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务执行记录'
            """)
            logger.info("table_scheduled_task_execution_created")

            # 扫描任务表
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS scan_task (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    run_id VARCHAR(50) UNIQUE,
                    scan_type VARCHAR(20) NOT NULL,
                    org_name VARCHAR(100),
                    trigger_by VARCHAR(50),
                    status VARCHAR(20) DEFAULT 'pending',
                    phase VARCHAR(30) DEFAULT 'init',
                    phase_progress JSON,
                    scan_warnings JSON,
                    total_repos INT DEFAULT 0,
                    scanned_repos INT DEFAULT 0,
                    findings_count INT DEFAULT 0,
                    paused_at TIMESTAMP NULL,
                    resume_from_repo VARCHAR(200),
                    error_message TEXT,
                    started_at TIMESTAMP NULL,
                    completed_at TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_run_id (run_id),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            logger.info("table_scan_task_created")

            # 发现记录表
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS finding (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    repo_full_name VARCHAR(200) NOT NULL,
                    finding_type VARCHAR(30) NOT NULL,
                    severity VARCHAR(20) NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    description TEXT,
                    detail JSON,
                    is_acknowledged BOOLEAN DEFAULT FALSE,
                    acknowledged_by VARCHAR(100),
                    acknowledged_at TIMESTAMP NULL,
                    scan_task_id INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_repo (repo_full_name),
                    INDEX idx_severity (severity),
                    INDEX idx_type (finding_type),
                    INDEX idx_acknowledged (is_acknowledged)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            logger.info("table_finding_created")

            # 扫描子任务表
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS scan_subtask (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    scan_task_id INT NOT NULL,
                    repo_full_name VARCHAR(200) NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    findings_count INT DEFAULT 0,
                    high_severity_count INT DEFAULT 0,
                    started_at TIMESTAMP NULL,
                    completed_at TIMESTAMP NULL,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_scan_task_id (scan_task_id),
                    INDEX idx_status (status),
                    INDEX idx_repo (repo_full_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            logger.info("table_scan_subtask_created")

            # 扫描报告表
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS scan_report (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    scan_task_id INT NOT NULL,
                    report_type VARCHAR(30) DEFAULT 'deep_analysis',
                    title VARCHAR(200) NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT,
                    recommendations JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_scan_task_id (scan_task_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            logger.info("table_scan_report_created")

            # 扫描历史表
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS scan_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    org_name VARCHAR(100) NOT NULL,
                    run_id VARCHAR(50) NOT NULL,
                    scan_type VARCHAR(20) NOT NULL,
                    scan_mode VARCHAR(20) DEFAULT 'balanced',
                    trigger_by VARCHAR(50) DEFAULT 'manual',
                    status VARCHAR(20) NOT NULL,
                    total_repos INT DEFAULT 0,
                    findings_count INT DEFAULT 0,
                    high_severity_count INT DEFAULT 0,
                    duration_seconds INT DEFAULT 0,
                    success_rate FLOAT DEFAULT 0.0,
                    started_at TIMESTAMP NULL,
                    completed_at TIMESTAMP NULL,
                    dimensions JSON,
                    summary JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_org_name (org_name),
                    INDEX idx_run_id (run_id),
                    INDEX idx_status (status),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            logger.info("table_scan_history_created")

            # 字段迁移（兼容旧数据库）
            await _migrate_fields(cur)

            # 索引优化
            await _optimize_indexes(cur)

            logger.info("database_tables_initialized")


async def _migrate_fields(cur):
    """字段迁移（确保旧表有新字段）。"""
    migrations = [
        # scan_task 表迁移
        ("scan_task", "paused_at", "TIMESTAMP NULL"),
        ("scan_task", "resume_from_repo", "VARCHAR(200)"),
        ("scan_task", "phase", "VARCHAR(30) DEFAULT 'init'"),
        ("scan_task", "phase_progress", "JSON"),
        ("scan_task", "scan_warnings", "JSON"),
        ("scan_task", "alert_status", "VARCHAR(20) DEFAULT NULL COMMENT '告警推送状态'"),
        ("scan_task", "alert_sent_at", "TIMESTAMP NULL COMMENT '告警发送时间'"),
        ("scan_task", "alert_findings_count", "INT DEFAULT 0 COMMENT '推送的发现数量'"),
        ("scan_task", "alert_error", "TEXT COMMENT '告警发送错误信息'"),
        # scheduled_task 表迁移
        ("scheduled_task", "alert_channels", "JSON COMMENT '告警渠道配置（旧格式，兼容）'"),
        ("scheduled_task", "alert_channel_ids", "JSON COMMENT '绑定的告警渠道ID列表'"),
        # alert_channel 表迁移
        ("alert_channel", "description", "TEXT COMMENT '渠道描述'"),
        # scheduled_task_execution 表迁移（新增字段）
        ("scheduled_task_execution", "error_detail", "TEXT COMMENT '详细错误信息（含堆栈）'"),
        ("scheduled_task_execution", "tool_calls", "JSON COMMENT '工具调用详细记录'"),
        ("scheduled_task_execution", "agent_output", "TEXT COMMENT 'Agent 最终输出内容'"),
        ("scheduled_task_execution", "execution_log", "TEXT COMMENT '执行过程日志'"),
    ]

    for table, column, definition in migrations:
        try:
            await cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.info(f"column_{column}_added")
        except:
            pass  # 字段已存在


async def _optimize_indexes(cur):
    """索引优化。"""
    indexes = [
        ("scan_task", "idx_org_name", "org_name"),
        ("scan_task", "idx_org_status", "org_name, status"),
        ("scan_task", "idx_created_at", "created_at"),
        ("scan_subtask", "idx_task_status", "scan_task_id, status"),
        ("finding", "idx_created_at", "created_at"),
        ("finding", "idx_scan_task_id", "scan_task_id"),
        ("finding", "idx_common_filter", "severity, finding_type, is_acknowledged, created_at DESC"),
        ("finding", "idx_severity_ack", "severity, is_acknowledged, created_at DESC"),
        ("finding", "idx_type_ack", "finding_type, is_acknowledged, created_at DESC"),
    ]

    for table, index_name, columns in indexes:
        try:
            await cur.execute(f"CREATE INDEX {index_name} ON {table} ({columns})")
            logger.info(f"index_added_{index_name}")
        except:
            pass  # 索引已存在