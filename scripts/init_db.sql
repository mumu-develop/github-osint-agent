-- OSINT 业务数据表初始化脚本
-- 可手动执行或在 FastAPI lifespan 中自动执行

-- 组织配置表
CREATE TABLE IF NOT EXISTS org_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_name VARCHAR(100) NOT NULL UNIQUE COMMENT 'GitHub组织名称',
    display_name VARCHAR(200) COMMENT '显示名称',
    scan_enabled BOOLEAN DEFAULT TRUE COMMENT '是否启用扫描',
    scan_frequency VARCHAR(20) DEFAULT 'daily' COMMENT '扫描频率: daily|hourly|weekly',
    alert_channels JSON COMMENT '预警渠道配置',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='组织扫描配置表';

-- 仓库监控表
CREATE TABLE IF NOT EXISTS repo_monitor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_id INT NOT NULL COMMENT '所属组织ID',
    repo_name VARCHAR(100) NOT NULL COMMENT '仓库名称',
    repo_full_name VARCHAR(200) NOT NULL COMMENT '完整仓库路径 (owner/repo)',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否监控',
    priority_tier VARCHAR(20) DEFAULT 'L2_STANDARD' COMMENT '优先级层级: L1_HOT|L2_STANDARD|L3_NORMAL',
    star_count INT DEFAULT 0 COMMENT 'Star数',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_org_id (org_id),
    INDEX idx_repo_full_name (repo_full_name),
    UNIQUE KEY uk_org_repo (org_id, repo_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仓库监控配置表';

-- 扫描任务表
CREATE TABLE IF NOT EXISTS scan_task (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(50) UNIQUE COMMENT '扫描运行ID',
    scan_type VARCHAR(20) NOT NULL COMMENT '扫描类型: L1_LIGHT|L2_STANDARD|L3_DEEP|MANUAL',
    org_name VARCHAR(100) COMMENT '目标组织名称',
    trigger_by VARCHAR(50) COMMENT '触发方式: scheduler|manual|alert',
    status VARCHAR(20) DEFAULT 'pending' COMMENT '状态: pending|running|completed|failed|paused',
    phase VARCHAR(30) DEFAULT 'init' COMMENT '当前阶段: init|scanning|llm_analysis|generating_report|alert_sending|done',
    phase_progress JSON COMMENT '各维度扫描进度',
    scan_warnings JSON COMMENT '扫描警告信息',
    total_repos INT DEFAULT 0 COMMENT '扫描仓库总数',
    scanned_repos INT DEFAULT 0 COMMENT '已扫描数量',
    findings_count INT DEFAULT 0 COMMENT '发现数量',
    alert_status VARCHAR(20) COMMENT '告警推送状态: pending|sending|sent|skipped|failed',
    alert_sent_at TIMESTAMP NULL COMMENT '告警发送时间',
    alert_findings_count INT DEFAULT 0 COMMENT '推送的发现数量',
    alert_error TEXT COMMENT '告警发送错误信息',
    paused_at TIMESTAMP NULL COMMENT '暂停时间',
    resume_from_repo VARCHAR(200) COMMENT '恢复时从哪个仓库继续',
    error_message TEXT COMMENT '错误信息',
    started_at TIMESTAMP NULL COMMENT '开始时间',
    completed_at TIMESTAMP NULL COMMENT '完成时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_run_id (run_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='扫描任务记录表';

-- 发现记录表
CREATE TABLE IF NOT EXISTS finding (
    id INT AUTO_INCREMENT PRIMARY KEY,
    repo_full_name VARCHAR(200) NOT NULL COMMENT '仓库完整路径',
    finding_type VARCHAR(30) NOT NULL COMMENT '发现类型: CVE|SECRET|LICENSE|COMMUNITY|TREND',
    severity VARCHAR(20) NOT NULL COMMENT '严重程度: INFO|LOW|MEDIUM|HIGH|CRITICAL',
    title VARCHAR(500) NOT NULL COMMENT '标题',
    description TEXT COMMENT '详细描述',
    detail JSON COMMENT '详细信息JSON',
    is_acknowledged BOOLEAN DEFAULT FALSE COMMENT '是否已确认',
    acknowledged_by VARCHAR(100) COMMENT '确认人',
    acknowledged_at TIMESTAMP NULL COMMENT '确认时间',
    scan_task_id INT COMMENT '关联扫描任务ID',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_repo (repo_full_name),
    INDEX idx_severity (severity),
    INDEX idx_type (finding_type),
    INDEX idx_acknowledged (is_acknowledged),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='安全发现记录表';

-- 示例数据插入（可选）
-- INSERT INTO org_config (org_name, display_name, scan_enabled, scan_frequency, alert_channels)
-- VALUES ('SOFAStack', '蚂蚁金服SOFAStack', TRUE, 'daily', '{"dingtalk": "https://oapi.dingtalk.com/robot/send?access_token=xxx"}');