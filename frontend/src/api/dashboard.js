/**
 * 仪表板 API 模块
 *
 * 重构说明：
 * - 移除旧的 orgs API（已废弃）
 * - 新增 scheduled-task API（定时任务管理）
 */

const API_BASE = '/api'

/**
 * 获取发现统计
 */
export async function getFindingsStats() {
  const response = await fetch(`${API_BASE}/findings/stats`)
  if (!response.ok) throw new Error('获取统计失败')
  const data = await response.json()
  return data.data
}

/**
 * 获取最近发现
 */
export async function getRecentFindings(hours = 24) {
  const response = await fetch(`${API_BASE}/findings/recent?hours=${hours}`)
  if (!response.ok) throw new Error('获取最近发现失败')
  const data = await response.json()
  return data.data
}

/**
 * 获取发现列表
 */
export async function getFindings(params = {}) {
  const query = new URLSearchParams(params).toString()
  const response = await fetch(`${API_BASE}/findings?${query}`)
  if (!response.ok) throw new Error('获取发现列表失败')
  const data = await response.json()
  return data.data
}

/**
 * 确认发现
 */
export async function acknowledgeFinding(findingId) {
  const response = await fetch(`${API_BASE}/findings/${findingId}/acknowledge`, {
    method: 'POST'
  })
  if (!response.ok) throw new Error('确认失败')
  return response.json()
}

/**
 * 触发扫描
 */
export async function triggerScan(scanType, orgName = null) {
  const response = await fetch(`${API_BASE}/scanner/trigger`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scan_type: scanType, org_name: orgName })
  })
  if (!response.ok) throw new Error('触发扫描失败')
  const data = await response.json()
  return data.data
}

/**
 * 获取扫描状态
 */
export async function getScanStatus(runId) {
  const response = await fetch(`${API_BASE}/scanner/status/${runId}`)
  if (!response.ok) throw new Error('获取扫描状态失败')
  const data = await response.json()
  return data.data
}

/**
 * 扫描器健康检查
 */
export async function getScannerHealth() {
  const response = await fetch(`${API_BASE}/scanner/health`)
  if (!response.ok) throw new Error('扫描器健康检查失败')
  const data = await response.json()
  return data.data
}

/**
 * 获取扫描任务列表
 */
export async function getScanTasks(page = 1, pageSize = 20) {
  const response = await fetch(`${API_BASE}/scanner/list?page=${page}&page_size=${pageSize}`)
  if (!response.ok) throw new Error('获取扫描任务失败')
  const data = await response.json()
  return data.data
}

/**
 * 获取扫描子任务进度（仓库级详情）
 */
export async function getSubtaskProgress(runId, status = null) {
  const statusParam = status ? `?status=${status}` : ''
  const response = await fetch(`${API_BASE}/scanner/subtasks/${runId}${statusParam}`)
  if (!response.ok) throw new Error('获取子任务进度失败')
  const data = await response.json()
  return data.data
}

/**
 * 获取扫描进度统计
 */
export async function getScanProgress(runId) {
  const response = await fetch(`${API_BASE}/scanner/progress/${runId}`)
  if (!response.ok) throw new Error('获取扫描进度失败')
  const data = await response.json()
  return data.data
}

/**
 * 暂停扫描任务
 */
export async function pauseScan(runId) {
  const response = await fetch(`${API_BASE}/scanner/pause/${runId}`, {
    method: 'POST'
  })
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: '暂停扫描失败' }))
    throw new Error(errorData.detail || '暂停扫描失败')
  }
  const data = await response.json()
  return data.data
}

/**
 * 恢复扫描任务
 */
export async function resumeScan(runId) {
  const response = await fetch(`${API_BASE}/scanner/resume/${runId}`, {
    method: 'POST'
  })
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: '恢复扫描失败' }))
    throw new Error(errorData.detail || '恢复扫描失败')
  }
  const data = await response.json()
  return data.data
}

/**
 * 取消扫描任务
 */
export async function cancelScan(runId, reason = '用户取消') {
  const response = await fetch(`${API_BASE}/scanner/cancel/${runId}?reason=${encodeURIComponent(reason)}`, {
    method: 'POST'
  })
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: '取消扫描失败' }))
    throw new Error(errorData.detail || '取消扫描失败')
  }
  const data = await response.json()
  return data.data
}

