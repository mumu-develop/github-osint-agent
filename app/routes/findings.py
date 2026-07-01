"""发现记录 API 路由。"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
from app.models import Finding
from app.database import FindingDAO, init_business_tables
from app.log_utils import get_logger

logger = get_logger("findings_routes")

router = APIRouter(prefix="/api/findings", tags=["findings"])


def generate_github_url(finding: Finding) -> str:
    """生成 GitHub 链接。

    根据 Finding 的类型和 detail 信息生成对应的 GitHub 链接：
    - 有 commit_sha：跳转到特定 commit 的文件（最准确）
    - 有文件路径但无 commit：跳转到仓库首页（避免分支 404）
    - 无文件路径：跳转到仓库首页

    Args:
        finding: Finding 对象

    Returns:
        GitHub URL
    """
    repo = finding.repo_full_name
    detail = finding.detail or {}

    file_path = detail.get("file")
    commit_sha = detail.get("commit_sha")

    # 优先使用 commit_sha（最准确，不会 404）
    if file_path and commit_sha:
        return f"https://github.com/{repo}/blob/{commit_sha}/{file_path}"
    elif file_path:
        # 有文件但无 commit，跳转到仓库首页（避免分支错误导致 404）
        # 用户可以在仓库中搜索文件名
        return f"https://github.com/{repo}"
    else:
        # 无文件路径，跳转到仓库首页
        return f"https://github.com/{repo}"


# ==================== 静态路由（放在动态路由之前）====================

@router.get("")
async def list_findings(
    severity: Optional[str] = Query(None, description="筛选严重程度"),
    finding_type: Optional[str] = Query(None, description="筛选发现类型"),
    repo_full_name: Optional[str] = Query(None, description="筛选仓库"),
    is_acknowledged: Optional[bool] = Query(None, description="是否已确认"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
) -> Dict[str, Any]:
    """获取发现记录列表。"""
    await init_business_tables()

    findings = await FindingDAO.query(
        severity=severity,
        finding_type=finding_type,
        repo_full_name=repo_full_name,
        is_acknowledged=is_acknowledged,
        page=page,
        page_size=page_size
    )

    total = await FindingDAO.count(
        severity=severity,
        finding_type=finding_type,
        repo_full_name=repo_full_name,
        is_acknowledged=is_acknowledged
    )

    return {
        "code": 0,
        "data": {
            "findings": [
                {
                    "id": f.id,
                    "repo_full_name": f.repo_full_name,
                    "finding_type": f.finding_type,
                    "severity": f.severity,
                    "title": f.title,
                    "description": f.description,
                    "detail": f.detail,
                    "github_url": generate_github_url(f),  # 新增：GitHub 跳转链接
                    "is_acknowledged": f.is_acknowledged,
                    "acknowledged_by": f.acknowledged_by,
                    "acknowledged_at": f.acknowledged_at.isoformat() if f.acknowledged_at else None,
                    "created_at": f.created_at.isoformat() if f.created_at else None
                }
                for f in findings
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total // page_size) + 1 if total else 0
        }
    }


@router.get("/stats")
async def get_findings_stats() -> Dict[str, Any]:
    """获取发现统计信息（单次聚合查询，避免多次COUNT）。"""
    stats = await FindingDAO.get_all_stats()

    return {
        "code": 0,
        "data": stats
    }


@router.get("/recent")
async def get_recent_findings(hours: int = Query(24, ge=1, le=168, description="最近N小时")) -> Dict[str, Any]:
    """获取最近发现记录（用于仪表板展示）。"""
    findings = await FindingDAO.query(page=1, page_size=50)
    recent = findings[:20]

    return {
        "code": 0,
        "data": {
            "findings": [
                {
                    "id": f.id,
                    "repo_full_name": f.repo_full_name,
                    "finding_type": f.finding_type,
                    "severity": f.severity,
                    "title": f.title,
                    "github_url": generate_github_url(f),  # 新增
                    "created_at": f.created_at.isoformat() if f.created_at else None
                }
                for f in recent
            ],
            "hours": hours
        }
    }


# ==================== 动态路由（放在静态路由之后）====================

@router.get("/{finding_id}")
async def get_finding(finding_id: int) -> Dict[str, Any]:
    """获取单个发现记录详情。"""
    finding = await FindingDAO.get_by_id(finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail=f"发现 #{finding_id} 不存在")

    return {
        "code": 0,
        "data": {
            "id": finding.id,
            "repo_full_name": finding.repo_full_name,
            "finding_type": finding.finding_type,
            "severity": finding.severity,
            "title": finding.title,
            "description": finding.description,
            "detail": finding.detail,
            "github_url": generate_github_url(finding),  # 新增
            "is_acknowledged": finding.is_acknowledged,
            "acknowledged_by": finding.acknowledged_by,
            "acknowledged_at": finding.acknowledged_at.isoformat() if finding.acknowledged_at else None,
            "created_at": finding.created_at.isoformat() if finding.created_at else None
        }
    }


@router.post("/{finding_id}/acknowledge")
async def acknowledge_finding(finding_id: int, acknowledged_by: str = "system") -> Dict[str, Any]:
    """确认发现记录（标记为已处理）。"""
    success = await FindingDAO.acknowledge(finding_id, acknowledged_by)

    if success:
        logger.info("finding_acknowledged", finding_id=finding_id, by=acknowledged_by)
        return {"code": 0, "data": {"message": f"发现 #{finding_id} 已确认"}}
    else:
        raise HTTPException(status_code=404, detail=f"发现 #{finding_id} 不存在")