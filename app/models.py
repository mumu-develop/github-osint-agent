from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime


class ChatRequest(BaseModel):
    """流式对话请求"""
    session_id: Optional[str] = None
    message: str


# ==================== 业务数据模型 ====================

class ScanTask(BaseModel):
    """扫描任务"""
    id: Optional[int] = None
    run_id: Optional[str] = Field(None, description="扫描运行ID")
    scan_type: str = Field(..., description="扫描类型: L1_LIGHT|L2_STANDARD|L3_DEEP|FAST|BALANCED|DEEP")
    org_name: Optional[str] = Field(None, description="目标组织名称")
    trigger_by: Optional[str] = Field(None, description="触发方式: scheduler|manual|alert")
    status: str = Field("pending", description="状态: pending|running|completed|failed|paused")
    phase: str = Field("init", description="当前阶段: init|scanning|llm_analysis|generating_report|alert_sending|done")
    phase_progress: Optional[Dict] = Field(None, description="各维度扫描进度: {cve: {done: 10, total: 47}, ...}")
    scan_warnings: Optional[List[Dict]] = Field(None, description="扫描警告信息: [{type: 'rate_limit', message: '...', timestamp: '...'}]")
    total_repos: int = Field(0, description="扫描仓库总数")
    scanned_repos: int = Field(0, description="已扫描数量")
    findings_count: int = Field(0, description="发现数量")
    # 告警推送状态
    alert_status: Optional[str] = Field(None, description="告警推送状态: pending|sending|sent|skipped|failed")
    alert_sent_at: Optional[datetime] = Field(None, description="告警发送时间")
    alert_findings_count: int = Field(0, description="推送的发现数量")
    alert_error: Optional[str] = Field(None, description="告警发送错误信息")
    paused_at: Optional[datetime] = Field(None, description="暂停时间")
    resume_from_repo: Optional[str] = Field(None, description="恢复时从哪个仓库继续")
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class Finding(BaseModel):
    """发现记录"""
    id: Optional[int] = None
    repo_full_name: str = Field(..., description="仓库完整路径")
    finding_type: str = Field(..., description="发现类型: CVE|SECRET|LICENSE|COMMUNITY|TREND")
    severity: str = Field(..., description="严重程度: INFO|LOW|MEDIUM|HIGH|CRITICAL")
    title: str = Field(..., description="标题")
    description: Optional[str] = Field(None, description="详细描述")
    detail: Optional[Dict] = Field(None, description="详细信息JSON")
    is_acknowledged: bool = Field(False, description="是否已确认")
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    scan_task_id: Optional[int] = Field(None, description="关联扫描任务ID")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ScanTriggerRequest(BaseModel):
    """扫描触发请求"""
    scan_type: str = Field("L1_LIGHT", description="扫描类型: L1_LIGHT|L2_STANDARD|L3_DEEP|MANUAL")
    org_name: Optional[str] = Field(None, description="目标组织名称")


class FindingQueryRequest(BaseModel):
    """发现查询请求"""
    severity: Optional[str] = Field(None, description="筛选严重程度")
    finding_type: Optional[str] = Field(None, description="筛选发现类型")
    repo_full_name: Optional[str] = Field(None, description="筛选仓库")
    is_acknowledged: Optional[bool] = Field(None, description="是否已确认")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


# ==================== 扫描模板定义 ====================

SCAN_TEMPLATES = {
    "basic": {
        "name": "基础安全",
        "description": "CVE漏洞 + 敏感信息 + 许可证检查",
        "dimensions": {"cve": True, "secret": True, "license": True, "community": False, "trend": False, "supply_chain": False},
        "llm_enabled": False
    },
    "standard": {
        "name": "标准扫描",
        "description": "基础安全 + 社区健康度检查",
        "dimensions": {"cve": True, "secret": True, "license": True, "community": True, "trend": False, "supply_chain": False},
        "llm_enabled": False
    },
    "deep": {
        "name": "深度审计",
        "description": "全量扫描 + LLM深度分析（趋势、供应链）",
        "dimensions": {"cve": True, "secret": True, "license": True, "community": True, "trend": True, "supply_chain": True},
        "llm_enabled": True
    },
    "compliance_only": {
        "name": "合规检查",
        "description": "仅许可证合规检查",
        "dimensions": {"cve": False, "secret": False, "license": True, "community": False, "trend": False, "supply_chain": False},
        "llm_enabled": False
    },
    "security_focus": {
        "name": "安全专项",
        "description": "CVE + 敏感信息 + 供应链风险",
        "dimensions": {"cve": True, "secret": True, "license": False, "community": False, "trend": False, "supply_chain": True},
        "llm_enabled": True
    }
}


class ManualScanRequest(BaseModel):
    """手动扫描请求（支持维度选择）"""
    dimensions: Optional[List[str]] = Field(None, description="指定扫描维度列表，如 ['cve', 'secret']")
    template: Optional[str] = Field(None, description="使用预设模板: basic|standard|deep|compliance_only|security_focus")
    llm_enabled: Optional[bool] = Field(None, description="是否启用LLM分析")


class ApplyTemplateRequest(BaseModel):
    """应用预设模板请求"""
    template: str = Field(..., description="模板名称: basic|standard|deep|compliance_only|security_focus")


