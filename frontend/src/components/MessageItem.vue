<template>
  <!-- 用户消息 -->
  <div v-if="message.role === 'user'" class="message-item message-user">
    <div class="message-content-wrapper">
      <div class="message-content">
        <div class="content-text">{{ message.content }}</div>
      </div>
    </div>
    <div class="message-avatar">
      <div class="avatar user-avatar">👤</div>
    </div>
  </div>

  <!-- AI 助手消息 -->
  <div v-else-if="message.role === 'assistant'" class="message-item message-assistant" :class="{ streaming: isStreaming }">
    <div class="message-avatar">
      <div class="avatar assistant-avatar">🤖</div>
    </div>
    <div class="message-content-wrapper">
      <div class="msg-label-bar">
        <span class="msg-role-badge">{{ getRoleLabel(message.source) }}</span>
        <span v-if="message.source && message.source !== 'main'" class="msg-source-badge">
          {{ getSourceName(message.source) }}
        </span>
      </div>
      <div class="message-content">
        <!-- 有内容时显示 Markdown -->
        <MarkdownRenderer
          v-if="message.content"
          :content="message.content"
          :show-copy-button="!isStreaming && message.content.length > 50"
        />
        <!-- 无内容且正在流式输出时，显示思考状态 -->
        <div v-else-if="isStreaming" class="thinking-state">
          <span class="thinking-dot"></span>
          <span class="thinking-dot"></span>
          <span class="thinking-dot"></span>
          <span class="thinking-text">思考中...</span>
        </div>
        <!-- 无内容且已结束 -->
        <span v-else class="empty-response">（等待工具执行完成）</span>
        <span v-if="isStreaming && message.content" class="typing-cursor">▋</span>
      </div>
    </div>
  </div>

  <!-- 工具调用消息 -->
  <div v-else-if="message.role === 'tool'" class="message-item message-tool">
    <div class="message-avatar">
      <div class="avatar tool-avatar">{{ getToolIcon(message.tool_name) }}</div>
    </div>
    <div class="message-content-wrapper">
      <div class="msg-label-bar tool-label-bar">
        <span class="msg-role-badge tool-role-badge">工具</span>
        <span class="msg-tool-name-badge">{{ formatToolName(message.tool_name) }}</span>
        <span v-if="message.tool_status === 'calling'" class="tool-status-badge calling">执行中</span>
        <span v-else-if="message.tool_status === 'stopped'" class="tool-status-badge stopped">已停止</span>
        <span v-else-if="message.tool_status === 'error'" class="tool-status-badge error">失败</span>
        <span v-else class="tool-status-badge done">完成</span>
      </div>

      <!-- 仓库扫描进度面板（在工具执行中显示） -->
      <RepoStatusPanel v-if="showRepoProgress" :status-data="repoStatus" />

      <!-- 报告下载工具：显示下载按钮 -->
      <div v-if="message.tool_name === 'return_report_for_download' && message.tool_status === 'done'" class="download-action">
        <a :href="extractDownloadUrl(message.output)" target="_blank" class="download-btn">
          ⬇️ 点击下载报告
        </a>
        <span class="download-hint">（已自动下载，也可手动点击）</span>
      </div>
      <div v-if="message.input" class="tool-section">
        <div class="tool-section-header" @click="toggleSection('input')">
          <span class="section-arrow">{{ expandedSections.includes('input') ? '▼' : '▶' }}</span>
          <span class="section-label">参数</span>
        </div>
        <pre v-if="expandedSections.includes('input')" class="tool-code">{{ formatArgs(message.input) }}</pre>
      </div>
      <div v-if="message.output" class="tool-section">
        <div class="tool-section-header" @click="toggleSection('output')">
          <span class="section-arrow">{{ expandedSections.includes('output') ? '▼' : '▶' }}</span>
          <span class="section-label">结果</span>
        </div>
        <div v-if="expandedSections.includes('output')" class="tool-result">
          <MarkdownRenderer :content="cleanOutput(message.output)" />
        </div>
      </div>
      <div v-if="message.tool_status === 'calling' && !message.output" class="tool-waiting">
        <span class="waiting-dot"></span>
        <span class="waiting-dot"></span>
        <span class="waiting-dot"></span>
        <span class="waiting-text">执行中...</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import RepoStatusPanel from './RepoStatusPanel.vue'

const props = defineProps({
  message: { type: Object, required: true },
  isStreaming: { type: Boolean, default: false },
  repoStatus: { type: Object, default: null }  // 仓库扫描进度
})

const expandedSections = ref(['output'])

// 允许显示进度面板的扫描工具（排除 task 等非扫描工具）
const SCAN_TOOLS_WITH_PROGRESS = [
  'check_cve_repos', 'scan_secrets', 'check_license', 'check_community',
  'batch_scan_org', 'batch_check_cve', 'batch_scan_secrets',
  'batch_check_license', 'batch_check_community', 'scan_org',
  'get_org_repos', 'get_dependency_files'
]

