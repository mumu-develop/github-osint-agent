<template>
  <div class="alert-list">
    <div class="alert-header">
      <h1>预警列表</h1>
      <div class="filter-bar">
        <select v-model="filterSeverity" class="filter-select">
          <option value="">全部严重程度</option>
          <option value="CRITICAL">严重</option>
          <option value="HIGH">高危</option>
          <option value="MEDIUM">中危</option>
          <option value="LOW">低危</option>
          <option value="INFO">信息</option>
        </select>
        <select v-model="filterType" class="filter-select">
          <option value="">全部类型</option>
          <option value="CVE">CVE漏洞</option>
          <option value="SECRET">敏感信息</option>
          <option value="LICENSE">许可证</option>
          <option value="COMMUNITY">社区健康</option>
          <option value="TREND">趋势分析</option>
          <option value="SUPPLY_CHAIN">供应链风险</option>
        </select>
        <select v-model="filterAcknowledged" class="filter-select">
          <option value="">全部状态</option>
          <option value="false">未处理</option>
          <option value="true">已处理</option>
        </select>
      </div>
    </div>

    <!-- 发现详情弹窗 -->
    <div class="modal-overlay" v-if="selectedFinding" @click.self="selectedFinding = null">
      <div class="modal">
        <div class="modal-header">
          <h2>发现详情</h2>
          <button class="close-btn" @click="selectedFinding = null">×</button>
        </div>
        <div class="modal-body">
          <div class="detail-section">
            <div class="detail-row">
              <span class="label">仓库</span>
              <span class="value repo-link">{{ selectedFinding.repo_full_name }}</span>
            </div>
            <div class="detail-row">
              <span class="label">类型</span>
              <span class="value">{{ selectedFinding.finding_type }}</span>
            </div>
            <div class="detail-row">
              <span class="label">严重程度</span>
              <span class="severity-badge" :class="selectedFinding.severity.toLowerCase()">
                {{ selectedFinding.severity }}
              </span>
            </div>
            <div class="detail-row">
              <span class="label">标题</span>
              <span class="value">{{ selectedFinding.title }}</span>
            </div>
            <div class="detail-row full-width">
              <span class="label">描述</span>
              <span class="value description">{{ selectedFinding.description || '无详细描述' }}</span>
            </div>
          </div>

          <!-- 详细信息 -->
          <div class="detail-section" v-if="selectedFinding.detail">
            <h3>详细信息</h3>
            <div class="detail-json">
              <div class="json-item" v-if="selectedFinding.detail.cve_id">
                <span class="json-key">CVE ID:</span>
                <span class="json-value">{{ selectedFinding.detail.cve_id }}</span>
              </div>
              <div class="json-item" v-if="selectedFinding.detail.package">
                <span class="json-key">依赖包:</span>
                <span class="json-value">{{ selectedFinding.detail.package }}@{{ selectedFinding.detail.version }}</span>
              </div>
              <div class="json-item" v-if="selectedFinding.detail.file">
                <span class="json-key">文件:</span>
                <span class="json-value">{{ selectedFinding.detail.file }}</span>
              </div>
              <div class="json-item" v-if="selectedFinding.detail.pattern_type">
                <span class="json-key">敏感信息类型:</span>
                <span class="json-value">{{ selectedFinding.detail.pattern_type }}</span>
              </div>
              <div class="json-item" v-if="selectedFinding.detail.commit_sha">
                <span class="json-key">提交SHA:</span>
                <span class="json-value">{{ selectedFinding.detail.commit_sha }}</span>
              </div>
              <div class="json-item" v-if="selectedFinding.detail.aliases?.length">
                <span class="json-key">相关CVE:</span>
                <span class="json-value">{{ selectedFinding.detail.aliases.join(', ') }}</span>
              </div>
            </div>
          </div>

          <!-- 社区健康：未合并的 PR 列表 -->
          <div class="detail-section" v-if="selectedFinding.finding_type === 'COMMUNITY' && selectedFinding.detail?.stale_prs?.length">
            <h3>🔴 长时间未合并的 PR</h3>
            <div class="stale-list">
              <div class="stale-item" v-for="pr in selectedFinding.detail.stale_prs" :key="pr.number">
                <a :href="pr.url" target="_blank" class="stale-link">
                  <span class="stale-number">#{{ pr.number }}</span>
                  <span class="stale-title">{{ pr.title }}</span>
                </a>
                <div class="stale-meta">
                  <span class="stale-author">@{{ pr.author }}</span>
                  <span class="stale-days" :class="{ critical: pr.waiting_days > 30, warning: pr.waiting_days > 7 }">
                    等待 {{ pr.waiting_days }} 天
                  </span>
                </div>
              </div>
            </div>
            <div class="stale-summary" v-if="selectedFinding.detail.stale_prs_count > selectedFinding.detail.stale_prs.length">
              还有 {{ selectedFinding.detail.stale_prs_count - selectedFinding.detail.stale_prs.length }} 个未合并的 PR
            </div>
          </div>

          <!-- 社区健康：未处理的 Issue 列表 -->
          <div class="detail-section" v-if="selectedFinding.finding_type === 'COMMUNITY' && selectedFinding.detail?.stale_issues?.length">
            <h3>🟠 长时间未处理的 Issue</h3>
            <div class="stale-list">
              <div class="stale-item" v-for="issue in selectedFinding.detail.stale_issues" :key="issue.number">
                <a :href="issue.url" target="_blank" class="stale-link">
                  <span class="stale-number">#{{ issue.number }}</span>
                  <span class="stale-title">{{ issue.title }}</span>
                </a>
                <div class="stale-meta">
                  <span class="stale-author">@{{ issue.author }}</span>
                  <span class="stale-days" :class="{ critical: issue.waiting_days > 60, warning: issue.waiting_days > 14 }">
                    等待 {{ issue.waiting_days }} 天
                  </span>
                  <span class="stale-labels" v-if="issue.labels?.length">
                    {{ issue.labels.join(', ') }}
                  </span>
                </div>
              </div>
            </div>
            <div class="stale-summary" v-if="selectedFinding.detail.stale_issues_count > selectedFinding.detail.stale_issues.length">
              还有 {{ selectedFinding.detail.stale_issues_count - selectedFinding.detail.stale_issues.length }} 个未处理的 Issue
            </div>
          </div>

          <!-- 时间信息 -->
          <div class="detail-section">
            <div class="detail-row">
              <span class="label">发现时间</span>
              <span class="value">{{ formatTime(selectedFinding.created_at) }}</span>
            </div>
            <div class="detail-row" v-if="selectedFinding.is_acknowledged">
              <span class="label">处理状态</span>
              <span class="value">已由 {{ selectedFinding.acknowledged_by }} 确认处理</span>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <a :href="selectedFinding.github_url || `https://github.com/${selectedFinding.repo_full_name}`" target="_blank" class="github-link-btn">
            查看 GitHub
          </a>
          <button class="ack-btn" v-if="!selectedFinding.is_acknowledged"
                  @click="handleAcknowledge(selectedFinding)">
            确认处理
          </button>
          <button class="close-modal-btn" @click="selectedFinding = null">关闭</button>
        </div>
      </div>
    </div>

    <!-- 列表 -->
    <div class="list-container">
      <div class="alert-items" v-if="findings.length">
        <div class="alert-item" v-for="f in findings" :key="f.id" @click="showFindingDetail(f)">
          <div class="alert-left">
            <span class="severity-badge" :class="f.severity.toLowerCase()">{{ f.severity }}</span>
            <span class="type-badge">{{ f.finding_type }}</span>
          </div>

          <div class="alert-main">
            <a :href="f.github_url || `https://github.com/${f.repo_full_name}`" target="_blank" class="repo-link">{{ f.repo_full_name }}</a>
            <div class="alert-title">{{ f.title }}</div>
            <div class="alert-desc" v-if="f.description">{{ f.description }}</div>
            <div class="alert-detail" v-if="f.detail">
              <span v-if="f.detail.cve_id">CVE: {{ f.detail.cve_id }}</span>
              <span v-if="f.detail.file">文件: {{ f.detail.file }}</span>
              <span v-if="f.detail.package">包: {{ f.detail.package }}@{{ f.detail.version }}</span>
            </div>
          </div>

          <div class="alert-right">
            <div class="time-info">
              <span class="created-time">{{ formatTime(f.created_at) }}</span>
            </div>
            <button
              class="ack-btn"
              :class="{ acknowledged: f.is_acknowledged }"
              @click.stop="handleAcknowledge(f)"
              :disabled="f.is_acknowledged"
            >
              {{ f.is_acknowledged ? '已处理' : '确认处理' }}
            </button>
          </div>
        </div>
      </div>

      <div class="empty-state" v-else>
        <p>暂无预警记录</p>
      </div>

      <!-- 分页 -->
      <div class="pagination" v-if="totalPages > 1">
        <button class="page-btn" @click="prevPage" :disabled="page <= 1">上一页</button>
        <span class="page-info">第 {{ page }} / {{ totalPages }} 页</span>
        <button class="page-btn" @click="nextPage" :disabled="page >= totalPages">下一页</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { getFindings, acknowledgeFinding } from '../api/dashboard.js'

