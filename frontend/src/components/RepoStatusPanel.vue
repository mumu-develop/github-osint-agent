<template>
  <div class="repo-status-panel" v-if="shouldShow">
    <!-- 标题栏 -->
    <div class="panel-header">
      <span class="panel-icon">{{ getIcon(statusData.subagent) }}</span>
      <span class="panel-title">{{ getTitle(statusData.subagent, statusData.phase) }}</span>
    </div>

    <!-- 仓库列表 -->
    <div class="repo-list">
      <div
        v-for="repo in statusData.repos"
        :key="repo.name"
        class="repo-item"
        :class="repo.status"
      >
        <span class="repo-status-icon">{{ getStatusIcon(repo.status) }}</span>
        <span class="repo-name">{{ repo.name.split('/').pop() }}</span>
        <span class="repo-status-text">{{ getStatusText(repo) }}</span>
      </div>
    </div>

    <!-- 统计栏 -->
    <div class="stats-bar">
      <span class="stat-item done">
        <span class="stat-icon">✅</span>
        <span class="stat-count">{{ statusData.stats.done }}</span>
        <span class="stat-label">完成</span>
      </span>
      <span class="stat-item running">
        <span class="stat-icon">⏳</span>
        <span class="stat-count">{{ statusData.stats.running }}</span>
        <span class="stat-label">执行</span>
      </span>
      <span class="stat-item waiting">
        <span class="stat-icon">⏸️</span>
        <span class="stat-count">{{ statusData.stats.waiting }}</span>
        <span class="stat-label">等待</span>
      </span>
      <span class="stat-item error">
        <span class="stat-icon">❌</span>
        <span class="stat-count">{{ statusData.stats.error }}</span>
        <span class="stat-label">失败</span>
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'

const props = defineProps({
  statusData: {
    type: Object,
    default: null
  }
})

// 计算属性 - 判断是否显示
const shouldShow = computed(() => {
  const hasData = props.statusData !== null && props.statusData !== undefined
  const hasRepos = hasData && props.statusData.repos && props.statusData.repos.length > 0
  return hasRepos
})

function getIcon(subagent) {
  const icons = {
    'security-analyzer': '🛡️',
    'compliance-analyzer': '⚖️',
    'community-analyzer': '👥',
    'trend-analyzer': '📊'
  }
  return icons[subagent] || '🔧'
}

function getTitle(subagent, phase) {
  const phaseNames = {
    'cve_scan': 'CVE漏洞检查',
    'secret_scan': '敏感信息扫描',
    'license_check': '许可证检查',
    'community_check': '社区健康检查'
  }
  const phaseText = phaseNames[phase] || phase || '扫描'
  return `${getIcon(subagent)} ${phaseText}`
}

function getStatusIcon(status) {
  const icons = {
    'waiting': '⏸️',
    'running': '⏳',
    'done': '✅',
    'error': '❌'
  }
  return icons[status] || '⏸️'
}

function getStatusText(repo) {
  if (repo.status === 'done') {
    if (repo.findings > 0) {
      return `完成 (发现${repo.findings}个)`
    }
    return '完成'
  }
  if (repo.status === 'error') {
    return repo.error || '失败'
  }
  if (repo.status === 'running') {
    return '执行中...'
  }
  return '等待'
}
</script>

<style scoped>
.repo-status-panel {
  margin: 12px 0;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e2e8f0;
}

.panel-icon {
  font-size: 18px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.repo-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 12px 0;
  max-height: 200px;
  overflow-y: auto;
}

.repo-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.repo-item.running {
  background: #fef3c7;
  border-color: #fde68a;
  animation: pulse 1.5s infinite;
}

.repo-item.done {
  background: #d1fae5;
  border-color: #a7f3d0;
}

.repo-item.error {
  background: #fee2e2;
  border-color: #fecaca;
}

.repo-item.waiting {
  background: #f1f5f9;
  border-color: #e2e8f0;
}

.repo-status-icon {
  font-size: 11px;
}

.repo-name {
  font-weight: 500;
  color: #1e293b;
}

.repo-status-text {
  color: #64748b;
  font-size: 11px;
}

.repo-item.done .repo-status-text {
  color: #065f46;
}

.repo-item.error .repo-status-text {
  color: #991b1b;
}

.repo-item.running .repo-status-text {
  color: #b45309;
}

.stats-bar {
  display: flex;
  gap: 16px;
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.stat-icon {
  font-size: 14px;
}

.stat-count {
  font-weight: 600;
  font-size: 14px;
}

.stat-label {
  font-size: 12px;
  color: #64748b;
}

.stat-item.done .stat-count {
  color: #065f46;
}

.stat-item.running .stat-count {
  color: #b45309;
}

.stat-item.error .stat-count {
  color: #991b1b;
}

.stat-item.waiting .stat-count {
  color: #64748b;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
</style>