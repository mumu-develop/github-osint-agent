"""数据库表初始化脚本 - 使用同步 pymysql。"""

import pymysql
import os
from dotenv import load_dotenv

load_dotenv()


def create_tables():
    """创建所有业务表。"""

    mysql_host = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_password = os.getenv("MYSQL_PASSWORD", "123456")
    mysql_db = os.getenv("MYSQL_DB_NAME", "osint")

    print(f"连接数据库: {mysql_host}:{mysql_port}/{mysql_db}")

    try:
        conn = pymysql.connect(
            host=mysql_host,
            port=mysql_port,
            user=mysql_user,
            password=mysql_password,
            db=mysql_db,
            charset="utf8mb4"
        )
    except Exception as e:
        print(f"数据库连接失败: {e}")
        print("\n请确保 MySQL 服务正在运行，并且配置正确。")
        print("你可以手动执行以下 SQL 来创建表：")
        print_sql()
        return

    cur = conn.cursor()

    # ==================== 新架构：Agent 生成的定时任务 ====================

    print("\n创建 scheduled_task 表...")
    cur.execute("""
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

    print("创建 scheduled_task_execution 表...")
    cur.execute("""
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

    # 删除旧表
    print("\n删除旧表...")
    try:
        cur.execute("DROP TABLE IF EXISTS repo_monitor")
        print("✓ repo_monitor 表已删除")
    except:
        print("! repo_monitor 表不存在")

    try:
        cur.execute("DROP TABLE IF EXISTS org_config")
        print("✓ org_config 表已删除")
    except:
        print("! org_config 表不存在")

    conn.commit()
    cur.close()
    conn.close()

    print("\n所有表创建完成！")


def print_sql():
    """打印手动执行的 SQL。"""
    print("\n" + "="*60)
    print("手动执行以下 SQL（在 MySQL 客户端中）：")
    print("="*60)
    print("""
-- 1. 创建 scheduled_task 表
CREATE TABLE IF NOT EXISTS scheduled_task (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT '任务名称',
    description TEXT COMMENT '任务描述',
    target_type VARCHAR(20) NOT NULL COMMENT 'org | repo',
    target_name VARCHAR(200) NOT NULL COMMENT '目标名称',
    prompt TEXT NOT NULL COMMENT 'Agent 执行的 prompt',
    cron_expression VARCHAR(50) NOT NULL COMMENT 'cron表达式',
    dimensions JSON COMMENT '扫描维度',
    alert_threshold VARCHAR(20) DEFAULT 'HIGH',
    status VARCHAR(20) DEFAULT 'active',
    enabled BOOLEAN DEFAULT TRUE,
    created_by VARCHAR(50) DEFAULT 'agent',
    conversation_id VARCHAR(50),
    last_run_id VARCHAR(50),
    last_run_at TIMESTAMP NULL,
    last_run_status VARCHAR(20),
    next_run_at TIMESTAMP NULL,
    run_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_target (target_type, target_name),
    INDEX idx_status (status, enabled),
    INDEX idx_next_run (next_run_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 创建 scheduled_task_execution 表
CREATE TABLE IF NOT EXISTS scheduled_task_execution (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scheduled_task_id INT NOT NULL,
    run_id VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP NULL,
    error_message TEXT,
    steps JSON,
    total_findings INT DEFAULT 0,
    high_severity_count INT DEFAULT 0,
    duration_seconds INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_task_id (scheduled_task_id),
    INDEX idx_run_id (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 删除旧表
DROP TABLE IF EXISTS repo_monitor;
DROP TABLE IF EXISTS org_config;
""")
    print("="*60)


if __name__ == "__main__":
    create_tables()