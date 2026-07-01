-- 数据库迁移脚本 - 新增告警状态字段
-- 请手动执行此脚本

-- 1. 扫描任务表新增字段
ALTER TABLE scan_task ADD COLUMN phase VARCHAR(30) DEFAULT 'init' COMMENT '当前阶段: init|scanning|llm_analysis|generating_report|alert_sending|done';
ALTER TABLE scan_task ADD COLUMN phase_progress JSON COMMENT '各维度扫描进度';
ALTER TABLE scan_task ADD COLUMN scan_warnings JSON COMMENT '扫描警告信息';
ALTER TABLE scan_task ADD COLUMN paused_at TIMESTAMP NULL COMMENT '暂停时间';
ALTER TABLE scan_task ADD COLUMN resume_from_repo VARCHAR(200) COMMENT '恢复时从哪个仓库继续';

-- 2. 扫描任务表新增告警状态字段
ALTER TABLE scan_task ADD COLUMN alert_status VARCHAR(20) COMMENT '告警推送状态: pending|sending|sent|skipped|failed';
ALTER TABLE scan_task ADD COLUMN alert_sent_at TIMESTAMP NULL COMMENT '告警发送时间';
ALTER TABLE scan_task ADD COLUMN alert_findings_count INT DEFAULT 0 COMMENT '推送的发现数量';
ALTER TABLE scan_task ADD COLUMN alert_error TEXT COMMENT '告警发送错误信息';

-- 3. 组织配置表新增字段（如果之前没有）
ALTER TABLE org_config ADD COLUMN scan_dimensions JSON COMMENT '扫描维度配置';
ALTER TABLE org_config ADD COLUMN llm_enabled BOOLEAN DEFAULT FALSE COMMENT '是否启用LLM深度分析';
ALTER TABLE org_config ADD COLUMN generate_report BOOLEAN DEFAULT TRUE COMMENT '扫描完成后是否生成分析报告';
ALTER TABLE org_config ADD COLUMN secret_filter_config JSON COMMENT 'SECRET扫描过滤配置';
ALTER TABLE org_config ADD COLUMN alert_threshold VARCHAR(20) DEFAULT 'HIGH' COMMENT '告警阈值';
ALTER TABLE org_config ADD COLUMN alert_immediate BOOLEAN DEFAULT TRUE COMMENT '高危问题是否立即推送';
ALTER TABLE org_config ADD COLUMN alert_rules JSON COMMENT '推送规则: {severity: immediate|disabled}';

-- 4. 发现表新增索引
ALTER TABLE finding ADD INDEX idx_scan_task_id (scan_task_id);

-- 5. 扫描子任务表（如果之前没有）
CREATE TABLE IF NOT EXISTS scan_subtask (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scan_task_id INT NOT NULL COMMENT '主任务ID',
    repo_full_name VARCHAR(200) NOT NULL COMMENT '仓库完整路径',
    status VARCHAR(20) DEFAULT 'pending' COMMENT '状态: pending|running|completed|failed|paused',
    findings_count INT DEFAULT 0 COMMENT '发现数量',
    high_severity_count INT DEFAULT 0 COMMENT '高危数量',
    started_at TIMESTAMP NULL COMMENT '开始时间',
    completed_at TIMESTAMP NULL COMMENT '完成时间',
    error_message TEXT COMMENT '错误信息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_scan_task_id (scan_task_id),
    INDEX idx_status (status),
    INDEX idx_repo (repo_full_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='扫描子任务记录表';

-- 6. 扫描历史记录表（如果之前没有）
CREATE TABLE IF NOT EXISTS scan_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id VARCHAR(50) COMMENT '扫描运行ID',
    scan_type VARCHAR(20) COMMENT '扫描类型',
    scan_mode VARCHAR(20) COMMENT '扫描模式: fast|balanced|deep',
    org_name VARCHAR(100) COMMENT '组织名称',
    trigger_by VARCHAR(50) COMMENT '触发方式',
    status VARCHAR(20) COMMENT '状态',
    total_repos INT DEFAULT 0 COMMENT '扫描仓库总数',
    findings_count INT DEFAULT 0 COMMENT '发现数量',
    high_severity_count INT DEFAULT 0 COMMENT '高危数量',
    duration_seconds INT DEFAULT 0 COMMENT '耗时秒数',
    success_rate DECIMAL(5,2) DEFAULT 0 COMMENT '成功率',
    dimensions JSON COMMENT '扫描维度',
    summary JSON COMMENT '扫描结果摘要',
    started_at TIMESTAMP NULL COMMENT '开始时间',
    completed_at TIMESTAMP NULL COMMENT '完成时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_run_id (run_id),
    INDEX idx_org_name (org_name),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='扫描历史记录表';

-- 7. 扫描报告表（如果之前没有）
CREATE TABLE IF NOT EXISTS scan_report (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scan_task_id INT NOT NULL COMMENT '扫描任务ID',
    report_type VARCHAR(30) DEFAULT 'deep_analysis' COMMENT '报告类型',
    title VARCHAR(200) COMMENT '报告标题',
    content LONGTEXT COMMENT '报告内容(Markdown)',
    summary TEXT COMMENT '报告摘要',
    recommendations JSON COMMENT '修复建议列表',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_scan_task_id (scan_task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='扫描分析报告表';