class ScanSubTask(BaseModel):
    """扫描子任务 - 单个仓库的扫描记录"""
    id: Optional[int] = None
    scan_task_id: int = Field(..., description="关联的主扫描任务ID")
    repo_full_name: str = Field(..., description="仓库全名 owner/repo")
    status: str = Field("pending", description="状态: pending|running|completed|failed|paused")
    findings_count: int = Field(0, description="发现的Finding数量")
    high_severity_count: int = Field(0, description="高危Finding数量")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None


class ScanHistory(BaseModel):
    """扫描执行历史 - 任务完成后归档记录"""
    id: Optional[int] = None
    org_name: str = Field(..., description="组织名称")
    run_id: str = Field(..., description="任务运行ID")
    scan_type: str = Field(..., description="扫描类型")
    scan_mode: str = Field("balanced", description="扫描模式: fast|balanced|deep")
    trigger_by: str = Field("manual", description="触发方式: manual|scheduler")
    status: str = Field(..., description="最终状态: completed|failed")
    total_repos: int = Field(0, description="扫描仓库总数")
    findings_count: int = Field(0, description="发现问题总数")
    high_severity_count: int = Field(0, description="高危问题数量")
    # 执行统计
    duration_seconds: int = Field(0, description="执行耗时（秒）")
    success_rate: float = Field(0.0, description="成功率（子任务完成比例）")
    # 时间记录
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    # 扫描维度（JSON）
    dimensions: Optional[Dict[str, bool]] = Field(None, description="扫描维度配置")
    # 结果摘要（JSON）
    summary: Optional[Dict[str, Any]] = Field(None, description="结果摘要统计")
    created_at: Optional[datetime] = None


class ScanReport(BaseModel):
    """扫描报告 - Agent生成的深度分析报告"""
    id: Optional[int] = None
    scan_task_id: int = Field(..., description="关联的主扫描任务ID")
    report_type: str = Field("deep_analysis", description="报告类型: deep_analysis|summary|security_audit")
    title: str = Field(..., description="报告标题")
    content: str = Field(..., description="报告内容（Markdown格式）")
    summary: Optional[str] = Field(None, description="摘要")
    recommendations: Optional[List[str]] = Field(None, description="修复建议列表")
    created_at: Optional[datetime] = None


# ==================== Agent 生成的定时任务模型 ====================

class ScheduledTask(BaseModel):
    """Agent 生成的定时任务"""
    id: Optional[int] = None
    name: str = Field(..., description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    target_type: str = Field(..., description="目标类型: org | repo")
    target_name: str = Field(..., description="目标名称: org_name 或 repo_full_name")
    prompt: str = Field(..., description="Agent 执行的 prompt")
    cron_expression: str = Field(..., description="cron 表达式: 0 3 * * *")
    dimensions: Optional[List[str]] = Field(None, description="扫描维度列表")
    alert_threshold: str = Field("HIGH", description="告警阈值: CRITICAL|HIGH|MEDIUM")
    alert_channels: Optional[Dict[str, Any]] = Field(None, description="告警渠道配置（旧格式，兼容）")
    alert_channel_ids: Optional[List[int]] = Field(None, description="绑定的告警渠道ID列表")
    status: str = Field("active", description="状态: active | paused | disabled")
    enabled: bool = Field(True, description="是否启用")
    created_by: str = Field("agent", description="创建者: agent | manual")
    conversation_id: Optional[str] = Field(None, description="关联的对话ID")
    last_run_id: Optional[str] = Field(None, description="上次执行的 run_id")
    last_run_at: Optional[datetime] = Field(None, description="上次执行时间")
    last_run_status: Optional[str] = Field(None, description="上次执行状态")
    next_run_at: Optional[datetime] = Field(None, description="下次执行时间")
    run_count: int = Field(0, description="累计执行次数")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AlertChannel(BaseModel):
    """告警渠道配置"""
    id: Optional[int] = None
    name: str = Field(..., description="渠道名称（用户自定义）")
    channel_type: str = Field(..., description="渠道类型: dingtalk | feishu | webhook")
    webhook_url: str = Field(..., description="Webhook URL")
    secret: Optional[str] = Field(None, description="签名密钥（钉钉可选）")
    description: Optional[str] = Field(None, description="渠道描述")
    enabled: bool = Field(True, description="是否启用")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ScheduledTaskExecution(BaseModel):
    """定时任务执行记录"""
    id: Optional[int] = None
    scheduled_task_id: int = Field(..., description="关联的定时任务ID")
    run_id: str = Field(..., description="执行ID")
    status: str = Field(..., description="状态: running | completed | failed")
    started_at: datetime = Field(..., description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    error_message: Optional[str] = Field(None, description="错误信息")
    error_detail: Optional[str] = Field(None, description="详细错误信息（含堆栈）")
    steps: Optional[List[Dict]] = Field(None, description="执行步骤记录")
    tool_calls: Optional[List[Dict]] = Field(None, description="工具调用详细记录")
    agent_output: Optional[str] = Field(None, description="Agent 最终输出内容")
    execution_log: Optional[str] = Field(None, description="执行过程日志")
    total_findings: int = Field(0, description="发现数量")
    high_severity_count: int = Field(0, description="高危数量")
    duration_seconds: int = Field(0, description="执行耗时")
    created_at: Optional[datetime] = None