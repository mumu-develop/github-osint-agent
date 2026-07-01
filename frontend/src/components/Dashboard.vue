<template>
  <div class="dashboard">
    <div class="dashboard-header">
      <h1>OSINT 情报看板</h1>
      <div class="header-actions">
        <button class="scan-btn" @click="handleTriggerScan" :disabled="scanning">
          {{ scanning ? '扫描中...' : '触发扫描' }}
        </button>
        <span class="last-update">最后更新: {{ lastUpdate }}</span>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card critical clickable" @click="handleStatClick('CRITICAL')">
        <div class="stat-icon">🔴</div>
        <div class="stat-content">
          <span class="stat-value">{{ stats.by_severity?.CRITICAL || 0 }}</span>
          <span class="stat-label">严重</span>
        </div>
      </div>
      <div class="stat-card high clickable" @click="handleStatClick('HIGH')">
        <div class="stat-icon">🟠</div>
        <div class="stat-content">
          <span class="stat-value">{{ stats.by_severity?.HIGH || 0 }}</span>
          <span class="stat-label">高危</span>
        </div>
      </div>
      <div class="stat-card medium clickable" @click="handleStatClick('MEDIUM')">
        <div class="stat-icon">🟡</div>
        <div class="stat-content">
          <span class="stat-value">{{ stats.by_severity?.MEDIUM || 0 }}</span>
          <span class="stat-label">中危</span>
        </div>
      </div>
      <div class="stat-card info clickable" @click="handleUnacknowledgedClick()">
        <div class="stat-icon">🔵</div>
        <div class="stat-content">
          <span class="stat-value">{{ stats.unacknowledged || 0 }}</span>
          <span class="stat-label">未处理</span>
        </div>
      </div>
    </div>

    <!-- 类型分布 -->
    <div class="distribution-section">
      <h2>发现类型分布</h2>
      <div class="type-bars">
        <div class="type-bar" v-for="(count, type) in stats.by_type" :key="type">
          <span class="type-label">{{ type }}</span>
          <div class="bar-container">
            <div class="bar-fill" :style="{ width: getBarWidth(count) }"></div>
          </div>
          <span class="type-count">{{ count }}</span>
        </div>
      </div>
    </div>

    <!-- 最近发现 -->
    <div class="recent-section">
      <h2>最近发现</h2>
      <div class="findings-list" v-if="recentFindings.length">
        <div class="finding-item" v-for="f in recentFindings" :key="f.id">
          <span class="severity-badge" :class="f.severity.toLowerCase()">{{ f.severity }}</span>
          <div class="finding-content">
            <span class="repo-name">{{ f.repo_full_name }}</span>
            <span class="finding-title">{{ f.title }}</span>
          </div>
          <span class="finding-time">{{ formatTime(f.created_at) }}</span>
        </div>
      </div>
      <div class="empty-state" v-else>
        <p>暂无发现记录</p>
      </div>
    </div>

    <!-- 扫描任务状态 -->
    <div class="scan-status-section" v-if="scanStatus">
      <h2>扫描状态</h2>
      <div class="status-card">
        <div class="status-header">
          <span class="run-id">{{ scanStatus.run_id }}</span>
          <span class="status-badge" :class="scanStatus.status">{{ getStatusText(scanStatus.status) }}</span>
        </div>
        <div class="status-progress">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: getScanProgress(scanStatus) }"></div>
          </div>
          <span class="progress-text">
            {{ scanStatus.scanned_repos }} / {{ scanStatus.total_repos }} 仓库
          </span>
        </div>
        <div class="status-stats">
          <span>发现问题: {{ scanStatus.findings_count }}</span>
          <span class="phase-info" v-if="scanStatus.phase">
            | 阶段: {{ getPhaseText(scanStatus.phase) }}
          </span>
        </div>
        <!-- 告警推送状态 -->
        <div class="alert-status-section" v-if="scanStatus.alert_status">
          <div class="alert-status-header">
            <span class="alert-label">告警推送状态:</span>
            <span class="alert-status-badge" :class="scanStatus.alert_status">
              {{ getAlertStatusText(scanStatus.alert_status) }}
            </span>
          </div>
          <div class="alert-details" v-if="scanStatus.alert_status === 'sent'">
            <span class="alert-detail">推送发现数: {{ scanStatus.alert_findings_count || 0 }}</span>
            <span class="alert-detail" v-if="scanStatus.alert_sent_at">
              | 推送时间: {{ formatTime(scanStatus.alert_sent_at) }}
            </span>
          </div>
          <div class="alert-details warning" v-if="scanStatus.alert_status === 'failed'">
            <span class="alert-error">{{ scanStatus.alert_error || '推送失败' }}</span>
          </div>
          <div class="alert-details info" v-if="scanStatus.alert_status === 'skipped'">
            <span class="alert-info">{{ scanStatus.alert_error || '按规则不推送' }}</span>
          </div>
        </div>
        <!-- 任务控制按钮 -->
        <div class="task-controls">
          <!-- running 状态: 暂停/取消 -->
          <button
            v-if="scanStatus.status === 'running'"
            class="control-btn pause"
            @click="handlePauseScan"
            :disabled="controlLoading"
          >
            {{ controlLoading ? '处理中...' : '暂停' }}
          </button>
          <button
            v-if="scanStatus.status === 'running'"
            class="control-btn cancel"
            @click="handleCancelScan"
            :disabled="controlLoading"
          >
            {{ controlLoading ? '处理中...' : '取消' }}
          </button>
          <!-- paused 状态: 恢复/取消 -->
          <button
            v-if="scanStatus.status === 'paused'"
            class="control-btn resume"
            @click="handleResumeScan"
            :disabled="controlLoading"
          >
            {{ controlLoading ? '处理中...' : '恢复' }}
          </button>
          <button
            v-if="scanStatus.status === 'paused'"
            class="control-btn cancel"
            @click="handleCancelScan"
            :disabled="controlLoading"
          >
            {{ controlLoading ? '处理中...' : '取消' }}
          </button>
          <!-- running 但可能是卡住的状态: 强制重置 -->
          <button
            v-if="scanStatus.status === 'running'"
            class="control-btn force-reset"
            @click="handleForceReset"
            :disabled="controlLoading"
          >
            强制重置
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, defineEmits } from 'vue'
import {
  getFindingsStats,
  getRecentFindings,
  triggerScan,
  getScanStatus,
  pauseScan,
  resumeScan,
  cancelScan,
  forceResetScan
} from '../api/dashboard.js'