const findings = ref([])
const selectedFinding = ref(null)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const totalPages = ref(0)

const filterSeverity = ref('')
const filterType = ref('')
const filterAcknowledged = ref('')

async function loadFindings() {
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value
    }
    if (filterSeverity.value) params.severity = filterSeverity.value
    if (filterType.value) params.finding_type = filterType.value
    if (filterAcknowledged.value !== '') params.is_acknowledged = filterAcknowledged.value === 'true'

    const data = await getFindings(params)
    findings.value = data.findings || []
    total.value = data.total || 0
    totalPages.value = data.total_pages || 0
  } catch (e) {
    console.error('加载发现列表失败:', e)
  }
}

async function handleAcknowledge(finding) {
  try {
    await acknowledgeFinding(finding.id)
    finding.is_acknowledged = true
    finding.acknowledged_by = 'user'
  } catch (e) {
    console.error('确认失败:', e)
  }
}

function showFindingDetail(finding) {
  selectedFinding.value = finding
}

function prevPage() {
  if (page.value > 1) {
    page.value--
    loadFindings()
  }
}

function nextPage() {
  if (page.value < totalPages.value) {
    page.value++
    loadFindings()
  }
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN')
}

// 监听筛选变化
watch([filterSeverity, filterType, filterAcknowledged], () => {
  page.value = 1
  loadFindings()
})