// 是否显示进度面板（仅扫描工具执行时显示）
const showRepoProgress = computed(() => {
  // 必须是扫描工具
  const isScanTool = SCAN_TOOLS_WITH_PROGRESS.includes(props.message.tool_name)
  return props.message.role === 'tool' &&
         props.message.tool_status === 'calling' &&
         isScanTool &&
         props.repoStatus &&
         props.repoStatus.repos &&
         props.repoStatus.repos.length > 0
})

function toggleSection(name) {
  const idx = expandedSections.value.indexOf(name)
  if (idx === -1) expandedSections.value.push(name)
  else expandedSections.value.splice(idx, 1)
}

function getRoleLabel(source) {
  if (!source || source === 'main') return 'OSINT'
  return getSourceName(source)
}

function getSourceName(source) {
  const map = {
    'main': '主Agent',
    'trend-analyzer': '趋势分析',
    'security-analyzer': '安全分析',
    'community-analyzer': '社区分析',
    'compliance-analyzer': '合规审计'
  }
  return map[source] || source
}

function formatToolName(name) {
  const map = {
    // === 组织级扫描 ===
    'scan_org': '组织扫描',
    'get_org_repos': '获取组织仓库',
    // === 安全工具 ===
    'check_cve_repos': 'CVE漏洞检查',
    'check_package_cve': 'CVE包查询',
    'scan_secrets': '敏感信息扫描',
    'get_dependency_files': '获取依赖文件',
    // === 合规工具 ===
    'check_license': '许可证检查',
    'scan_copyright': '版权扫描',
    // === 社区工具 ===
    'check_community': '社区健康检查',
    'get_issue_metrics': 'Issue统计',
    'get_pr_metrics': 'PR统计',
    'get_contributor_activity': '贡献者活跃度',
    // === 趋势工具 ===
    'get_star_history': 'Star历史',
    'get_repo_stats': '仓库统计',
    'calculate_growth_rate': '计算增长率',
    // === 报告工具 ===
    'get_sandbox_report_path': '获取报告路径',
    'return_report_for_download': '返回报告下载',
    'save_report_to_local': '保存报告',
    'list_local_reports': '报告列表',
    'get_report_content': '获取报告',
    // === 记忆工具 ===
    'save_memory': '保存记忆',
    'get_memory': '获取记忆',
    // === 技能管理工具 ===
    'download_skill': '下载技能',
    'scan_skill': '扫描技能',
    'validate_skill': '验证技能',
    'assign_skill': '分配技能',
    'list_skills': '技能列表',
    'remove_skill': '移除技能',
    // === 任务委派 ===
    'task': '委派子Agent',
    'write_todos': '规划任务',
    // === 已弃用工具（兼容旧版本）===
    'batch_scan_org': '批量扫描组织',
    'batch_check_cve': '批量CVE检查',
    'batch_scan_secrets': '批量敏感信息扫描',
    'batch_check_license': '批量许可证检查',
    'batch_check_community': '批量社区健康检查',
    'batch_get_dependencies': '批量获取依赖文件',
    'scan_repo': '仓库扫描',
    'generate_download_url': '生成下载链接',
  }
  return map[name] || name
}

function getToolIcon(name) {
  if (!name) return '🔧'
  const lower = name.toLowerCase()
  if (lower.includes('trend') || lower.includes('star') || lower.includes('growth')) return '📊'
  if (lower.includes('security') || lower.includes('cve') || lower.includes('secret')) return '🛡️'
  if (lower.includes('community') || lower.includes('issue') || lower.includes('pr') || lower.includes('contributor')) return '👥'
  if (lower.includes('compliance') || lower.includes('license') || lower.includes('copyright')) return '⚖️'
  if (lower.includes('task')) return '🤝'
  if (lower.includes('memory')) return '💾'
  if (lower.includes('report')) return '📄'
  if (lower.includes('download')) return '⬇️'
  return '🔧'
}

function formatArgs(args) {
  if (!args) return ''
  try {
    return JSON.stringify(JSON.parse(args), null, 2)
  } catch {
    return args
  }
}

function cleanOutput(output) {
  if (!output) return ''
  if (typeof output === 'object') {
    return JSON.stringify(output, null, 2)
  }
  return output
}