const emit = defineEmits(['switch-view', 'filter-alerts'])

const stats = ref({})
const recentFindings = ref([])
const lastUpdate = ref('')
const scanning = ref(false)
const scanStatus = ref(null)
const controlLoading = ref(false)
let refreshTimer = null
let scanPollTimer = null  // 扫描状态轮询定时器

// 点击统计卡片跳转到预警列表
function handleStatClick(severity) {
  emit('switch-view', 'alerts')
  emit('filter-alerts', { severity })
}

function handleUnacknowledgedClick() {
  emit('switch-view', 'alerts')
  emit('filter-alerts', { is_acknowledged: false })
}

async function loadDashboard() {
  try {
    stats.value = await getFindingsStats()
    const recentData = await getRecentFindings(24)
    recentFindings.value = recentData.findings || []
    lastUpdate.value = new Date().toLocaleTimeString()
  } catch (e) {
    console.error('加载仪表板失败:', e)
  }
}

async function handleTriggerScan() {
  scanning.value = true
  try {
    const result = await triggerScan('L1_LIGHT')
    scanStatus.value = result
    // 开始轮询状态
    pollScanStatus(result.run_id)
  } catch (e) {
    console.error('触发扫描失败:', e)
    scanning.value = false
  }
}

async function pollScanStatus(runId) {
  // 清除之前的轮询
  if (scanPollTimer) {
    clearInterval(scanPollTimer)
    scanPollTimer = null
  }

  // 立即获取一次
  const poll = async () => {
    try {
      const status = await getScanStatus(runId)
      scanStatus.value = status

      if (status.status === 'completed' || status.status === 'failed') {
        scanning.value = false
        clearInterval(scanPollTimer)
        scanPollTimer = null
        // 刷新仪表板
        await loadDashboard()
      }
    } catch (e) {
      console.error('获取扫描状态失败:', e)
      scanning.value = false
      clearInterval(scanPollTimer)
      scanPollTimer = null
    }
  }

  poll()
  // 每2秒轮询
  scanPollTimer = setInterval(poll, 2000)
}

function getStatusText(status) {
  const statusMap = {
    'running': '运行中',
    'paused': '已暂停',
    'completed': '已完成',
    'failed': '失败',
    'cancelled': '已取消',
    'pending': '等待中'
  }
  return statusMap[status] || status
}

