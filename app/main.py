"""FastAPI 主应用模块。"""

import asyncio
import uuid
import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from app.agent import create_agent
from app.models import ChatRequest
from app.routes import download_router, set_sandbox_backend as set_download_backend, scanner_router, findings_router, scheduled_task_router, channel_router
from app.tools.report import set_sandbox_backend as set_report_backend
from app.progress import set_current_session, get_progress_queue, remove_progress_queue
from app.backend_factory import SandboxManager
from app.utils.sse_manager import acquire_sse_connection, release_sse_connection, get_sse_stats
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver
from langgraph.store.mysql.aio import AIOMySQLStore
from langgraph.store.memory import InMemoryStore
from app.log_utils import get_logger
from app.database import init_business_tables
from app.scheduler import init_scheduler, stop_scheduler
from app.redis_client import get_redis_client, close_redis_pool, check_redis_health
import aiomysql

logger = get_logger("main")

_agent = None
_backend = None  # 沙箱后端引用
_mysql_pool = None  # MySQL 连接池


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 应用生命周期管理（仅支持沙箱模式）。"""
    global _agent, _backend, _mysql_pool
    logger.info("lifespan_start")

    mysql_host = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_password = os.getenv("MYSQL_PASSWORD", "123456")
    mysql_db = os.getenv("MYSQL_DB_NAME", "osint")

    use_mysql = mysql_host and mysql_db

    try:
        if use_mysql:
            logger.info("mysql_connecting", host=mysql_host, port=mysql_port, db=mysql_db)

            # 创建 MySQL 连接池（支持高并发对话）
            # 每个对话会话占用 2 连接（checkpointer + store）
            # 配置 100 并发对话需要至少 200 连接池
            mysql_pool_maxsize = int(os.getenv("MYSQL_POOL_MAXSIZE", "200"))
            mysql_pool_minsize = int(os.getenv("MYSQL_POOL_MINSIZE", "20"))
            _mysql_pool = await aiomysql.create_pool(
                host=mysql_host,
                port=mysql_port,
                user=mysql_user,
                password=mysql_password,
                db=mysql_db,
                charset="utf8mb4",
                autocommit=True,
                minsize=mysql_pool_minsize,
                maxsize=mysql_pool_maxsize,
            )
            logger.info("mysql_pool_created", minsize=mysql_pool_minsize, maxsize=mysql_pool_maxsize)

            # 初始化业务数据表（在沙箱之前，独立执行）
            try:
                await init_business_tables()
                logger.info("business_tables_initialized")
            except Exception as e:
                logger.warning("business_tables_init_failed", error=str(e))

            # 初始化 Redis 连接池（用于分布式锁）
            try:
                await get_redis_client()
                redis_health = await check_redis_health()
                logger.info("redis_initialized", health=redis_health)
            except Exception as e:
                logger.warning("redis_init_failed", error=str(e), message="分布式锁功能不可用，回退到数据库检查")

            # 启动定时任务调度器
            try:
                await init_scheduler()
                logger.info("scheduler_started")
            except Exception as e:
                logger.warning("scheduler_start_failed", error=str(e))

            # 从连接池获取两个独立连接
            conn_checkpointer = await _mysql_pool.acquire()
            conn_store = await _mysql_pool.acquire()
            logger.info("mysql_connections_acquired")

            # 创建 checkpointer 和 store
            saver = AIOMySQLSaver(conn=conn_checkpointer)
            store = AIOMySQLStore(conn=conn_store)

            await saver.setup()
            await store.setup()
            logger.info("checkpointer_initialized")
            logger.info("store_initialized", store_type="AIOMySQLStore")

            # 尝试创建 Agent（沙箱可能失败）
            try:
                _agent, _backend = await create_agent(checkpointer=saver, store=store)
            except Exception as agent_error:
                logger.warning("agent_creation_failed", error=str(agent_error), message="聊天功能不可用，业务API正常")
                _agent = None
                _backend = None
        else:
            logger.info("no_mysql_using_inmemory_store")
            # 即使没有 MySQL，也初始化业务功能
            try:
                await init_business_tables()
                logger.info("business_tables_initialized_no_mysql")
            except Exception as e:
                logger.warning("business_tables_init_failed", error=str(e))

            # 初始化 Redis 连接池（用于分布式锁）
            try:
                await get_redis_client()
                redis_health = await check_redis_health()
                logger.info("redis_initialized_no_mysql", health=redis_health)
            except Exception as e:
                logger.warning("redis_init_failed_no_mysql", error=str(e))

            # 启动定时任务调度器
            try:
                await init_scheduler()
                logger.info("scheduler_started_no_mysql")
            except Exception as e:
                logger.warning("scheduler_start_failed", error=str(e))

            # 尝试创建 Agent
            try:
                _agent, _backend = await create_agent(checkpointer=None, store=InMemoryStore())
            except Exception as agent_error:
                logger.warning("agent_creation_failed", error=str(agent_error))
                _agent = None
                _backend = None

        # 设置沙箱后端引用（用于下载路由和报告工具）
        if _backend:
            set_download_backend(_backend)
            set_report_backend(_backend)
            logger.info("sandbox_backend_set", sandbox_id=_backend.id, for_download=True, for_report=True)
        else:
            logger.warning("sandbox_backend_not_available", message="聊天功能可能受限，但业务API正常")

        logger.info("application_started", sandbox_id=_backend.id if _backend else "none", agent_available=_agent is not None)
        yield

    except Exception as e:
        import traceback
        full_error = traceback.format_exc()
        logger.error("lifespan_init_failed",
                     error=str(e),
                     error_type=type(e).__name__,
                     traceback=full_error)
        print(f"\n[LIFESPAN ERROR] 初始化失败")
        print(f"Error: {str(e)}")
        print(f"Traceback:\n{full_error}\n")
        raise

    finally:
        # 停止调度器
        try:
            await stop_scheduler()
            logger.info("scheduler_stopped")
        except Exception as e:
            logger.warning("scheduler_stop_failed", error=str(e))

        # 关闭 Redis 连接池
        try:
            await close_redis_pool()
            logger.info("redis_pool_closed")
        except Exception as e:
            logger.warning("redis_pool_close_failed", error=str(e))

        # 清理 MySQL 连接池
        if _mysql_pool is not None:
            try:
                _mysql_pool.close()
                await _mysql_pool.wait_closed()
                logger.info("mysql_pool_closed")
            except Exception as e:
                logger.warning("mysql_pool_close_failed", error=str(e))
            _mysql_pool = None

    logger.info("lifespan_end")


app = FastAPI(
    title="OSINT Agent",
    version="3.0.0",
    lifespan=lifespan
)

# 注册下载路由
app.include_router(download_router)

# 注册业务路由
app.include_router(scanner_router)
app.include_router(findings_router)
app.include_router(scheduled_task_router)
app.include_router(channel_router)

logger.info("fastapi_app_created", title="OSINT Agent", version="3.0.0")


@app.post("/api/osint/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口（SSE）。

    支持高并发配置：
    - SSE_MAX_CONNECTIONS: 最大并发连接数（默认 500）
    - 超过限制时返回 429 错误
    """
    if not _agent:
        logger.error("agent_not_ready")
        raise HTTPException(status_code=503, detail="Agent not ready")

    session_id = request.session_id or f"session_{uuid.uuid4().hex[:8]}"

    # 检查 SSE 连接数限制
    acquired = await acquire_sse_connection(session_id)
    if not acquired:
        sse_stats = get_sse_stats()
        logger.warning("sse_connection_rejected",
                      session_id=session_id,
                      active=sse_stats["active_connections"],
                      max=sse_stats["max_connections"])
        raise HTTPException(
            status_code=429,
            detail=f"达到最大并发连接数限制 ({sse_stats['max_connections']})，请稍后重试"
        )

    # 配置：降低 recursion_limit 防止复杂任务无限循环，配合批量工具提升效率
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": 50  # 默认 25，调整为 50（使用批量工具后无需太高）
    }

    logger.info("chat_stream_start",
                session_id=session_id,
                message_length=len(request.message),
                sse_stats=get_sse_stats())

    async def event_generator():
        # 设置当前 session（用于进度推送）
        set_current_session(session_id)
        logger.info("session_set_for_progress", session_id=session_id)

        # 暂停沙箱健康检查（避免打断流式对话）
        sandbox_manager = SandboxManager.get_instance()
        sandbox_manager.pause_health_check()

        # 发送流开始事件
        yield f"data: {json.dumps({'type':'start','data':{'session_id':session_id}})}\n\n"
        logger.info("stream_started", session_id=session_id)

        # 获取进度队列
        progress_queue = get_progress_queue(session_id)

        # 创建一个任务来定期检查进度队列
        progress_events = asyncio.Queue()
        polling_active = True

        async def poll_progress():
            """后台任务：持续轮询进度队列并放入本地队列。"""
            while polling_active:
                try:
                    event = await asyncio.wait_for(progress_queue.get(), timeout=0.3)
                    await progress_events.put(event)
                    logger.debug("progress_event_received", session_id=session_id)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.warning("progress_poll_error", error=str(e))
                    break

        # 启动进度轮询任务
        poll_task = asyncio.create_task(poll_progress())

        try:
            logger.info("agent_stream_calling", session_id=session_id)

            # 使用原始的 async for 循环处理 agent 事件
            async for event in _agent.astream_events(
                {"messages": [{"role": "user", "content": request.message}]},
                config=config,
                version="v2"
            ):
                # 先发送任何待处理的进度事件
                while not progress_events.empty():
                    try:
                        progress_event = progress_events.get_nowait()
                        yield f"data: {json.dumps({'type':'repo_status','data':progress_event.get('data', {})})}\n\n"
                        logger.debug("progress_event_sent", session_id=session_id)
                    except asyncio.QueueEmpty:
                        break

                # 处理 agent 事件
                event_type = event["event"]
                data = event.get("data", {})

                logger.debug("stream_event", session_id=session_id, event_type=event_type)

                if event_type == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        yield f"data: {json.dumps({'type':'token','data':{'content':chunk.content}})}\n\n"

                elif event_type == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = data.get("input", {})
                    logger.info("tool_call_started", session_id=session_id, tool=tool_name)
                    yield f"data: {json.dumps({'type':'tool_call','data':{'tool':tool_name,'input':tool_input}})}\n\n"

                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    output = data.get("output", "")
                    logger.info("tool_call_ended", session_id=session_id, tool=tool_name)
                    yield f"data: {json.dumps({'type':'tool_result','data':{'tool':tool_name,'output':str(output)}})}\n\n"

                elif event_type == "on_chain_start":
                    chain_name = data.get("name", "unknown")
                    if "agent" in chain_name.lower():
                        logger.info("chain_started", session_id=session_id, chain_name=chain_name)
                        yield f"data: {json.dumps({'type':'thinking','data':{'agent':chain_name}})}\n\n"

            # Agent 结束，停止进度轮询
            polling_active = False
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass

            # 发送剩余进度事件
            while not progress_events.empty():
                try:
                    progress_event = progress_events.get_nowait()
                    yield f"data: {json.dumps({'type':'repo_status','data':progress_event.get('data', {})})}\n\n"
                except asyncio.QueueEmpty:
                    break

            # 发送流结束事件
            yield f"data: {json.dumps({'type':'end','data':{'session_id':session_id}})}\n\n"
            logger.info("stream_ended", session_id=session_id)

        except (GeneratorExit, asyncio.CancelledError) as e:
            # 客户端断开连接，正常清理
            logger.info("stream_client_disconnected",
                         session_id=session_id,
                         error_type=type(e).__name__)
            polling_active = False
            if poll_task:
                poll_task.cancel()
            # 清理进度队列
            remove_progress_queue(session_id)
            return

        except Exception as e:
            # 输出完整错误堆栈
            import traceback
            full_error = traceback.format_exc()
            logger.error("stream_error",
                         session_id=session_id,
                         error=str(e),
                         error_type=type(e).__name__,
                         traceback=full_error)
            print(f"\n[STREAM ERROR] Session: {session_id}")
            print(f"Error Type: {type(e).__name__}")
            print(f"Error Message: {str(e)}")
            print(f"Full Traceback:\n{full_error}\n")
            polling_active = False
            if poll_task:
                poll_task.cancel()
            # 清理进度队列
            remove_progress_queue(session_id)
            # 尝试发送错误消息（如果客户端还在线）
            try:
                yield f"data: {json.dumps({'type':'error','data':{'code':500,'message':str(e),'traceback':full_error}})}\n\n"
            except (GeneratorExit, asyncio.CancelledError):
                # 发送失败，客户端已断开
                pass

        finally:
            # 恢复沙箱健康检查
            sandbox_manager = SandboxManager.get_instance()
            sandbox_manager.resume_health_check()
            # 确保清理进度队列
            remove_progress_queue(session_id)
            # 释放 SSE 连接槽位
            await release_sse_connection(session_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/osint/subagents")
async def list_subagents():
    """列出所有可用子Agent。"""
    if not _agent:
        logger.error("subagents_list_failed", reason="agent_not_ready")
        raise HTTPException(status_code=503, detail="Agent not ready")

    subagents_info = [{"name": s["name"], "description": s.get("description", "")} for s in _agent.subagents]
    logger.info("subagents_listed", count=len(subagents_info))
    return {"code": 0, "data": subagents_info}


@app.get("/health")
async def health():
    """健康检查。"""
    redis_status = await check_redis_health()
    sse_stats = get_sse_stats()
    status = {
        "status": "ok",
        "agent_ready": _agent is not None,
        "redis": redis_status,
        "sse": sse_stats,
    }
    logger.debug("health_check", **status)
    return status


@app.get("/api/osint/sse/stats")
async def sse_status():
    """SSE 连接状态查询。

    返回当前 SSE 连接数、最大连接数、利用率等信息。
    """
    stats = get_sse_stats()
    return {"code": 0, "data": stats}


@app.get("/api/osint/dashboard")
async def dashboard():
    """系统统计仪表板。

    返回完整的系统状态信息，用于监控和运维。
    """
    from app.llm_config import get_llm_semaphore

    sse_stats = get_sse_stats()
    llm_semaphore = get_llm_semaphore()
    redis_status = await check_redis_health()

    dashboard_data = {
        "agent": {
            "ready": _agent is not None,
            "sandbox_id": _backend.id if _backend else None,
        },
        "sse": sse_stats,
        "llm": {
            "max_concurrency": llm_semaphore._value + sse_stats["active_connections"],
            "current_available": llm_semaphore._value,
        },
        "redis": redis_status,
        "mysql": {
            "pool_maxsize": int(os.getenv("MYSQL_POOL_MAXSIZE", "50")),
        },
    }

    return {"code": 0, "data": dashboard_data}