"""数据库表初始化脚本 - 手动执行创建表。"""

import asyncio
import aiomysql
import os
from dotenv import load_dotenv

load_dotenv()


async def create_tables():
    """创建所有业务表。"""

    mysql_host = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_password = os.getenv("MYSQL_PASSWORD", "123456")
    mysql_db = os.getenv("MYSQL_DB_NAME", "osint")

    print(f"连接数据库: {mysql_host}:{mysql_port}/{mysql_db}")

    conn = await aiomysql.connect(
        host=mysql_host,
        port=mysql_port,
        user=mysql_user,
        password=mysql_password,
        db=mysql_db,
        charset="utf8mb4"
    )

    async with conn.cursor() as cur:
        # ==================== 新架构：Agent 生成的定时任务 ====================

        print("创建 scheduled_task 表...")
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
        print("✓ scheduled_task 表创建成功")

        # 定时任务执行记录表
        print("创建 scheduled_task_execution 表...")
        await cur.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_task_execution (
                id INT AUTO_INCREMENT PRIMARY KEY,
                scheduled_task_id INT NOT NULL COMMENT '关联的定时任务ID',
                run_id VARCHAR(50) NOT NULL COMMENT '执行ID',
                status VARCHAR(20) NOT NULL COMMENT 'running | completed | failed',
                started_at TIMESTAMP NOT NULL COMMENT '开始时间',
                completed_at TIMESTAMP NULL COMMENT '完成时间',
                error_message TEXT COMMENT '错误信息',
                steps JSON COMMENT '执行步骤记录',
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
        print("✓ scheduled_task_execution 表创建成功")

        # ==================== 保留的表 ====================

        print("创建 scan_task 表...")
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
                alert_status VARCHAR(20) DEFAULT NULL,
                alert_sent_at TIMESTAMP NULL,
                alert_findings_count INT DEFAULT 0,
                alert_error TEXT,
                paused_at TIMESTAMP NULL,
                resume_from_repo VARCHAR(200),
                error_message TEXT,
                started_at TIMESTAMP NULL,
                completed_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_run_id (run_id),
                INDEX idx_status (status),
                INDEX idx_org_name (org_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        print("✓ scan_task 表创建成功")

        print("创建 finding 表...")
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
        print("✓ finding 表创建成功")

        print("创建 scan_subtask 表...")
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
        print("✓ scan_subtask 表创建成功")

        print("创建 scan_report 表...")
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
        print("✓ scan_report 表创建成功")

        print("创建 scan_history 表...")
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
        print("✓ scan_history 表创建成功")

        # 删除旧的 org_config 和 repo_monitor 表（如果存在）
        print("删除旧表...")
        try:
            await cur.execute("DROP TABLE IF EXISTS repo_monitor")
            print("✓ repo_monitor 表已删除")
        except:
            print("! repo_monitor 表不存在")

        try:
            await cur.execute("DROP TABLE IF EXISTS org_config")
            print("✓ org_config 表已删除")
        except:
            print("! org_config 表不存在")

    await conn.commit()
    conn.close()

    print("\n所有表创建完成！")


if __name__ == "__main__":
    asyncio.run(create_tables())