onMounted(() => {
  loadFindings()
})

// 暴露方法供父组件调用
function setFilters(filters) {
  if (filters.severity) {
    filterSeverity.value = filters.severity
  }
  if (filters.is_acknowledged !== undefined) {
    filterAcknowledged.value = String(filters.is_acknowledged)
  }
  page.value = 1
  loadFindings()
}

defineExpose({ setFilters })
</script>

<style scoped>
.alert-list {
  padding: 24px;
  background: #f8fafc;
}

.alert-header {
  margin-bottom: 24px;
}

.alert-header h1 {
  font-size: 24px;
  color: #1e293b;
  margin-bottom: 16px;
}

.filter-bar {
  display: flex;
  gap: 12px;
}

.filter-select {
  padding: 10px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: white;
  font-size: 14px;
  color: #1e293b;
}

.list-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.alert-items {
  padding: 16px;
}

.alert-item {
  display: flex;
  padding: 16px;
  border-bottom: 1px solid #f1f5f9;
  gap: 16px;
  cursor: pointer;
  transition: background 0.2s;
}

.alert-item:hover {
  background: #f8fafc;
}

.alert-item:last-child {
  border-bottom: none;
}

.alert-left {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 100px;
}

.severity-badge {
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.severity-badge.critical { background: #fef2f2; color: #dc2626; }
.severity-badge.high { background: #fff7ed; color: #ea580c; }
.severity-badge.medium { background: #fefce8; color: #eab308; }
.severity-badge.low { background: #f0fdf4; color: #22c55e; }
.severity-badge.info { background: #eff6ff; color: #3b82f6; }

.type-badge {
  padding: 4px 8px;
  background: #f1f5f9;
  border-radius: 4px;
  font-size: 12px;
  color: #64748b;
}

.alert-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.repo-link {
  font-size: 14px;
  color: #0ea5e9;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
}

.repo-link:hover {
  text-decoration: underline;
}

.alert-title {
  font-size: 16px;
  color: #1e293b;
  font-weight: 500;
}

.alert-desc {
  font-size: 14px;
  color: #64748b;
}

.alert-detail {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #94a3b8;
}

.alert-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
  min-width: 120px;
}

.time-info {
  font-size: 12px;
  color: #94a3b8;
}

.ack-btn {
  padding: 8px 16px;
  background: #0ea5e9;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
}

.ack-btn.acknowledged {
  background: #e2e8f0;
  color: #64748b;
  cursor: not-allowed;
}

.empty-state {
  padding: 60px;
  text-align: center;
  color: #94a3b8;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  padding: 20px;
  border-top: 1px solid #f1f5f9;
}

.page-btn {
  padding: 10px 20px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #1e293b;
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 14px;
  color: #64748b;
}

/* Modal styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: white;
  border-radius: 12px;
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #f1f5f9;
}

.modal-header h2 {
  font-size: 18px;
  color: #1e293b;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #94a3b8;
  cursor: pointer;
}

.modal-body {
  padding: 20px;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section h3 {
  font-size: 14px;
  color: #64748b;
  margin-bottom: 12px;
}

.detail-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid #f8fafc;
}

.detail-row.full-width {
  flex-direction: column;
  gap: 8px;
}

.detail-row .label {
  width: 80px;
  font-size: 14px;
  color: #64748b;
}

.detail-row .value {
  font-size: 14px;
  color: #1e293b;
}

.detail-row .value.description {
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-row .repo-link {
  color: #0ea5e9;
}

.detail-json {
  background: #f8fafc;
  padding: 12px;
  border-radius: 8px;
}

.json-item {
  display: flex;
  gap: 12px;
  padding: 8px 0;
}

.json-key {
  font-size: 12px;
  color: #64748b;
  min-width: 100px;
}

.json-value {
  font-size: 14px;
  color: #1e293b;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid #f1f5f9;
}

.github-link-btn {
  padding: 10px 20px;
  background: #f1f5f9;
  color: #1e293b;
  border-radius: 8px;
  text-decoration: none;
  font-size: 14px;
}

.close-modal-btn {
  padding: 10px 20px;
  background: #f1f5f9;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
}

/* PR/Issue 未处理列表样式 */
.stale-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stale-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.stale-link {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: #0ea5e9;
}

.stale-link:hover .stale-title {
  text-decoration: underline;
}

.stale-number {
  font-weight: 600;
  font-size: 14px;
}

.stale-title {
  font-size: 14px;
  color: #1e293b;
}

.stale-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #64748b;
}

.stale-author {
  color: #94a3b8;
}

.stale-days {
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.stale-days.warning {
  background: #fef3c7;
  color: #b45309;
}

.stale-days.critical {
  background: #fee2e2;
  color: #dc2626;
}

.stale-labels {
  color: #94a3b8;
  font-size: 11px;
}

.stale-summary {
  padding: 12px;
  text-align: center;
  color: #64748b;
  font-size: 13px;
  background: #f8fafc;
  border-radius: 8px;
  margin-top: 8px;
}
</style>