function extractDownloadUrl(output) {
  if (!output) return ''
  // 尝试解析 JSON/Python dict
  try {
    // 处理 Python dict 格式
    const jsonStr = output
      .replace(/True/g, 'true')
      .replace(/False/g, 'false')
      .replace(/None/g, 'null')
      .replace(/'/g, '"')
    const parsed = JSON.parse(jsonStr)
    // 新格式：return_report_for_download 返回 sandbox_path
    if (parsed.sandbox_path) {
      return `/api/download/sandbox${parsed.sandbox_path}`
    }
    // 旧格式：generate_download_url 返回 download_url
    if (parsed.download_url) return parsed.download_url
  } catch {
    // 尝试从字符串提取 sandbox_path
    const pathMatch = output.match(/sandbox_path[=:]\s*['"]?([^'"}\s]+)['"]?/)
    if (pathMatch) return `/api/download/sandbox${pathMatch[1]}`
    // 尝试从字符串提取 download_url
    const urlMatch = output.match(/download_url[=:]\s*['"]?([^'"}\s]+)['"]?/)
    if (urlMatch) return urlMatch[1]
  }
  return ''
}
</script>

<style scoped>
.message-item {
  display: flex;
  gap: 12px;
  padding: 12px 24px;
  max-width: 100%;
}

.message-item.streaming {
  background: linear-gradient(to right, transparent, rgba(14, 165, 233, 0.03), transparent);
}

.msg-label-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 6px 0;
}

.msg-role-badge {
  padding: 3px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  background: #dbeafe;
  color: #1d4ed8;
}

.msg-source-badge {
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  background: #ddd6fe;
  color: #6d28d9;
}

/* 用户消息 */
.message-user {
  justify-content: flex-end;
}

.message-user .message-content-wrapper {
  max-width: 65%;
}

.message-user .message-content {
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  border-radius: 18px 18px 6px 18px;
  padding: 14px 18px;
  box-shadow: 0 2px 8px rgba(14, 165, 233, 0.2);
}

.message-user .content-text {
  color: #fff;
  font-size: 15px;
  white-space: pre-wrap;
}

.user-avatar {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
}

/* AI 消息 */
.message-assistant {
  justify-content: flex-start;
}

.message-assistant .message-content-wrapper {
  max-width: 80%;
}

.message-assistant .message-content {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px 14px 14px 14px;
  padding: 14px 18px;
}

.assistant-avatar {
  background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
}

/* 工具消息 */
.message-tool {
  justify-content: flex-start;
}

.message-tool .message-content-wrapper {
  max-width: 85%;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 0 14px 14px 14px;
  padding: 14px 18px;
}

.tool-label-bar .tool-role-badge {
  background: #fef3c7;
  color: #b45309;
}

.msg-tool-name-badge {
  padding: 3px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
  color: #92400e;
  background: #fef9c3;
}

.tool-status-badge {
  margin-left: auto;
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 10px;
  font-weight: 600;
}

.tool-status-badge.calling {
  background: #fef3c7;
  color: #b45309;
  animation: pulse 1.5s infinite;
}

.tool-status-badge.done {
  background: #d1fae5;
  color: #065f46;
}

.tool-status-badge.stopped {
  background: #fee2e2;
  color: #991b1b;
}

.tool-status-badge.error {
  background: #fef2f2;
  color: #dc2626;
}

.tool-avatar {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
}

.tool-section {
  margin-top: 8px;
}

.tool-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 6px 0;
  color: #92400e;
  font-size: 13px;
  font-weight: 600;
}

.section-arrow {
  font-size: 10px;
}

.tool-code {
  background: #fffbeb;
  border: 1px solid #fde68a;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-family: monospace;
  overflow-x: auto;
  margin: 4px 0 0 20px;
  color: #78350f;
}

.tool-result {
  margin: 4px 0 0 20px;
  padding: 10px 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 14px;
}

.download-action {
  margin-top: 12px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.download-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: #ffffff;
  color: #0284c7;
  border-radius: 8px;
  font-weight: 600;
  font-size: 14px;
  text-decoration: none;
  transition: all 0.2s;
}

.download-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.download-hint {
  color: #ffffff;
  font-size: 13px;
  opacity: 0.9;
}

.tool-waiting {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 0;
}

.waiting-dot {
  width: 8px;
  height: 8px;
  background: #f59e0b;
  border-radius: 50%;
  animation: bounce 1.4s infinite;
}

.waiting-dot:nth-child(1) { animation-delay: -0.32s; }
.waiting-dot:nth-child(2) { animation-delay: -0.16s; }

.waiting-text {
  margin-left: 8px;
  font-size: 13px;
  color: #a16207;
}

/* 通用 */
.avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 19px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
}

.typing-cursor {
  animation: blink 1s infinite;
  color: #0ea5e9;
  margin-left: 3px;
  font-weight: bold;
}

.thinking-state {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 0;
}

.thinking-dot {
  width: 10px;
  height: 10px;
  background: #0ea5e9;
  border-radius: 50%;
  animation: bounce 1.4s infinite;
}

.thinking-dot:nth-child(1) { animation-delay: -0.32s; }
.thinking-dot:nth-child(2) { animation-delay: -0.16s; }

.thinking-text {
  margin-left: 8px;
  font-size: 14px;
  color: #64748b;
  font-weight: 500;
}

.empty-response {
  font-size: 14px;
  color: #94a3b8;
  font-style: italic;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.4); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>