/**
 * 强制重置卡住的扫描任务
 */
export async function forceResetScan(runId) {
  const response = await fetch(`${API_BASE}/scanner/force-reset/${runId}`, {
    method: 'POST'
  })
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: '强制重置失败' }))
    throw new Error(errorData.detail || '强制重置失败')
  }
  const data = await response.json()
  return data.data
}

// ==================== 定时任务管理 API ====================

/**
 * 获取定时任务列表
 */
export async function getScheduledTasks(params = {}) {
  const query = new URLSearchParams(params).toString()
  const url = query ? `${API_BASE}/scheduled-task/list?${query}` : `${API_BASE}/scheduled-task/list`
  const response = await fetch(url)
  if (!response.ok) throw new Error('获取定时任务失败')
  const data = await response.json()
  return data.data
}

/**
 * 获取定时任务详情
 */
export async function getScheduledTask(taskId) {
  const response = await fetch(`${API_BASE}/scheduled-task/${taskId}`)
  if (!response.ok) throw new Error('获取任务详情失败')
  const data = await response.json()
  return data.data
}

/**
 * 获取任务执行历史（简要列表）
 */
export async function getTaskExecutions(taskId, limit = 20) {
  const response = await fetch(`${API_BASE}/scheduled-task/${taskId}/executions?limit=${limit}`)
  if (!response.ok) throw new Error('获取执行历史失败')
  const data = await response.json()
  return data.data
}

/**
 * 获取执行详情（完整数据：tool_calls、agent_output、execution_log）
 */
export async function getExecutionDetail(runId) {
  const response = await fetch(`${API_BASE}/scheduled-task/executions/${runId}`)
  if (!response.ok) throw new Error('获取执行详情失败')
  const data = await response.json()
  return data.data
}

/**
 * 暂停定时任务
 */
export async function pauseScheduledTask(taskId) {
  const response = await fetch(`${API_BASE}/scheduled-task/${taskId}/pause`, {
    method: 'POST'
  })
  if (!response.ok) throw new Error('暂停任务失败')
  const data = await response.json()
  return data.data
}

/**
 * 恢复定时任务
 */
export async function resumeScheduledTask(taskId) {
  const response = await fetch(`${API_BASE}/scheduled-task/${taskId}/resume`, {
    method: 'POST'
  })
  if (!response.ok) throw new Error('恢复任务失败')
  const data = await response.json()
  return data.data
}

/**
 * 删除定时任务
 */
export async function deleteScheduledTask(taskId) {
  const response = await fetch(`${API_BASE}/scheduled-task/${taskId}`, {
    method: 'DELETE'
  })
  if (!response.ok) throw new Error('删除任务失败')
  const data = await response.json()
  return data.data
}

/**
 * 手动触发任务执行
 */
export async function triggerScheduledTask(taskId) {
  const response = await fetch(`${API_BASE}/scheduled-task/${taskId}/run`, {
    method: 'POST'
  })
  if (!response.ok) throw new Error('触发任务失败')
  const data = await response.json()
  return data.data
}

/**
 * 更新告警渠道配置
 */
export async function updateAlertChannels(taskId, channels) {
  const response = await fetch(`${API_BASE}/scheduled-task/${taskId}/alert-channels`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(channels)
  })
  if (!response.ok) throw new Error('更新渠道配置失败')
  const data = await response.json()
  return data.data
}

/**
 * SSE 进度推送连接（定时任务）
 * @param {number} taskId 任务 ID
 * @param {object} callbacks 回调函数
 * @returns {function} 关闭连接的函数
 */