function getPhaseText(phase) {
  const phaseMap = {
    'init': '初始化',
    'scanning': '扫描中',
    'llm_analysis': 'LLM分析',
    'generating_report': '生成报告',
    'alert_sending': '发送告警',
    'done': '完成'
  }
  return phaseMap[phase] || phase
}

function getAlertStatusText(alertStatus) {
  const alertStatusMap = {
    'pending': '等待推送',
    'sending': '正在推送',
    'sent': '已推送',
    'skipped': '已跳过',
    'failed': '推送失败'
  }
  return alertStatusMap[alertStatus] || alertStatus
}

async function handlePauseScan() {
  if (!scanStatus.value) return
  controlLoading.value = true
  try {
    await pauseScan(scanStatus.value.run_id)
    // 立即刷新状态
    const status = await getScanStatus(scanStatus.value.run_id)
    scanStatus.value = status
  } catch (e) {
    console.error('暂停扫描失败:', e)
    alert(e.message || '暂停失败')
  } finally {
    controlLoading.value = false
  }
}

async function handleResumeScan() {
  if (!scanStatus.value) return
  controlLoading.value = true
  try {
    const result = await resumeScan(scanStatus.value.run_id)
    // 恢复后继续轮询
    scanStatus.value.status = 'running'
    scanning.value = true
    pollScanStatus(scanStatus.value.run_id)
  } catch (e) {
    console.error('恢复扫描失败:', e)
    alert(e.message || '恢复失败')
  } finally {
    controlLoading.value = false
  }
}

async function handleCancelScan() {
  if (!scanStatus.value) return
  if (!confirm('确定要取消此扫描任务吗？')) return
  controlLoading.value = true
  try {
    await cancelScan(scanStatus.value.run_id)
    // 立即刷新状态
    const status = await getScanStatus(scanStatus.value.run_id)
    scanStatus.value = status
    scanning.value = false
    // 停止轮询
    if (scanPollTimer) {
      clearInterval(scanPollTimer)
      scanPollTimer = null
    }
  } catch (e) {
    console.error('取消扫描失败:', e)
    alert(e.message || '取消失败')
  } finally {
    controlLoading.value = false
  }
}

async function handleForceReset() {
  if (!scanStatus.value) return
  if (!confirm('此操作将强制将任务标记为失败状态（用于服务异常终止后状态卡住的情况）。\n\n确定要强制重置吗？')) return
  controlLoading.value = true
  try {
    await forceResetScan(scanStatus.value.run_id)
    // 立即刷新状态
    const status = await getScanStatus(scanStatus.value.run_id)
    scanStatus.value = status
    scanning.value = false
    // 停止轮询
    if (scanPollTimer) {
      clearInterval(scanPollTimer)
      scanPollTimer = null
    }
    alert('任务已强制重置为失败状态，可以重新触发新任务')
  } catch (e) {
    console.error('强制重置失败:', e)
    alert(e.message || '强制重置失败')
  } finally {
    controlLoading.value = false
  }
}

function getBarWidth(count) {
  const max = Math.max(...Object.values(stats.value.by_type || {}), 1)
  return `${(count / max) * 100}%`
}

function getScanProgress(status) {
  if (!status.total_repos) return '0%'
  return `${(status.scanned_repos / status.total_repos) * 100}%`
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return date.toLocaleDateString()
}

