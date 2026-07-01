<template>
  <div class="scheduled-task">
    <div class="task-header">
      <h1>定时任务管理</h1>
      <span class="hint">通过 Agent 对话创建定时扫描任务</span>
    </div>

    <!-- 任务列表 -->
    <div class="task-list">
      <div class="task-item" v-for="task in tasks" :key="task.id" @click="selectTask(task)">
        <div class="task-main">
          <div class="task-info">
            <span class="task-name">{{ task.name }}</span>
            <span class="task-target">{{ task.target }}</span>
            <span class="task-cron">{{ task.cron }}</span>
            <span class="status-badge" :class="task.status">{{ getStatusLabel(task.status) }}</span>
          </div>
          <div class="task-meta">
            <span class="meta-item">下次执行: {{ task.next_run || '未设置' }}</span>
            <span class="meta-item">已执行 {{ task.run_count }} 次</span>
            <span class="meta-item" v-if="task.dimensions?.length">维度: {{ task.dimensions.join(', ') }}</span>
          </div>
        </div>
        <div class="task-actions">
          <button class="action-btn run" @click.stop="handleRun(task.id)" :disabled="running">
            {{ runningTaskId === task.id ? '执行中...' : '执行' }}
          </button>
          <button class="action-btn pause" @click.stop="handlePause(task.id)" v-if="task.status === 'active'">
            暂停
          </button>
          <button class="action-btn resume" @click.stop="handleResume(task.id)" v-if="task.status === 'paused'">
            恢复
          </button>
          <button class="action-btn delete" @click.stop="handleDelete(task.id)">删除</button>
        </div>
      </div>

      <div class="empty-state" v-if="tasks.length === 0 && !loading">
        <p>暂无定时任务</p>
        <p class="hint">在对话中告诉 Agent：「帮我创建一个定时扫描任务，每周一扫描 sofastack 组织的 CVE 漏洞」</p>
      </div>

      <div class="loading-state" v-if="loading">
        <p>加载中...</p>
      </div>
    </div>

    <!-- 任务详情面板 -->
    <div class="task-detail-panel" v-if="selectedTask">
      <div class="panel-header">
        <h2>{{ selectedTask.name }}</h2>
        <button class="close-btn" @click="selectedTask = null">✕</button>
      </div>

      <!-- 任务基本信息 -->
      <div class="task-info-section">
        <div class="info-row">
          <span class="label">任务 ID:</span>
          <span class="value">{{ selectedTask.id }}</span>
        </div>
        <div class="info-row">
          <span class="label">目标:</span>
          <span class="value">{{ selectedTask.target_type }}: {{ selectedTask.target_name }}</span>
        </div>
        <div class="info-row">
          <span class="label">Cron 表达式:</span>
          <span class="value">{{ selectedTask.cron_expression }}</span>
        </div>
        <div class="info-row">
          <span class="label">扫描维度:</span>
          <span class="value">{{ selectedTask.dimensions?.join(', ') || '默认（全部）' }}</span>
        </div>
        <div class="info-row">
          <span class="label">告警阈值:</span>
          <span class="value">{{ selectedTask.alert_threshold }}</span>
        </div>
        <div class="info-row">
          <span class="label">状态:</span>
          <span class="value">
            <span class="status-badge" :class="selectedTask.status">{{ getStatusLabel(selectedTask.status) }}</span>
          </span>
        </div>
        <div class="info-row">
          <span class="label">是否启用:</span>
          <span class="value">{{ selectedTask.enabled ? '✓ 启用' : '○ 禁用' }}</span>
        </div>
        <div class="info-row">
          <span class="label">创建方式:</span>
          <span class="value">{{ selectedTask.created_by === 'agent' ? 'Agent 创建' : '手动创建' }}</span>
        </div>
        <div class="info-row">
          <span class="label">关联对话:</span>
          <span class="value">{{ selectedTask.conversation_id || '无' }}</span>
        </div>
        <div class="info-row">
          <span class="label">下次执行:</span>
          <span class="value">{{ selectedTask.next_run_at ? formatTime(selectedTask.next_run_at) : '未设置' }}</span>
        </div>
        <div class="info-row">
          <span class="label">上次执行:</span>
          <span class="value">
            {{ selectedTask.last_run_at ? formatTime(selectedTask.last_run_at) : '未执行' }}
            <span v-if="selectedTask.last_run_status" class="last-status" :class="selectedTask.last_run_status">
              ({{ selectedTask.last_run_status }})
            </span>
          </span>
        </div>
        <div class="info-row">
          <span class="label">执行次数:</span>
          <span class="value">{{ selectedTask.run_count }} 次</span>
        </div>
        <div class="info-row">
          <span class="label">创建时间:</span>
          <span class="value">{{ selectedTask.created_at ? formatTime(selectedTask.created_at) : '未知' }}</span>
        </div>
        <div class="info-row" v-if="selectedTask.description">
          <span class="label">描述:</span>
          <span class="value">{{ selectedTask.description }}</span>
        </div>
      </div>

      <!-- Agent Prompt（可展开） -->
      <div class="prompt-section">
        <div class="prompt-header" @click="showFullPrompt = !showFullPrompt">
          <span class="label">Agent 执行 Prompt:</span>
          <span class="toggle-btn">{{ showFullPrompt ? '收起' : '展开' }}</span>
        </div>
        <div class="prompt-content" v-if="showFullPrompt">
          <pre>{{ selectedTask.prompt }}</pre>
        </div>
        <div class="prompt-preview" v-else>
          {{ selectedTask.prompt?.slice(0, 150) }}...
        </div>
      </div>

      <!-- 告警渠道配置 -->
      <div class="channels-section">
        <div class="channels-header">
          <h3>
            <span class="section-icon">📢</span>
            告警渠道配置
          </h3>
          <button class="edit-btn" @click="openChannelsEdit">
            <span class="btn-icon">✏️</span>
            编辑
          </button>
        </div>
        <div class="channels-content">
          <!-- 新格式：绑定的渠道 -->
          <div class="bound-channels-list" v-if="selectedTask.alert_channel_ids?.length">
            <div class="bound-channel-card" v-for="channelId in selectedTask.alert_channel_ids" :key="channelId">
              <div class="channel-type-tag" :class="getChannelType(channelId)">
                <span class="type-icon">{{ getChannelTypeIcon(channelId) }}</span>
                <span class="type-name">{{ getChannelTypeLabel(channelId) }}</span>
              </div>
              <div class="channel-info">
                <span class="channel-name">{{ getChannelName(channelId) }}</span>
                <span class="bind-status">✓ 已绑定</span>
              </div>
            </div>
          </div>
          <!-- 旧格式兼容 -->
          <div class="legacy-channels" v-else-if="selectedTask.alert_channels?.dingtalk?.webhook || selectedTask.alert_channels?.feishu?.webhook">
            <div class="bound-channel-card legacy" v-if="selectedTask.alert_channels?.dingtalk?.webhook">
              <div class="channel-type-tag dingtalk">
                <span class="type-icon">🔵</span>
                <span class="type-name">钉钉</span>
              </div>
              <div class="channel-info">
                <span class="channel-name">旧配置</span>
                <span class="bind-status legacy">旧格式</span>
              </div>
            </div>
            <div class="bound-channel-card legacy" v-if="selectedTask.alert_channels?.feishu?.webhook">
              <div class="channel-type-tag feishu">
                <span class="type-icon">🟣</span>
                <span class="type-name">飞书</span>
              </div>
              <div class="channel-info">
                <span class="channel-name">旧配置</span>
                <span class="bind-status legacy">旧格式</span>
              </div>
            </div>
          </div>
          <!-- 未配置 -->
          <div class="no-channel-config" v-else>
            <div class="no-channel-icon">📭</div>
            <p class="no-channel-text">未绑定告警渠道</p>
            <p class="no-channel-hint">执行结果将不会推送通知</p>
          </div>
        </div>
      </div>

      <!-- 渠道配置编辑弹窗 -->
      <div class="channels-modal-overlay" v-if="showChannelsEdit" @click.self="closeChannelsEdit">
        <div class="channels-modal">
          <div class="modal-header-bar">
            <h2 class="modal-title">
              <span class="title-icon">📢</span>
              绑定告警渠道
            </h2>
            <button class="modal-close-btn" @click="closeChannelsEdit">×</button>
          </div>

          <div class="modal-body-content">
            <!-- 选择渠道 -->
            <div class="select-section">
              <p class="select-hint">选择要绑定的告警渠道（可多选）</p>
              <div class="channel-select-grid" v-if="availableChannels.length">
                <div class="channel-select-card"
                     v-for="channel in availableChannels"
                     :key="channel.id"
                     :class="{ selected: selectedChannelIds.includes(channel.id), [channel.channel_type]: true }"
                     @click="toggleChannelSelection(channel.id)">
                  <div class="select-header">
                    <span class="select-checkbox">{{ selectedChannelIds.includes(channel.id) ? '✅' : '⬜' }}</span>
                    <span class="channel-type-badge" :class="channel.channel_type">
                      <span class="badge-icon">{{ getTypeIcon(channel.channel_type) }}</span>
                      <span class="badge-text">{{ getTypeLabel(channel.channel_type) }}</span>
                    </span>
                  </div>
                  <div class="select-body">
                    <span class="select-name">{{ channel.name }}</span>
                    <span class="select-desc" v-if="channel.description">{{ channel.description }}</span>
                  </div>
                </div>
              </div>
              <div class="no-channels-hint" v-else>
                <div class="empty-icon">📭</div>
                <p>暂无可用渠道</p>
                <button class="goto-btn" @click="$emit('goto-channels')">
                  <span class="btn-icon">→</span>
                  前往创建渠道
                </button>
              </div>
            </div>

            <!-- 兼容旧格式 -->
            <div class="legacy-config-section">
              <div class="section-divider">
                <span class="divider-text">或使用旧格式配置</span>
              </div>
              <div class="legacy-form">
                <div class="form-row">
                  <label class="form-label">钉钉 Webhook</label>
                  <input type="text" v-model="editChannels.dingtalk.webhook" placeholder="https://oapi.dingtalk.com/robot/send?access_token=xxx" class="form-input-legacy" />
                </div>
                <div class="form-row">
                  <label class="form-label">钉钉 Secret</label>
                  <input type="text" v-model="editChannels.dingtalk.secret" placeholder="SECxxx（签名密钥，可选）" class="form-input-legacy" />
                </div>
                <div class="form-row">
                  <label class="form-label">飞书 Webhook</label>
                  <input type="text" v-model="editChannels.feishu.webhook" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx" class="form-input-legacy" />
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer-bar">
            <button class="footer-btn cancel" @click="closeChannelsEdit">取消</button>
            <button class="footer-btn save" @click="saveChannels" :disabled="savingChannels">
              {{ savingChannels ? '保存中...' : '保存配置' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 执行历史 -->
      <div class="executions-section">
        <h3>执行历史</h3>
        <div class="executions-list" v-if="executions.length > 0">
          <div class="execution-item" v-for="e in executions" :key="e.id" @click="showExecutionDetail(e)">
            <div class="exec-header">
              <span class="run-id">{{ e.run_id }}</span>
              <span class="exec-status" :class="e.status">{{ getExecStatusLabel(e.status) }}</span>
              <span class="exec-time">{{ formatTime(e.started_at) }}</span>
              <span class="duration">{{ e.duration_seconds }}秒</span>
            </div>
            <div class="exec-stats">
              <span>发现: {{ e.total_findings }}</span>
              <span>高危: {{ e.high_severity_count }}</span>
            </div>
            <div class="exec-error-preview" v-if="e.error_message">
              <span class="error-label">错误:</span>
              <span class="error-text">{{ e.error_message.slice(0, 80) }}...</span>
            </div>
          </div>
        </div>
        <div class="empty-state" v-else>
          <p>暂无执行记录</p>
        </div>
      </div>

      <!-- 执行详情弹窗 -->
      <div class="execution-detail-modal-overlay" v-if="selectedExecution" @click.self="closeExecutionDetail">
        <div class="execution-detail-modal">
          <div class="modal-header-bar">
            <h2 class="modal-title">
              <span class="title-icon">📋</span>
              执行详情
              <span class="live-indicator" v-if="selectedExecution.status === 'running'">● 实时更新</span>
            </h2>
            <button class="modal-close-btn" @click="closeExecutionDetail">×</button>
          </div>

          <div class="modal-body-content">
            <!-- 基本信息 -->
            <div class="detail-section">
              <div class="section-title">基本信息</div>
              <div class="detail-grid">
                <div class="detail-item">
                  <span class="detail-label">Run ID</span>
                  <span class="detail-value">{{ selectedExecution.run_id }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">状态</span>
                  <span class="detail-value">
                    <span class="exec-status" :class="selectedExecution.status">{{ getExecStatusLabel(selectedExecution.status) }}</span>
                  </span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">开始时间</span>
                  <span class="detail-value">{{ formatFullTime(selectedExecution.started_at) }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">完成时间</span>
                  <span class="detail-value">{{ selectedExecution.completed_at ? formatFullTime(selectedExecution.completed_at) : '-' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">执行耗时</span>
                  <span class="detail-value">{{ selectedExecution.duration_seconds }} 秒</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">发现问题</span>
                  <span class="detail-value">{{ selectedExecution.total_findings }} 个（高危 {{ selectedExecution.high_severity_count }} 个）</span>
                </div>
              </div>
            </div>

            <!-- 工具调用记录 -->
            <div class="detail-section" v-if="selectedExecution.tool_calls?.length">
              <div class="section-title">工具调用记录</div>
              <div class="tool-calls-list">
                <div class="tool-call-item" :class="call.status" v-for="(call, idx) in selectedExecution.tool_calls" :key="idx">
                  <div class="tool-call-header">
                    <span class="tool-name">{{ call.tool }}</span>
                    <span class="tool-status" :class="call.status">{{ call.status === 'completed' ? '成功' : '失败' }}</span>
                    <span class="tool-duration">{{ call.duration_ms }}ms</span>
                    <span class="tool-time">{{ formatTime(call.timestamp) }}</span>
                  </div>
                  <div class="tool-call-body">
                    <div class="tool-input" v-if="call.input">
                      <span class="input-label">输入:</span>
                      <pre class="input-content">{{ call.input }}</pre>
                    </div>
                    <div class="tool-output">
                      <span class="output-label" :class="{ error: call.status === 'failed' }">{{ call.status === 'failed' ? '错误信息:' : '输出:' }}</span>
                      <pre class="output-content" :class="{ error: call.status === 'failed' }">{{ call.output }}</pre>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Agent 输出 -->
            <div class="detail-section" v-if="selectedExecution.agent_output">
              <div class="section-title">Agent 输出</div>
              <div class="agent-output-box">
                <pre>{{ selectedExecution.agent_output }}</pre>
              </div>
            </div>

            <!-- 执行日志 -->
            <div class="detail-section" v-if="selectedExecution.execution_log">
              <div class="section-title">执行日志</div>
              <div class="execution-log-box">
                <pre>{{ selectedExecution.execution_log }}</pre>
              </div>
            </div>

            <!-- 错误详情 -->
            <div class="detail-section error-section" v-if="selectedExecution.error_detail">
              <div class="section-title error-title">错误详情</div>
              <div class="error-box">
                <div class="error-message">
                  <strong>错误信息:</strong> {{ selectedExecution.error_message }}
                </div>
                <pre class="error-traceback">{{ selectedExecution.error_detail }}</pre>
              </div>
            </div>

            <!-- 步骤记录 -->
            <div class="detail-section" v-if="selectedExecution.steps?.length">
              <div class="section-title">执行步骤</div>
              <div class="steps-list-detail">
                <div class="step-item-detail" v-for="(step, idx) in selectedExecution.steps" :key="idx" :class="step.status">
                  <span class="step-icon">{{ getStepIcon(step.status) }}</span>
                  <span class="step-name">{{ step.name || step.tool }}</span>
                  <span class="step-message">{{ step.message }}</span>
                  <span class="step-time">{{ formatTime(step.timestamp) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- SSE 实时进度 -->
      <div class="progress-panel" v-if="progressData">
        <div class="progress-header">
          <span class="run-id">{{ progressData.run_id }}</span>
          <span class="progress-status" :class="progressData.status">{{ progressData.status }}</span>
        </div>

        <!-- 步骤列表 -->
        <div class="steps-list">
          <div class="step" v-for="(step, idx) in progressSteps" :key="idx" :class="step.status">
            <span class="step-icon">{{ getStepIcon(step.status) }}</span>
            <span class="step-tool">{{ step.tool || step.name }}</span>
            <span class="step-message">{{ step.message }}</span>
            <span class="step-time" v-if="step.end_time">{{ step.end_time }}</span>
          </div>
        </div>

        <!-- 当前仓库进度 -->
        <div class="repo-progress" v-if="currentRepo">
          <div class="repo-status">
            <span class="pulse-icon">●</span>
            <span>正在扫描: {{ currentRepo }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import {
  getScheduledTasks,
  getScheduledTask,
  getTaskExecutions,
  getExecutionDetail,
  pauseScheduledTask,
  resumeScheduledTask,
  deleteScheduledTask,
  triggerScheduledTask,
  connectScheduledTaskProgress,
  updateAlertChannels,
  getEnabledChannels,
  bindChannelsToTask
} from '../api/dashboard.js'

// 状态
const tasks = ref([])
const selectedTask = ref(null)
const executions = ref([])
const selectedExecution = ref(null)
const loading = ref(false)
const running = ref(false)
const runningTaskId = ref(null)
const progressData = ref(null)
const progressSteps = ref([])
const currentRepo = ref('')
const showFullPrompt = ref(false)
const showChannelsEdit = ref(false)
const availableChannels = ref([])
const selectedChannelIds = ref([])
const savingChannels = ref(false)
const editChannels = ref({
  dingtalk: { webhook: '', secret: '' },
  feishu: { webhook: '' }
})
let closeSSE = null
let closeExecutionSSE = null  // 执行详情 SSE 连接

// 加载任务列表
async function loadTasks() {
  loading.value = true
  try {
    const data = await getScheduledTasks()
    tasks.value = data.tasks || []
  } catch (e) {
    console.error('加载任务失败:', e)
  } finally {
    loading.value = false
  }
}

// 选择任务 - 加载完整详情
async function selectTask(task) {
  try {
    // 调用详情 API 获取完整信息
    const detail = await getScheduledTask(task.id)
    selectedTask.value = detail

    // 初始化编辑渠道数据
    const channels = detail.alert_channels || {}
    editChannels.value = {
      dingtalk: {
        webhook: channels.dingtalk?.webhook || '',
        secret: channels.dingtalk?.secret || ''
      },
      feishu: {
        webhook: channels.feishu?.webhook || ''
      }
    }

    // 初始化绑定的渠道 ID
    selectedChannelIds.value = detail.alert_channel_ids || []

    // 加载可用渠道列表
    await loadAvailableChannels()

    // 加载执行历史
    const execData = await getTaskExecutions(task.id)
    executions.value = execData.executions || []
  } catch (e) {
    console.error('加载任务详情失败:', e)
    // 失败时使用列表数据
    selectedTask.value = task
  }
}

// 加载可用渠道列表
async function loadAvailableChannels() {
  try {
    const data = await getEnabledChannels()
    availableChannels.value = data.channels || []
  } catch (e) {
    console.error('加载可用渠道失败:', e)
    availableChannels.value = []
  }
}

// 切换渠道选择
function toggleChannelSelection(channelId) {
  const idx = selectedChannelIds.value.indexOf(channelId)
  if (idx >= 0) {
    selectedChannelIds.value.splice(idx, 1)
  } else {
    selectedChannelIds.value.push(channelId)
  }
}

// 关闭渠道编辑弹窗
function closeChannelsEdit() {
  showChannelsEdit.value = false
}

// 打开渠道编辑弹窗
function openChannelsEdit() {
  // 重新加载可用渠道
  loadAvailableChannels()
  showChannelsEdit.value = true
}

// 获取渠道信息
function getChannelInfo(channelId) {
  return availableChannels.value.find(c => c.id === channelId)
}

// 获取渠道名称
function getChannelName(channelId) {
  const channel = getChannelInfo(channelId)
  return channel ? channel.name : `渠道 #${channelId}`
}

// 获取渠道类型
function getChannelType(channelId) {
  const channel = getChannelInfo(channelId)
  return channel ? channel.channel_type : 'unknown'
}

// 获取渠道类型图标
function getChannelTypeIcon(channelId) {
  const icons = { dingtalk: '🔵', feishu: '🟣', webhook: '🟢', unknown: '⚪' }
  return icons[getChannelType(channelId)] || '⚪'
}

// 获取渠道类型标签
function getChannelTypeLabel(channelId) {
  const labels = { dingtalk: '钉钉', feishu: '飞书', webhook: 'Webhook', unknown: '未知' }
  return labels[getChannelType(channelId)] || '未知'
}

// 获取类型图标（通用）
function getTypeIcon(type) {
  const icons = { dingtalk: '🔵', feishu: '🟣', webhook: '🟢' }
  return icons[type] || '⚪'
}

// 获取类型标签（通用）
function getTypeLabel(type) {
  const labels = { dingtalk: '钉钉', feishu: '飞书', webhook: 'Webhook' }
  return labels[type] || type
}

// 保存渠道配置
async function saveChannels() {
  if (!selectedTask.value) return

  savingChannels.value = true
  try {
    // 如果选择了渠道 ID，使用新的绑定方式
    if (selectedChannelIds.value.length > 0) {
      await bindChannelsToTask(selectedTask.value.id, selectedChannelIds.value)
      selectedTask.value.alert_channel_ids = [...selectedChannelIds.value]
      selectedTask.value.alert_channels = null // 清除旧配置
    } else {
      // 使用旧的 webhook 配置方式
      const channels = {}
      if (editChannels.value.dingtalk.webhook) {
        channels.dingtalk = {
          webhook: editChannels.value.dingtalk.webhook,
          secret: editChannels.value.dingtalk.secret || undefined
        }
      }
      if (editChannels.value.feishu.webhook) {
        channels.feishu = {
          webhook: editChannels.value.feishu.webhook
        }
      }

      await updateAlertChannels(selectedTask.value.id, channels)
      selectedTask.value.alert_channels = channels
      selectedTask.value.alert_channel_ids = null // 清除新的绑定
    }

    closeChannelsEdit()
    // 刷新可用渠道列表（以便显示正确的渠道名称）
    await loadAvailableChannels()
    alert('渠道配置已保存，下次执行时生效')
  } catch (e) {
    console.error('保存渠道配置失败:', e)
    alert('保存失败: ' + e.message)
  }
  savingChannels.value = false
}

// 手动执行
async function handleRun(taskId) {
  running.value = true
  runningTaskId.value = taskId

  try {
    const result = await triggerScheduledTask(taskId)
    console.log('任务已触发:', result)

    // 连接 SSE
    connectSSE(taskId)

    // 刷新任务列表
    await loadTasks()
  } catch (e) {
    console.error('触发任务失败:', e)
    alert('触发失败: ' + e.message)
    running.value = false
    runningTaskId.value = null
  }
}

// 连接 SSE 进度推送
function connectSSE(taskId) {
  // 清理之前的连接
  if (closeSSE) {
    closeSSE()
  }

  progressSteps.value = []
  currentRepo.value = ''
  progressData.value = { run_id: 'connecting...', status: 'connecting' }

  closeSSE = connectScheduledTaskProgress(taskId, {
    onInit: (data) => {
      progressData.value = { ...data, status: 'running' }
    },
    onStart: (data) => {
      progressData.value = data
      progressSteps.value.push({ name: 'init', status: 'done', message: '任务开始执行', time: data.timestamp })
    },
    onToolStart: (data) => {
      progressSteps.value.push({ tool: data.tool, status: 'running', message: data.message, time: data.timestamp })
    },
    onToolEnd: (data) => {
      // 更新步骤状态
      const step = progressSteps.value.find(s => s.tool === data.tool && s.status === 'running')
      if (step) {
        step.status = 'done'
        step.end_time = data.timestamp
        step.result = data.result
      }
    },
    onRepoStart: (data) => {
      currentRepo.value = data.repo
    },
    onRepoDone: (data) => {
      if (currentRepo.value === data.repo) {
        currentRepo.value = ''
      }
    },
    onDone: (data) => {
      progressData.value = data
      running.value = false
      runningTaskId.value = null
      progressSteps.value.push({ name: 'done', status: 'done', message: '任务执行完成', time: data.timestamp })
      // 刷新执行历史
      if (selectedTask.value) {
        getTaskExecutions(selectedTask.value.id).then(res => executions.value = res.executions || [])
      }
    },
    onError: (error) => {
      progressData.value = { status: 'failed', error }
      running.value = false
      runningTaskId.value = null
      progressSteps.value.push({ name: 'error', status: 'failed', message: error, time: new Date().toISOString() })
    },
    onHeartbeat: (timestamp) => {
      console.log('[SSE] Heartbeat:', timestamp)
    }
  })
}

// 暂停
async function handlePause(taskId) {
  try {
    await pauseScheduledTask(taskId)
    await loadTasks()
    if (selectedTask.value?.id === taskId) {
      selectedTask.value = tasks.value.find(t => t.id === taskId)
    }
  } catch (e) {
    alert('暂停失败: ' + e.message)
  }
}

// 恢复
async function handleResume(taskId) {
  try {
    await resumeScheduledTask(taskId)
    await loadTasks()
    if (selectedTask.value?.id === taskId) {
      selectedTask.value = tasks.value.find(t => t.id === taskId)
    }
  } catch (e) {
    alert('恢复失败: ' + e.message)
  }
}

// 删除
async function handleDelete(taskId) {
  if (!confirm('确定删除此任务？')) return

  try {
    await deleteScheduledTask(taskId)
    tasks.value = tasks.value.filter(t => t.id !== taskId)
    if (selectedTask.value?.id === taskId) {
      selectedTask.value = null
    }
  } catch (e) {
    alert('删除失败: ' + e.message)
  }
}

// 格式化时间
function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// 格式化完整时间
function formatFullTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// 显示执行详情
// 显示执行详情（调用 API 获取完整数据，如正在执行则建立 SSE 实时更新）
async function showExecutionDetail(execution) {
  try {
    // 从 API 获取完整详情（包含 tool_calls、agent_output、execution_log）
    const detail = await getExecutionDetail(execution.run_id)
    selectedExecution.value = detail

    // 如果执行状态是 running，建立 SSE 实时更新
    if (detail.status === 'running') {
      connectExecutionSSE(detail.scheduled_task_id, execution.run_id)
    }
  } catch (e) {
    console.error('获取执行详情失败:', e)
    // 失败时使用列表数据（可能缺少完整详情）
    selectedExecution.value = execution

    // 如果列表数据显示正在执行，也尝试建立 SSE
    if (execution.status === 'running' && execution.scheduled_task_id) {
      connectExecutionSSE(execution.scheduled_task_id, execution.run_id)
    }
  }
}

// 连接执行详情 SSE（实时更新）
function connectExecutionSSE(taskId, runId) {
  // 清理之前的连接
  if (closeExecutionSSE) {
    closeExecutionSSE()
    closeExecutionSSE = null
  }

  console.log('[ExecutionSSE] Connecting for task:', taskId, 'run:', runId)

  closeExecutionSSE = connectScheduledTaskProgress(taskId, {
    onInit: (data) => {
      if (selectedExecution.value?.run_id === runId) {
        selectedExecution.value.status = 'running'
      }
    },
    onStart: (data) => {
      if (selectedExecution.value?.run_id === runId) {
        selectedExecution.value.status = 'running'
        // 初始化步骤列表
        if (!selectedExecution.value.steps) {
          selectedExecution.value.steps = []
        }
        selectedExecution.value.steps.push({
          name: 'init',
          status: 'done',
          message: '任务开始执行',
          timestamp: data.timestamp
        })
      }
    },
    onToolStart: (data) => {
      if (selectedExecution.value?.run_id === runId) {
        if (!selectedExecution.value.steps) {
          selectedExecution.value.steps = []
        }
        selectedExecution.value.steps.push({
          tool: data.tool,
          status: 'running',
          message: data.message,
          timestamp: data.timestamp
        })
        // 初始化 tool_calls
        if (!selectedExecution.value.tool_calls) {
          selectedExecution.value.tool_calls = []
        }
        selectedExecution.value.tool_calls.push({
          tool: data.tool,
          status: 'running',
          timestamp: data.timestamp
        })
      }
    },
    onToolEnd: (data) => {
      if (selectedExecution.value?.run_id === runId) {
        // 更新步骤状态
        if (selectedExecution.value.steps) {
          const step = selectedExecution.value.steps.find(
            s => s.tool === data.tool && s.status === 'running'
          )
          if (step) {
            step.status = 'done'
            step.end_time = data.timestamp
            step.result = data.result
          }
        }
        // 更新 tool_calls
        if (selectedExecution.value.tool_calls) {
          const call = selectedExecution.value.tool_calls.find(
            c => c.tool === data.tool && c.status === 'running'
          )
          if (call) {
            call.status = 'done'
            call.output = data.result
            call.end_time = data.timestamp
          }
        }
      }
    },
    onRepoStart: (data) => {
      // 仓库开始扫描（可选更新）
    },
    onRepoDone: (data) => {
      // 仓库扫描完成（可选更新）
    },
    onDone: (data) => {
      if (selectedExecution.value?.run_id === runId) {
        // 更新状态
        selectedExecution.value.status = 'completed'
        selectedExecution.value.completed_at = data.timestamp

        // 更新结果数据
        if (data.result) {
          selectedExecution.value.total_findings = data.result.total_findings || 0
          selectedExecution.value.high_severity_count = data.result.high_severity_count || 0
          selectedExecution.value.agent_output = data.result.agent_output || ''
        }

        // 添加完成步骤
        if (selectedExecution.value.steps) {
          selectedExecution.value.steps.push({
            name: 'done',
            status: 'done',
            message: '任务执行完成',
            timestamp: data.timestamp
          })
        }
      }
      // 关闭 SSE
      if (closeExecutionSSE) {
        closeExecutionSSE()
        closeExecutionSSE = null
      }
      // 刷新执行历史列表
      if (selectedTask.value) {
        getTaskExecutions(selectedTask.value.id).then(res => executions.value = res.executions || [])
      }
    },
    onError: (error) => {
      if (selectedExecution.value?.run_id === runId) {
        selectedExecution.value.status = 'failed'
        selectedExecution.value.error_message = error
        if (!selectedExecution.value.steps) {
          selectedExecution.value.steps = []
        }
        selectedExecution.value.steps.push({
          name: 'error',
          status: 'failed',
          message: error,
          timestamp: new Date().toISOString()
        })
      }
      // 关闭 SSE
      if (closeExecutionSSE) {
        closeExecutionSSE()
        closeExecutionSSE = null
      }
    },
    onHeartbeat: (timestamp) => {
      console.log('[ExecutionSSE] Heartbeat:', timestamp)
    }
  })
}

// 关闭执行详情弹窗时清理 SSE
function closeExecutionDetail() {
  if (closeExecutionSSE) {
    closeExecutionSSE()
    closeExecutionSSE = null
  }
  selectedExecution.value = null
}

// 状态标签
function getStatusLabel(status) {
  const labels = { active: '运行中', paused: '已暂停', disabled: '已禁用' }
  return labels[status] || status
}

function getExecStatusLabel(status) {
  const labels = { running: '执行中', completed: '已完成', failed: '失败' }
  return labels[status] || status
}

function getStepIcon(status) {
  const icons = { running: '●', done: '✓', failed: '✗' }
  return icons[status] || '○'
}

// 清理
onUnmounted(() => {
  if (closeSSE) {
    closeSSE()
  }
  if (closeExecutionSSE) {
    closeExecutionSSE()
  }
})

// 初始化
onMounted(() => {
  loadTasks()
})
</script>

<style scoped>
.scheduled-task {
  padding: 24px;
  height: 100%;
  overflow-y: auto;
  background: #f8fafc;
}

.task-header {
  display: flex;
  align-items: baseline;
  gap: 16px;
  margin-bottom: 24px;
}

.task-header h1 {
  font-size: 24px;
  font-weight: 600;
  color: #1e293b;
}

.hint {
  font-size: 14px;
  color: #94a3b8;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.task-item:hover {
  border-color: #7dd3fc;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.task-main {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.task-name {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}

.task-target {
  font-size: 14px;
  color: #0ea5e9;
  background: #e0f2fe;
  padding: 2px 8px;
  border-radius: 4px;
}

.task-cron {
  font-size: 12px;
  color: #64748b;
}

.status-badge {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  font-weight: 500;
}

.status-badge.active {
  background: #dcfce7;
  color: #16a34a;
}

.status-badge.paused {
  background: #fef3c7;
  color: #d97706;
}

.status-badge.disabled {
  background: #f1f5f9;
  color: #94a3b8;
}

.task-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #64748b;
}

.task-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn.run {
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  color: white;
  border: none;
}

.action-btn.run:hover:not(:disabled) {
  transform: translateY(-1px);
}

.action-btn.run:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-btn.pause, .action-btn.resume {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.action-btn.delete {
  background: transparent;
  color: #dc2626;
  border: 1px solid #fecaca;
}

.empty-state, .loading-state {
  padding: 40px;
  text-align: center;
  color: #94a3b8;
}

/* 详情面板 */
.task-detail-panel {
  position: fixed;
  right: 0;
  top: 0;
  width: 400px;
  height: 100vh;
  background: #ffffff;
  border-left: 1px solid #e2e8f0;
  padding: 24px;
  overflow-y: auto;
  box-shadow: -4px 0 12px rgba(0, 0, 0, 0.05);
  z-index: 100;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.panel-header h2 {
  font-size: 18px;
  font-weight: 600;
}

.close-btn {
  background: transparent;
  border: none;
  font-size: 20px;
  color: #94a3b8;
  cursor: pointer;
}

.task-info-section {
  margin-bottom: 24px;
}

.info-row {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #f1f5f9;
}

.info-row .label {
  font-size: 13px;
  color: #94a3b8;
  width: 100px;
}

.info-row .value {
  font-size: 14px;
  color: #1e293b;
}

.prompt-preview {
  color: #64748b;
  font-size: 12px;
}

/* Prompt 展开/收起 */
.prompt-section {
  margin-bottom: 24px;
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
}

.prompt-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
}

.prompt-header .label {
  font-size: 13px;
  color: #94a3b8;
}

.toggle-btn {
  font-size: 12px;
  color: #0ea5e9;
  padding: 2px 8px;
  background: #e0f2fe;
  border-radius: 4px;
}

.prompt-content pre {
  margin-top: 12px;
  padding: 12px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 12px;
  color: #1e293b;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

.prompt-preview {
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
}

.last-status {
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
  margin-left: 4px;
}

.last-status.completed {
  background: #dcfce7;
  color: #16a34a;
}

.last-status.failed {
  background: #fef2f2;
  color: #dc2626;
}

.executions-section h3 {
  font-size: 14px;
  color: #64748b;
  margin-bottom: 12px;
}

.executions-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.execution-item {
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
}

.exec-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.run-id {
  font-size: 12px;
  color: #64748b;
}

.exec-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}

.exec-status.completed {
  background: #dcfce7;
  color: #16a34a;
}

.exec-status.running {
  background: #dbeafe;
  color: #2563eb;
}

.exec-status.failed {
  background: #fef2f2;
  color: #dc2626;
}

.exec-time {
  font-size: 12px;
  color: #94a3b8;
}

.exec-stats {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #64748b;
}

.exec-steps {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.step-item {
  font-size: 11px;
  color: #94a3b8;
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
}

/* SSE 进度面板 */
.progress-panel {
  margin-top: 20px;
  padding: 16px;
  background: #f0fdf4;
  border: 1px solid #86efac;
  border-radius: 12px;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.progress-status.running {
  color: #2563eb;
}

.progress-status.completed {
  color: #16a34a;
}

.progress-status.failed {
  color: #dc2626;
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.step.running {
  color: #2563eb;
}

.step.done {
  color: #16a34a;
}

.step.failed {
  color: #dc2626;
}

.step-icon {
  width: 16px;
}

.repo-progress {
  margin-top: 12px;
  padding: 12px;
  background: #ffffff;
  border-radius: 8px;
}

.repo-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pulse-icon {
  color: #f97316;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 告警渠道配置 */
.channels-section {
  margin-bottom: 24px;
  padding: 16px 20px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 12px;
}

.channels-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.channels-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-icon {
  font-size: 18px;
}

.edit-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #0ea5e9;
  padding: 6px 14px;
  background: #e0f2fe;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.edit-btn:hover {
  background: #bae6fd;
}

.btn-icon {
  font-size: 14px;
}

.channels-content {
  margin-top: 8px;
}

/* 绑定的渠道列表 */
.bound-channels-list {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.bound-channel-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 10px;
  border: 2px solid;
}

.bound-channel-card.dingtalk {
  border-color: rgba(37, 99, 235, 0.3);
}

.bound-channel-card.feishu {
  border-color: rgba(124, 58, 237, 0.3);
}

.bound-channel-card.webhook {
  border-color: rgba(22, 163, 74, 0.3);
}

.bound-channel-card.legacy {
  border-color: rgba(251, 146, 60, 0.4);
  background: #fffbeb;
}

.channel-type-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
}

.channel-type-tag.dingtalk {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
}

.channel-type-tag.feishu {
  background: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%);
}

.channel-type-tag.webhook {
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
}

.channel-type-tag.unknown {
  background: #f1f5f9;
}

.type-icon {
  font-size: 14px;
}

.type-name {
  font-size: 12px;
  font-weight: 600;
}

.channel-type-tag.dingtalk .type-name { color: #2563eb; }
.channel-type-tag.feishu .type-name { color: #7c3aed; }
.channel-type-tag.webhook .type-name { color: #16a34a; }
.channel-type-tag.unknown .type-name { color: #64748b; }

.channel-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.channel-info .channel-name {
  font-size: 14px;
  font-weight: 500;
  color: #1e293b;
}

.bind-status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #dcfce7;
  color: #16a34a;
  font-weight: 500;
}

.bind-status.legacy {
  background: #fef3c7;
  color: #d97706;
}

/* 未配置状态 */
.no-channel-config {
  text-align: center;
  padding: 24px;
}

.no-channel-icon {
  font-size: 40px;
  margin-bottom: 8px;
}

.no-channel-text {
  font-size: 14px;
  color: #64748b;
  margin-bottom: 4px;
}

.no-channel-hint {
  font-size: 12px;
  color: #94a3b8;
}

/* 旧格式渠道 */
.legacy-channels {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

/* 渠道编辑弹窗 */
.channels-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 200;
}

.channels-modal {
  background: #fff;
  border-radius: 16px;
  width: 560px;
  max-width: 90vw;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
}

.modal-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #f1f5f9;
}

.modal-title {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-icon {
  font-size: 22px;
}

.live-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #2563eb;
  background: #dbeafe;
  padding: 4px 12px;
  border-radius: 20px;
  margin-left: 12px;
  animation: pulse-live 1.5s infinite;
}

@keyframes pulse-live {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.modal-close-btn {
  background: none;
  border: none;
  font-size: 28px;
  color: #94a3b8;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.modal-close-btn:hover {
  color: #64748b;
}

.modal-body-content {
  padding: 24px;
}

.select-section {
  margin-bottom: 20px;
}

.select-hint {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 16px;
}

/* 渠道选择网格 */
.channel-select-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.channel-select-card {
  padding: 14px 16px;
  background: #f8fafc;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.channel-select-card:hover {
  border-color: #cbd5e1;
}

.channel-select-card.selected {
  background: #fff;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.channel-select-card.selected.dingtalk {
  border-color: #2563eb;
  background: linear-gradient(135deg, #eff6ff 0%, #fff 100%);
}

.channel-select-card.selected.feishu {
  border-color: #7c3aed;
  background: linear-gradient(135deg, #f5f3ff 0%, #fff 100%);
}

.channel-select-card.selected.webhook {
  border-color: #16a34a;
  background: linear-gradient(135deg, #f0fdf4 0%, #fff 100%);
}

.select-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.select-checkbox {
  font-size: 18px;
}

.channel-type-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
}

.channel-type-badge.dingtalk {
  background: #eff6ff;
}

.channel-type-badge.feishu {
  background: #f5f3ff;
}

.channel-type-badge.webhook {
  background: #f0fdf4;
}

.badge-icon {
  font-size: 12px;
}

.badge-text {
  font-size: 11px;
  font-weight: 600;
}

.channel-type-badge.dingtalk .badge-text { color: #2563eb; }
.channel-type-badge.feishu .badge-text { color: #7c3aed; }
.channel-type-badge.webhook .badge-text { color: #16a34a; }

.select-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.select-name {
  font-size: 14px;
  font-weight: 500;
  color: #1e293b;
}

.select-desc {
  font-size: 12px;
  color: #94a3b8;
}

/* 无渠道提示 */
.no-channels-hint {
  text-align: center;
  padding: 32px;
}

.no-channels-hint .empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.no-channels-hint p {
  font-size: 14px;
  color: #64748b;
  margin-bottom: 16px;
}

.goto-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.goto-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
}

.goto-btn .btn-icon {
  font-size: 16px;
}

/* 兼容旧格式区域 */
.legacy-config-section {
  margin-top: 20px;
}

.section-divider {
  text-align: center;
  margin-bottom: 16px;
}

.divider-text {
  font-size: 12px;
  color: #94a3b8;
  background: #f1f5f9;
  padding: 6px 16px;
  border-radius: 20px;
}

.legacy-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 13px;
  color: #64748b;
}

.form-input-legacy {
  padding: 12px 14px;
  border: 2px solid #e2e8f0;
  border-radius: 10px;
  font-size: 14px;
  color: #1e293b;
  transition: all 0.2s;
}

.form-input-legacy:focus {
  border-color: #0ea5e9;
  outline: none;
}

/* 弹窗底部 */
.modal-footer-bar {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 24px;
  border-top: 1px solid #f1f5f9;
}

.footer-btn {
  padding: 12px 24px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.footer-btn.cancel {
  background: #f1f5f9;
  color: #64748b;
  border: none;
}

.footer-btn.cancel:hover {
  background: #e2e8f0;
}

.footer-btn.save {
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  color: white;
  border: none;
}

.footer-btn.save:hover {
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
}

.footer-btn.save:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 执行详情弹窗 */
.execution-detail-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(15, 23, 42, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 300;
}

.execution-detail-modal {
  background: #fff;
  border-radius: 16px;
  width: 700px;
  max-width: 90vw;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
}

.modal-body-content {
  padding: 24px;
}

.detail-section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid #e2e8f0;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 12px;
  color: #94a3b8;
}

.detail-value {
  font-size: 14px;
  color: #1e293b;
}

/* 工具调用记录 */
.tool-calls-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tool-call-item {
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.tool-call-item.failed {
  background: #fef2f2;
  border-color: #fecaca;
}

.tool-call-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.tool-name {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.tool-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}

.tool-status.completed {
  background: #dcfce7;
  color: #16a34a;
}

.tool-status.failed {
  background: #fee2e2;
  color: #b91c1c;
  font-weight: 500;
}

.tool-status.failed {
  background: #fef2f2;
  color: #dc2626;
}

.tool-duration {
  font-size: 12px;
  color: #64748b;
}

.tool-time {
  font-size: 11px;
  color: #94a3b8;
}

.tool-call-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-input, .tool-output {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.input-label, .output-label {
  font-size: 12px;
  color: #64748b;
}

.output-label.error {
  color: #dc2626;
  font-weight: 500;
}

.input-content, .output-content {
  padding: 8px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 12px;
  color: #1e293b;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 100px;
  overflow-y: auto;
}

.output-content.error {
  background: #fef2f2;
  border-color: #fecaca;
  color: #b91c1c;
}

/* Agent 输出 */
.agent-output-box {
  padding: 16px;
  background: #f0fdf4;
  border: 1px solid #86efac;
  border-radius: 8px;
}

.agent-output-box pre {
  font-size: 13px;
  color: #1e293b;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 执行日志 */
.execution-log-box {
  padding: 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.execution-log-box pre {
  font-size: 12px;
  color: #475569;
  white-space: pre-wrap;
  line-height: 1.6;
}

/* 错误详情 */
.error-section .section-title {
  color: #dc2626;
  border-bottom-color: #fecaca;
}

.error-box {
  padding: 16px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
}

.error-message {
  font-size: 14px;
  color: #dc2626;
  margin-bottom: 12px;
}

.error-traceback {
  font-size: 12px;
  color: #7f1d1d;
  white-space: pre-wrap;
  background: #fff;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}

/* 步骤列表详情 */
.steps-list-detail {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.step-item-detail {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: #f8fafc;
  border-radius: 6px;
}

.step-item-detail.running {
  background: #eff6ff;
}

.step-item-detail.done {
  background: #f0fdf4;
}

.step-item-detail.failed {
  background: #fef2f2;
}

.step-item-detail .step-icon {
  font-size: 14px;
}

.step-item-detail .step-name {
  font-size: 13px;
  font-weight: 500;
  color: #1e293b;
}

.step-item-detail .step-message {
  font-size: 12px;
  color: #64748b;
}

.step-item-detail .step-time {
  font-size: 11px;
  color: #94a3b8;
  margin-left: auto;
}

/* 执行历史列表增强 */
.execution-item {
  cursor: pointer;
  transition: all 0.2s;
}

.execution-item:hover {
  background: #e0f2fe;
  border-radius: 8px;
}

.exec-error-preview {
  margin-top: 8px;
  font-size: 12px;
}

.error-label {
  color: #dc2626;
  font-weight: 500;
}

.error-text {
  color: #7f1d1d;
}
</style>