export function connectScheduledTaskProgress(taskId, callbacks = {}) {
  const url = `${API_BASE}/scheduled-task/${taskId}/progress-stream`
  const es = new EventSource(url)

  console.log('[SSE] Connecting to task:', taskId)

  es.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data)
      const { type, data } = event

      console.log('[SSE] Event:', type, data)

      switch(type) {
        case 'init':
          callbacks.onInit?.(data)
          break
        case 'start':
          callbacks.onStart?.(data)
          break
        case 'tool_start':
          callbacks.onToolStart?.(data)
          break
        case 'tool_end':
          callbacks.onToolEnd?.(data)
          break
        case 'repo_start':
          callbacks.onRepoStart?.(data)
          break
        case 'repo_done':
          callbacks.onRepoDone?.(data)
          break
        case 'done':
          callbacks.onDone?.(data)
          es.close()
          break
        case 'error':
          callbacks.onError?.(data.error || '任务执行失败')
          es.close()
          break
        case 'heartbeat':
          callbacks.onHeartbeat?.(data.timestamp)
          break
      }
    } catch (err) {
      console.error('[SSE] Parse error:', err)
    }
  }

  es.onerror = (e) => {
    console.error('[SSE] Connection error:', e)
    if (es.readyState === EventSource.CLOSED) {
      callbacks.onDisconnected?.()
    } else {
      callbacks.onError?.('SSE 连接错误')
    }
    es.close()
  }

  return () => {
    console.log('[SSE] Closing connection')
    es.close()
  }
}

// ==================== 告警渠道管理 API ====================

/**
 * 获取告警渠道列表
 */
export async function getChannels(channelType = null) {
  const url = channelType ? `${API_BASE}/channel/list?channel_type=${channelType}` : `${API_BASE}/channel/list`
  const response = await fetch(url)
  if (!response.ok) throw new Error('获取渠道列表失败')
  const data = await response.json()
  return data.data
}

/**
 * 获取启用的渠道列表（用于任务绑定）
 */
export async function getEnabledChannels() {
  const response = await fetch(`${API_BASE}/channel/enabled`)
  if (!response.ok) throw new Error('获取可用渠道失败')
  const data = await response.json()
  return data.data
}

/**
 * 创建告警渠道
 */
export async function createChannel(channelData) {
  const response = await fetch(`${API_BASE}/channel/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(channelData)
  })
  if (!response.ok) throw new Error('创建渠道失败')
  const data = await response.json()
  return data.data
}

/**
 * 获取渠道详情
 */
export async function getChannel(channelId) {
  const response = await fetch(`${API_BASE}/channel/${channelId}`)
  if (!response.ok) throw new Error('获取渠道详情失败')
  const data = await response.json()
  return data.data
}

/**
 * 更新渠道配置
 */
export async function updateChannel(channelId, updates) {
  const response = await fetch(`${API_BASE}/channel/${channelId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates)
  })
  if (!response.ok) throw new Error('更新渠道失败')
  const data = await response.json()
  return data.data
}

/**
 * 删除渠道
 */
export async function deleteChannel(channelId) {
  const response = await fetch(`${API_BASE}/channel/${channelId}`, {
    method: 'DELETE'
  })
  if (!response.ok) throw new Error('删除渠道失败')
  const data = await response.json()
  return data.data
}

/**
 * 启用渠道
 */
export async function enableChannel(channelId) {
  const response = await fetch(`${API_BASE}/channel/${channelId}/enable`, {
    method: 'POST'
  })
  if (!response.ok) throw new Error('启用渠道失败')
  const data = await response.json()
  return data.data
}

/**
 * 禁用渠道
 */
export async function disableChannel(channelId) {
  const response = await fetch(`${API_BASE}/channel/${channelId}/disable`, {
    method: 'POST'
  })
  if (!response.ok) throw new Error('禁用渠道失败')
  const data = await response.json()
  return data.data
}

/**
 * 测试渠道（发送测试消息）
 */
export async function testChannel(channelId) {
  const response = await fetch(`${API_BASE}/channel/${channelId}/test`, {
    method: 'POST'
  })
  if (!response.ok) throw new Error('测试渠道失败')
  const data = await response.json()
  return data.data
}

/**
 * 绑定渠道到定时任务
 */
export async function bindChannelsToTask(taskId, channelIds) {
  const response = await fetch(`${API_BASE}/channel/bind-task/${taskId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ channel_ids: channelIds })
  })
  if (!response.ok) throw new Error('绑定渠道失败')
  const data = await response.json()
  return data.data
}