onMounted(() => {
  loadDashboard()
  // 每5分钟自动刷新
  refreshTimer = setInterval(loadDashboard, 300000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (scanPollTimer) clearInterval(scanPollTimer)
})
</script>

<style scoped>
.dashboard {
  padding: 24px;
  background: #f8fafc;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.dashboard-header h1 {
  font-size: 24px;
  color: #1e293b;
}

.header-actions {
  display: flex;
  gap: 16px;
  align-items: center;
}

.scan-btn {
  padding: 12px 24px;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
}

.scan-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.last-update {
  font-size: 12px;
  color: #94a3b8;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: white;
  padding: 20px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.stat-icon {
  font-size: 32px;
}

.stat-content {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
}

.stat-label {
  font-size: 14px;
  color: #64748b;
}

.stat-card.critical { border-left: 4px solid #dc2626; }
.stat-card.high { border-left: 4px solid #ea580c; }
.stat-card.medium { border-left: 4px solid #eab308; }
.stat-card.info { border-left: 4px solid #3b82f6; }

.stat-card.clickable {
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card.clickable:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.stat-card.clickable:active {
  transform: translateY(0);
}

.distribution-section,
.recent-section,
.scan-status-section {
  background: white;
  padding: 20px;
  border-radius: 12px;
  margin-bottom: 24px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.distribution-section h2,
.recent-section h2,
.scan-status-section h2 {
  font-size: 18px;
  color: #1e293b;
  margin-bottom: 16px;
}

.type-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.type-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.type-label {
  width: 80px;
  font-size: 14px;
  color: #64748b;
}

.bar-container {
  flex: 1;
  height: 24px;
  background: #f1f5f9;
  border-radius: 4px;
}

.bar-fill {
  height: 100%;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  border-radius: 4px;
  transition: width 0.3s;
}

.type-count {
  width: 40px;
  font-size: 14px;
  color: #1e293b;
  font-weight: 600;
}

.findings-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.finding-item {
  display: flex;
  align-items: center;
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
  gap: 12px;
}

.severity-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.severity-badge.critical { background: #fef2f2; color: #dc2626; }
.severity-badge.high { background: #fff7ed; color: #ea580c; }
.severity-badge.medium { background: #fefce8; color: #eab308; }
.severity-badge.low { background: #f0fdf4; color: #22c55e; }
.severity-badge.info { background: #eff6ff; color: #3b82f6; }

.finding-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.repo-name {
  font-size: 12px;
  color: #64748b;
}

.finding-title {
  font-size: 14px;
  color: #1e293b;
}

.finding-time {
  font-size: 12px;
  color: #94a3b8;
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: #94a3b8;
}

.status-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
}

.status-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

.run-id {
  font-size: 14px;
  color: #64748b;
}

.status-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.status-badge.running { background: #dbeafe; color: #2563eb; }
.status-badge.completed { background: #dcfce7; color: #16a34a; }
.status-badge.failed { background: #fef2f2; color: #dc2626; }
.status-badge.paused { background: #fef3c7; color: #b45309; }
.status-badge.cancelled { background: #f1f5f9; color: #64748b; }
.status-badge.pending { background: #e0e7ff; color: #6366f1; }

.status-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: #f1f5f9;
  border-radius: 4px;
}

.progress-fill {
  height: 100%;
  background: #0ea5e9;
  border-radius: 4px;
  transition: width 0.3s;
}

.progress-text {
  font-size: 12px;
  color: #64748b;
}

.status-stats {
  font-size: 14px;
  color: #1e293b;
}

.task-controls {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
}

.control-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}

.control-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.control-btn.pause {
  background: #fef3c7;
  color: #b45309;
}

.control-btn.pause:hover:not(:disabled) {
  background: #fde68a;
}

.control-btn.resume {
  background: #d1fae5;
  color: #065f46;
}

.control-btn.resume:hover:not(:disabled) {
  background: #a7f3d0;
}

.control-btn.cancel {
  background: #fee2e2;
  color: #dc2626;
}

.control-btn.cancel:hover:not(:disabled) {
  background: #fecaca;
}

.control-btn.force-reset {
  background: #f1f5f9;
  color: #64748b;
  border: 1px dashed #94a3b8;
}

.control-btn.force-reset:hover:not(:disabled) {
  background: #e2e8f0;
  color: #475569;
}

/* 告警状态样式 */
.alert-status-section {
  margin-top: 12px;
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
}

.alert-status-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.alert-label {
  font-size: 13px;
  color: #64748b;
}

.alert-status-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.alert-status-badge.sent { background: #dcfce7; color: #16a34a; }
.alert-status-badge.sending { background: #dbeafe; color: #2563eb; }
.alert-status-badge.skipped { background: #f1f5f9; color: #64748b; }
.alert-status-badge.failed { background: #fef2f2; color: #dc2626; }
.alert-status-badge.pending { background: #e0e7ff; color: #6366f1; }

.alert-details {
  margin-top: 8px;
  font-size: 12px;
  color: #64748b;
}

.alert-details.warning {
  color: #dc2626;
}

.alert-details.info {
  color: #64748b;
}

.alert-detail {
  display: inline;
}

.alert-error {
  color: #dc2626;
}

.alert-info {
  color: #94a3b8;
}

.phase-info {
  color: #94a3b8;
}
</style>