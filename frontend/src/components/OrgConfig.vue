<template>
  <div class="org-config">
    <div class="org-header">
      <h1>组织配置管理</h1>
      <button class="create-btn" @click="showCreateModal = true">
        + 添加组织
      </button>
    </div>

    <!-- 组织列表 -->
    <div class="org-list">
      <div class="org-item" v-for="org in orgs" :key="org.id">
        <div class="org-main" @click="selectOrg(org)">
          <div class="org-info">
            <span class="org-name">{{ org.org_name }}</span>
            <span class="org-display-name">{{ org.display_name || org.org_name }}</span>
            <span class="org-status-badge" :class="{ enabled: org.scan_enabled }">
              {{ org.scan_enabled ? '✓ 扫描启用' : '○ 扫描暂停' }}
            </span>
          </div>
          <div class="org-meta">
            <span class="meta-item">频率: {{ org.scan_frequency }}</span>
            <span class="meta-item" v-if="org.alert_channels?.dingtalk_webhook">钉钉 ✓</span>
            <span class="meta-item" v-if="org.alert_channels?.feishu_webhook">飞书 ✓</span>
          </div>
        </div>
        <div class="org-actions">
          <button class="action-btn scan" @click="handleTriggerScan(org.org_name)" :disabled="scanning">
            {{ scanningOrg === org.org_name ? '扫描中...' : '扫描' }}
          </button>
          <button class="action-btn edit" @click="editOrg(org)">编辑</button>
          <button class="action-btn delete" @click="handleDeleteOrg(org.org_name)">删除</button>
        </div>
      </div>

      <div class="empty-state" v-if="orgs.length === 0">
        <p>暂无组织配置</p>
        <p class="hint">点击上方「添加组织」按钮创建</p>
      </div>
    </div>

    <!-- 组织详情面板（扫描任务和子任务） -->
    <div class="org-detail-panel" v-if="selectedOrg">
      <div class="panel-header">
        <h2>{{ selectedOrg.org_name }} - 扫描任务</h2>
        <div class="panel-actions">
          <button class="scan-btn" @click="handleTriggerScan(selectedOrg.org_name)" :disabled="scanning && scanningOrg === selectedOrg.org_name">
            {{ scanning && scanningOrg === selectedOrg.org_name ? '创建中...' : (activeTask?.status === 'running' ? '重新扫描' : '触发扫描') }}
          </button>
          <button class="close-panel" @click="closeOrgDetail">×</button>
        </div>
      </div>

      <!-- 加载状态 -->
      <div class="loading-state" v-if="activeTaskLoading">
        <p>加载任务信息...</p>
      </div>

      <!-- 无任务状态 -->
      <div class="empty-state" v-else-if="!activeTask">
        <p>该组织暂无扫描任务</p>
        <p class="hint">点击上方「触发扫描」按钮开始扫描</p>
      </div>

      <!-- 有任务状态 -->
      <div class="task-info" v-else>
        <!-- 任务状态卡片 -->
        <div class="task-card">
          <div class="task-header">
            <span class="task-run-id">{{ activeTask.run_id }}</span>
            <span class="task-trigger-badge" :class="activeTask.trigger_by">
              {{ activeTask.trigger_by === 'manual' ? '手动触发' : (activeTask.trigger_by === 'scheduler' ? '定时触发' : '触发扫描') }}
            </span>
            <span class="task-type-badge">{{ activeTask.scan_type }}</span>
            <span class="task-status-badge" :class="activeTask.status">
              {{ getStatusLabel(activeTask.status) }}
            </span>
          </div>

          <!-- 阶段进度（运行中或已完成都显示） -->
          <div class="phase-progress-panel" v-if="activeTask.phase && (activeTask.status === 'running' || activeTask.status === 'completed')">
            <div class="phase-header">
              <span class="label">扫描阶段:</span>
              <span class="phase-name" :class="activeTask.phase">{{ getPhaseLabel(activeTask.phase) }}</span>
              <span class="phase-status-badge" v-if="activeTask.status === 'completed'">✓ 完成</span>
            </div>
            <!-- 阶段步骤指示器 -->
            <div class="phase-steps">
              <template v-for="(step, idx) in phaseSteps" :key="step.key">
                <div class="phase-step"
                     :class="{ active: activeTask.phase === step.key && activeTask.status === 'running', done: isPhaseDone(step.key, activeTask.phase) || activeTask.status === 'completed', pending: isPhasePending(step.key, activeTask.phase) && activeTask.status !== 'completed' }">
                  <div class="step-icon">{{ step.icon }}</div>
                  <div class="step-label">{{ step.label }}</div>
                  <div class="step-ring" v-if="activeTask.phase === step.key && activeTask.status === 'running'"></div>
                </div>
                <!-- 箭头连接器（最后一个步骤不需要） -->
                <div class="phase-arrow" v-if="idx < phaseSteps.length - 1"
                     :class="{ active: isArrowActive(idx, activeTask.phase) && activeTask.status === 'running', done: isArrowDone(idx, activeTask.phase) || activeTask.status === 'completed' }">
                  <div class="arrow-line"></div>
                  <div class="arrow-head">→</div>
                  <div class="arrow-flow" v-if="isArrowFlowing(idx, activeTask.phase) && activeTask.status === 'running'"></div>
                </div>
              </template>
            </div>
            <!-- 扫描阶段的维度进度（仅运行中显示） -->
            <div class="dimension-progress" v-if="activeTask.phase === 'scanning' && activeTask.phase_progress && activeTask.status === 'running'">
              <div class="dim-progress-item" v-for="(progress, dim) in activeTask.phase_progress" :key="dim">
                <span class="dim-name">{{ getDimensionLabel(dim) }}</span>
                <div class="dim-bar">
                  <div class="dim-fill" :style="{ width: getDimProgressPercent(progress) + '%' }"></div>
                </div>
                <span class="dim-count">{{ progress.done }}/{{ progress.total }}</span>
              </div>
            </div>
          </div>

          <!-- 运行中状态：实时进度 -->
          <div class="task-running-info" v-if="activeTask.status === 'running'">
            <div class="running-status">
              <span class="pulse-icon">●</span>
              <span>正在扫描中...</span>
              <span class="current-repo" v-if="scanProgress?.current_repo">
                当前: {{ scanProgress.current_repo }}
              </span>
            </div>
            <div class="progress-bar-mini">
              <div class="progress-fill-mini"
                   :style="{ width: (progressSummary?.completed / progressSummary?.total * 100 || 0) + '%' }"></div>
            </div>
            <div class="progress-text-mini">
              {{ progressSummary?.completed || 0 }} / {{ progressSummary?.total || 0 }}
              ({{ Math.round((progressSummary?.completed / progressSummary?.total || 0) * 100) }}%)
            </div>
          </div>

          <!-- 完成状态：结果摘要 -->
          <div class="task-result-info" v-if="activeTask.status === 'completed'">
            <div class="result-summary">
              <span class="result-icon success">✓</span>
              <span>扫描完成</span>
              <span class="result-detail">
                发现 {{ activeTask.findings_count }} 个问题
                <span v-if="progressSummary?.high_severity > 0" class="high-alert">
                  ({{ progressSummary?.high_severity }} 个高危)
                </span>
              </span>
            </div>
            <!-- 告警推送状态 -->
            <div class="alert-status-info" v-if="activeTask.alert_status">
              <div class="alert-status-row">
                <span class="alert-label">告警推送:</span>
                <span class="alert-status-badge" :class="activeTask.alert_status">
                  {{ getAlertStatusLabel(activeTask.alert_status) }}
                </span>
              </div>
              <div class="alert-details" v-if="activeTask.alert_status === 'sent'">
                <span class="alert-detail">推送 {{ activeTask.alert_findings_count || 0 }} 个问题到钉钉</span>
              </div>
              <div class="alert-details warning" v-if="activeTask.alert_status === 'failed'">
                <span class="alert-error">{{ activeTask.alert_error || '推送失败' }}</span>
              </div>
              <div class="alert-details info" v-if="activeTask.alert_status === 'skipped'">
                <span class="alert-info">{{ activeTask.alert_error || '按规则不推送' }}</span>
              </div>
            </div>
          </div>

          <!-- 失败状态 -->
          <div class="task-result-info failed" v-if="activeTask.status === 'failed'">
            <div class="result-summary">
              <span class="result-icon failed">✗</span>
              <span>扫描失败</span>
              <span class="error-message" v-if="activeTask.error_message">{{ activeTask.error_message }}</span>
            </div>
          </div>

          <!-- 暂停状态 -->
          <div class="task-result-info paused" v-if="activeTask.status === 'paused'">
            <div class="result-summary">
              <span class="result-icon paused">⏸</span>
              <span>任务已暂停</span>
              <span class="result-detail">
                已扫描 {{ progressSummary?.completed || 0 }} / {{ progressSummary?.total || 0 }}
              </span>
            </div>
          </div>

          <!-- 统计信息 -->
          <div class="task-stats">
            <div class="stat-item">
              <span class="stat-label">仓库总数</span>
              <span class="stat-value">{{ activeTask.total_repos }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">发现问题</span>
              <span class="stat-value findings">{{ activeTask.findings_count }}</span>
            </div>
            <div class="stat-item" v-if="activeTask.started_at">
              <span class="stat-label">开始时间</span>
              <span class="stat-value">{{ formatTime(activeTask.started_at) }}</span>
            </div>
            <div class="stat-item" v-if="activeTask.completed_at">
              <span class="stat-label">完成时间</span>
              <span class="stat-value">{{ formatTime(activeTask.completed_at) }}</span>
            </div>
          </div>

          <!-- 控制按钮 -->
          <div class="task-controls" v-if="activeTask.status === 'running' || activeTask.status === 'paused' || activeTask.status === 'pending'">
            <button class="pause-btn-mini" @click="handlePauseScan" v-if="activeTask.status === 'running'">
              暂停
            </button>
            <button class="resume-btn-mini" @click="handleResumeScan" v-if="activeTask.status === 'paused'">
              恢复
            </button>
            <button class="cancel-btn-mini" @click="handleCancelScan" v-if="activeTask.status === 'running' || activeTask.status === 'paused' || activeTask.status === 'pending'">
              取消
            </button>
            <!-- 强制重置按钮：用于卡住的任务 -->
            <button class="force-reset-btn" @click="handleForceResetScan" v-if="activeTask.status === 'running'" title="服务异常终止后状态卡住时使用">
              强制重置
            </button>
            <!-- 异常任务强制终止按钮：pending或running但没有子任务 -->
            <button class="force-stop-btn" @click="handleForceStop" v-if="subtasks.length === 0">
              强制终止
            </button>
          </div>
        </div>

        <!-- 子任务列表 -->
        <div class="subtask-list">
          <div class="subtask-header">
            <span>子任务列表（{{ subtasks.length }} 个仓库）</span>
            <span class="subtask-summary">
              ✅ {{ progressSummary?.completed || 0 }}
              ⏳ {{ progressSummary?.running || 0 }}
              ⏸️ {{ progressSummary?.pending || 0 }}
              ❌ {{ progressSummary?.failed || 0 }}
            </span>
          </div>
          <div class="subtask-items">
            <div class="subtask-item" v-for="subtask in subtasks" :key="subtask.id"
                 :class="{ expanded: expandedSubtasks.includes(subtask.id) }">
              <div class="subtask-main" @click="toggleSubtask(subtask.id)">
                <span class="expand-icon">{{ expandedSubtasks.includes(subtask.id) ? '▼' : '▶' }}</span>
                <span class="subtask-repo">{{ subtask.repo_full_name }}</span>
                <span class="subtask-status" :class="subtask.status">
                  {{ getStatusLabel(subtask.status) }}
                </span>
                <span class="subtask-findings" v-if="subtask.findings_count > 0">
                  {{ subtask.findings_count }} 问题
                </span>
              </div>
              <!-- 展开后显示具体问题 -->
              <div class="subtask-findings-detail" v-if="expandedSubtasks.includes(subtask.id) && subtask.findings?.length > 0">
                <div class="finding-item" v-for="(f, idx) in subtask.findings" :key="idx">
                  <span class="finding-severity" :class="f.severity?.toLowerCase()">{{ f.severity }}</span>
                  <span class="finding-type">{{ f.finding_type }}</span>
                  <span class="finding-title">{{ f.title }}</span>
                </div>
                <div v-if="subtask.findings_count > subtask.findings?.length" class="finding-more">
                  还有 {{ subtask.findings_count - subtask.findings.length }} 个问题...
                </div>
              </div>
              <div class="subtask-findings-detail empty" v-if="expandedSubtasks.includes(subtask.id) && !subtask.findings?.length && subtask.status === 'completed'">
                <span>暂无发现问题</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 查看历史按钮 -->
        <div class="history-section">
          <button class="history-btn" @click="loadOrgHistory(selectedOrg.org_name)">
            查看历史记录
          </button>
          <button class="report-btn" @click="handleViewReport" v-if="activeTask?.status === 'completed'">
            查看分析报告
          </button>
        </div>
      </div>
    </div>

    <!-- 报告弹窗 -->
    <div class="modal-overlay" v-if="showReportModal" @click.self="closeReportModal">
      <div class="modal modal-large">
        <div class="modal-header">
          <h2>深度分析报告</h2>
          <button class="close-btn" @click="closeReportModal">×</button>
        </div>
        <div class="modal-body report-body">
          <div v-if="reportLoading" class="report-loading">加载中...</div>
          <div v-else-if="!reportData?.has_report" class="report-empty">
            <p>该扫描任务暂无分析报告</p>
            <p class="hint">深度分析报告会在扫描完成后自动生成</p>
          </div>
          <div v-else class="report-content">
            <div class="report-summary">
              <span class="report-title">{{ reportData.report.title }}</span>
              <span class="report-time">{{ formatTime(reportData.report.created_at) }}</span>
            </div>
            <div class="report-summary-text" v-if="reportData.report.summary">
              {{ reportData.report.summary }}
            </div>
            <div class="report-recommendations" v-if="reportData.report.recommendations?.length">
              <h4>修复建议</h4>
              <ul>
                <li v-for="(rec, idx) in reportData.report.recommendations" :key="idx">{{ rec }}</li>
              </ul>
            </div>
            <div class="report-markdown">
              <MarkdownRenderer :content="reportData.report.content" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建/编辑弹窗 -->
    <div class="modal-overlay" v-if="showCreateModal" @click.self="closeModal">
      <div class="modal modal-large">
        <div class="modal-header">
          <h2>{{ editingOrg ? '编辑组织' : '添加组织' }}</h2>
          <button class="close-btn" @click="closeModal">×</button>
        </div>

        <div class="modal-body">
          <!-- 基本信息 -->
          <div class="section">
            <h3>基本信息</h3>
            <div class="form-row">
              <div class="form-group">
                <label>GitHub 组织名称 *</label>
                <input type="text" v-model="form.org_name" placeholder="如: SOFAStack"
                       @input="validateOrgName" :disabled="editingOrg" />
                <span class="validation-status" v-if="orgValidation.status">
                  {{ orgValidation.status === 'valid' ? '✓ 组织存在' : '✗ 组织不存在' }}
                </span>
                <button class="validate-btn" @click="checkGithubOrg" v-if="!editingOrg && form.org_name">
                  验证
                </button>
              </div>
              <div class="form-group">
                <label>显示名称</label>
                <input type="text" v-model="form.display_name" placeholder="如: 蚂蚁金服SOFAStack" />
              </div>
            </div>
          </div>

          <!-- 扫描配置 -->
          <div class="section">
            <h3>扫描配置</h3>
            <div class="form-row">
              <div class="form-group">
                <label>扫描频率</label>
                <select v-model="form.scan_frequency">
                  <option value="hourly">每小时扫描（高频监控）</option>
                  <option value="daily">每日扫描（推荐）</option>
                  <option value="weekly">每周扫描（低频监控）</option>
                </select>
              </div>
              <div class="form-group toggle-group">
                <label>定时扫描</label>
                <div class="toggle-switch">
                  <input type="checkbox" v-model="form.scan_enabled" />
                  <span class="toggle-label">{{ form.scan_enabled ? '已启用' : '已暂停' }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 扫描维度配置 -->
          <div class="section">
            <h3>扫描维度配置</h3>
            <div class="template-buttons">
              <button class="template-btn" @click="applyTemplate('basic')">基础安全</button>
              <button class="template-btn" @click="applyTemplate('standard')">标准扫描</button>
              <button class="template-btn" @click="applyTemplate('deep')">深度审计</button>
              <button class="template-btn" @click="applyTemplate('compliance_only')">合规检查</button>
              <button class="template-btn" @click="applyTemplate('security_focus')">安全专项</button>
            </div>

            <!-- 基础扫描维度 -->
            <div class="dimension-section">
              <div class="dimension-header">基础扫描维度</div>
              <div class="dimension-grid">
                <div class="dimension-item">
                  <input type="checkbox" v-model="form.scan_dimensions.cve" />
                  <label>CVE漏洞扫描</label>
                  <span class="hint">依赖分析 + OSV.dev</span>
                </div>
                <div class="dimension-item">
                  <input type="checkbox" v-model="form.scan_dimensions.secret" />
                  <label>敏感信息检测</label>
                  <span class="hint">密钥/Token泄露</span>
                </div>
                <div class="dimension-item">
                  <input type="checkbox" v-model="form.scan_dimensions.license" />
                  <label>许可证合规</label>
                  <span class="hint">开源许可证检查</span>
                </div>
                <div class="dimension-item">
                  <input type="checkbox" v-model="form.scan_dimensions.community" />
                  <label>社区健康度</label>
                  <span class="hint">活跃度/维护状态</span>
                </div>
              </div>
            </div>

            <!-- LLM深度分析维度 -->
            <div class="dimension-section llm-section-block">
              <div class="dimension-header llm-header">LLM深度分析维度</div>
              <div class="dimension-grid llm-grid">
                <div class="dimension-item">
                  <input type="checkbox" v-model="form.scan_dimensions.trend" />
                  <label>趋势分析（Star历史、提交趋势）</label>
                </div>
                <div class="dimension-item">
                  <input type="checkbox" v-model="form.scan_dimensions.supply_chain" />
                  <label>供应链风险（依赖可信度）</label>
                </div>
              </div>
              <div class="llm-toggle" v-if="hasLlmDimension">
                <div class="toggle-switch">
                  <input type="checkbox" v-model="form.llm_enabled" />
                  <span class="toggle-label">启用LLM分析 {{ form.llm_enabled ? '(已启用)' : '(未启用)' }}</span>
                </div>
              </div>
            </div>

            <!-- 报告配置 -->
            <div class="section report-section">
              <h3>扫描报告配置</h3>
              <div class="form-group">
                <div class="toggle-switch">
                  <input type="checkbox" v-model="form.generate_report" />
                  <span class="toggle-label">
                    扫描完成后生成分析报告
                    <span class="toggle-status">{{ form.generate_report ? '(已启用)' : '(不生成)' }}</span>
                  </span>
                </div>
                <p class="field-hint">勾选后，扫描完成会自动生成深度分析报告，包含问题统计和修复建议</p>
              </div>
            </div>
          </div>

          <!-- 预警配置 -->
          <div class="section">
            <h3>预警推送配置</h3>
            <div class="form-group">
              <label>钉钉机器人 Webhook</label>
              <input type="text" v-model="form.dingtalk_webhook"
                     placeholder="https://oapi.dingtalk.com/robot/send?access_token=xxx" />
              <p class="field-hint">获取方式: 钉钉群 → 群设置 → 智能群助手 → 添加自定义机器人</p>
            </div>
            <div class="form-group">
              <label>钉钉加签密钥（可选）</label>
              <input type="text" v-model="form.dingtalk_secret" placeholder="SECxxx" />
            </div>
            <div class="form-group">
              <label>飞书机器人 Webhook</label>
              <input type="text" v-model="form.feishu_webhook"
                     placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx" />
            </div>

            <!-- 预警规则 -->
            <div class="form-group">
              <label>推送规则（每个等级独立配置）</label>
              <div class="alert-rules-config">
                <div class="rule-row" v-for="severity in severityLevels" :key="severity.key">
                  <span class="severity-badge" :class="severity.key.toLowerCase()">
                    {{ severity.icon }} {{ severity.label }}
                  </span>
                  <select v-model="form.alert_rules[severity.key]" class="rule-select">
                    <option value="immediate">立即推送（LLM 汇总分析）</option>
                    <option value="disabled">不推送（仅落库）</option>
                  </select>
                </div>
              </div>
              <p class="field-hint">立即推送：通过 LLM 汇总分析，生成精简报告后推送钉钉</p>
            </div>
          </div>

          <!-- 过滤配置 -->
          <div class="section">
            <h3>过滤规则（可选）</h3>
            <div class="form-group">
              <label>只监控以下仓库（留空则监控全部）</label>
              <textarea v-model="form.repo_filter" placeholder="sofa-rpc, sofa-boot, sofa-jarslink（逗号分隔）"></textarea>
            </div>
            <div class="form-group">
              <label>忽略以下文件路径</label>
              <textarea v-model="form.path_exclude" placeholder="test/, docs/, examples/（逗号分隔）"></textarea>
            </div>
          </div>

          <!-- SECRET 过滤配置 -->
          <div class="section" v-if="form.scan_dimensions.secret">
            <h3>敏感信息扫描配置</h3>
            <p class="section-hint">配置敏感信息扫描的过滤策略，减少误报</p>
            <div class="secret-config-grid">
              <div class="config-item">
                <input type="checkbox" v-model="form.secret_filter_config.exclude_vendor" id="exclude_vendor" />
                <label for="exclude_vendor">
                  <span class="config-title">排除 vendor/ 目录</span>
                  <span class="config-desc">跳过 Go/PHP 第三方依赖</span>
                </label>
              </div>
              <div class="config-item">
                <input type="checkbox" v-model="form.secret_filter_config.exclude_node_modules" id="exclude_node_modules" />
                <label for="exclude_node_modules">
                  <span class="config-title">排除 node_modules/ 目录</span>
                  <span class="config-desc">跳过 Node.js 第三方依赖</span>
                </label>
              </div>
              <div class="config-item">
                <input type="checkbox" v-model="form.secret_filter_config.exclude_test_files" id="exclude_test_files" />
                <label for="exclude_test_files">
                  <span class="config-title">排除测试文件</span>
                  <span class="config-desc">跳过 *_test.go、test/ 等测试文件</span>
                </label>
              </div>
              <div class="config-item">
                <input type="checkbox" v-model="form.secret_filter_config.example_whitelist" id="example_whitelist" />
                <label for="example_whitelist">
                  <span class="config-title">启用示例值白名单</span>
                  <span class="config-desc">过滤官方文档示例（如 AKIAIOSFODNN7EXAMPLE）</span>
                </label>
              </div>
              <div class="config-item">
                <input type="checkbox" v-model="form.secret_filter_config.doc_file_lower_severity" id="doc_file_lower_severity" />
                <label for="doc_file_lower_severity">
                  <span class="config-title">文档文件降低严重程度</span>
                  <span class="config-desc">README、doc.go 等文档中的发现降为 INFO</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button class="cancel-btn" @click="closeModal">取消</button>
          <button class="submit-btn" @click="submitForm" :disabled="!form.org_name || (!editingOrg && orgValidation.status !== 'valid')">
            {{ editingOrg ? '保存修改' : '创建组织' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 扫描任务历史弹窗 -->
    <div class="modal-overlay" v-if="showScanHistory" @click.self="showScanHistory = false">
      <div class="modal modal-large">
        <div class="modal-header">
          <h2>扫描任务历史</h2>
          <button class="close-btn" @click="showScanHistory = false">×</button>
        </div>
        <div class="modal-body">
          <div class="scan-history-list">
            <div class="scan-task-item" v-for="task in scanTasks" :key="task.id">
              <div class="task-main">
                <span class="task-id">{{ task.run_id }}</span>
                <span class="task-type">{{ task.scan_type }}</span>
                <span class="task-org">{{ task.org_name }}</span>
              </div>
              <div class="task-status">
                <span class="status-badge" :class="task.status">{{ task.status }}</span>
                <span class="task-time">{{ task.created_at }}</span>
              </div>
              <div class="task-progress">
                <span>{{ task.scanned_repos }}/{{ task.total_repos }} 仓库</span>
                <span>发现 {{ task.findings_count }} 个问题</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 扫描进度弹窗 -->
    <div class="modal-overlay" v-if="showScanProgress">
      <div class="modal scan-progress-modal">
        <div class="modal-header">
          <h2>扫描进度</h2>
          <button class="close-btn" @click="closeScanProgress" v-if="scanProgress.status === 'completed' || scanProgress.status === 'failed'">×</button>
        </div>
        <div class="modal-body">
          <!-- 基本信息 -->
          <div class="progress-info">
            <div class="progress-org">
              <span class="label">目标组织:</span>
              <span class="value">{{ scanProgress.org_name }}</span>
            </div>
            <div class="progress-mode">
              <span class="label">扫描模式:</span>
              <span class="value">{{ scanProgress.scan_mode || 'balanced' }}</span>
            </div>
            <div class="progress-estimate" v-if="scanProgress.estimated_time_minutes > 0">
              <span class="label">预估时间:</span>
              <span class="value estimate">{{ scanProgress.estimated_time_minutes }} 分钟</span>
            </div>
          </div>

          <!-- 扫描维度 -->
          <div class="progress-dimensions" v-if="scanProgress.dimensions">
            <span class="label">扫描维度:</span>
            <div class="dimension-tags">
              <span class="dimension-tag" v-for="(enabled, dim) in scanProgress.dimensions" :key="dim" v-if="enabled">
                {{ getDimensionLabel(dim) }}
              </span>
            </div>
          </div>

          <!-- 阶段进度 -->
          <div class="phase-progress" v-if="activeTask && activeTask.phase">
            <div class="phase-header">
              <span class="label">当前阶段:</span>
              <span class="phase-name" :class="activeTask.phase">{{ getPhaseLabel(activeTask.phase) }}</span>
            </div>
            <!-- 阶段步骤指示器 -->
            <div class="phase-steps">
              <template v-for="(step, idx) in phaseSteps" :key="step.key">
                <div class="phase-step"
                     :class="{ active: activeTask.phase === step.key, done: isPhaseDone(step.key, activeTask.phase), pending: isPhasePending(step.key, activeTask.phase) }">
                  <div class="step-icon">{{ step.icon }}</div>
                  <div class="step-label">{{ step.label }}</div>
                  <div class="step-ring" v-if="activeTask.phase === step.key"></div>
                </div>
                <!-- 箭头连接器（最后一个步骤不需要） -->
                <div class="phase-arrow" v-if="idx < phaseSteps.length - 1"
                     :class="{ active: isArrowActive(idx, activeTask.phase), done: isArrowDone(idx, activeTask.phase) }">
                  <div class="arrow-line"></div>
                  <div class="arrow-head">→</div>
                  <div class="arrow-flow" v-if="isArrowFlowing(idx, activeTask.phase)"></div>
                </div>
              </template>
            </div>
            <!-- 扫描阶段的维度进度 -->
            <div class="dimension-progress" v-if="activeTask.phase === 'scanning' && activeTask.phase_progress">
              <div class="dim-progress-item" v-for="(progress, dim) in activeTask.phase_progress" :key="dim">
                <span class="dim-name">{{ getDimensionLabel(dim) }}</span>
                <div class="dim-bar">
                  <div class="dim-fill" :style="{ width: getDimProgressPercent(progress) + '%' }"></div>
                </div>
                <span class="dim-count">{{ progress.done }}/{{ progress.total }}</span>
              </div>
            </div>
          </div>

          <!-- 进度条 -->
          <div class="progress-bar-container">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
            </div>
            <div class="progress-text">
              {{ scanProgress.scanned_repos }} / {{ scanProgress.total_repos }} 仓库
              <span v-if="scanProgress.total_repos > 0">({{ progressPercent }}%)</span>
              <span v-if="scanProgress.status === 'running'">
                - 预估还需 {{ getRemainingTime }} 分钟
              </span>
            </div>
          </div>

          <!-- 状态和控制 -->
          <div class="progress-status">
            <span class="status-badge" :class="scanProgress.status">{{ getStatusLabel(scanProgress.status) }}</span>
            <span class="status-message" v-if="scanProgress.status === 'pending'">任务启动中...</span>
            <span class="status-message" v-if="scanProgress.status === 'running'">
              正在扫描: {{ scanProgress.current_repo || '准备中...' }}
            </span>
            <span class="status-message success" v-if="scanProgress.status === 'completed'">扫描完成!</span>
            <span class="status-message warning" v-if="scanProgress.status === 'paused'">任务已暂停</span>
            <span class="status-message error" v-if="scanProgress.status === 'failed'">{{ scanProgress.error_message }}</span>
          </div>

          <!-- 控制按钮 -->
          <div class="progress-controls" v-if="scanProgress.status === 'running' || scanProgress.status === 'paused'">
            <button class="pause-btn" @click="handlePauseScan" v-if="scanProgress.status === 'running'">暂停</button>
            <button class="resume-btn" @click="handleResumeScan" v-if="scanProgress.status === 'paused'">恢复</button>
            <button class="cancel-btn" @click="handleCancelScan">取消</button>
            <button class="force-reset-btn" @click="handleForceResetScan" v-if="scanProgress.status === 'running'" title="服务异常终止后状态卡住时使用">强制重置</button>
          </div>

          <!-- 发现统计 -->
          <div class="progress-findings" v-if="scanProgress.findings_count > 0">
            <span class="findings-count">发现 {{ scanProgress.findings_count }} 个问题</span>
            <span class="high-count" v-if="scanProgress.high_severity_count > 0">
              ({{ scanProgress.high_severity_count }} 个高危)
            </span>
          </div>

          <!-- 仓库列表（已扫描/正在扫描） -->
          <div class="progress-repo-list" v-if="scanProgress.subtasks && scanProgress.subtasks.length > 0">
            <div class="repo-list-header">
              <span>仓库扫描进度</span>
              <span class="repo-stats">
                ✅ {{ scanProgress.progress_stats.completed }}
                ⏳ {{ scanProgress.progress_stats.running }}
                ⏸️ {{ scanProgress.progress_stats.pending }}
                ❌ {{ scanProgress.progress_stats.failed }}
              </span>
            </div>
            <div class="repo-list-items">
              <div class="repo-item" v-for="subtask in scanProgress.subtasks.slice(0, 10)" :key="subtask.id">
                <span class="repo-name">{{ subtask.repo_full_name }}</span>
                <span class="repo-status" :class="subtask.status">
                  {{ getStatusLabel(subtask.status) }}
                </span>
                <span class="repo-findings" v-if="subtask.findings_count > 0">
                  {{ subtask.findings_count }} 问题
                </span>
              </div>
            </div>
          </div>

          <!-- 时间信息 -->
          <div class="progress-time">
            <div v-if="scanProgress.started_at">
              <span class="label">开始时间:</span>
              <span class="value">{{ formatTime(scanProgress.started_at) }}</span>
            </div>
            <div v-if="scanProgress.completed_at">
              <span class="label">完成时间:</span>
              <span class="value">{{ formatTime(scanProgress.completed_at) }}</span>
              <span class="duration" v-if="scanProgress.started_at">
                (耗时 {{ getDuration(scanProgress.started_at, scanProgress.completed_at) }})
              </span>
            </div>
            <div v-if="scanProgress.status === 'running' && scanProgress.started_at">
              <span class="label">已运行:</span>
              <span class="value">{{ getElapsedTime(scanProgress.started_at) }}</span>
            </div>
          </div>

          <!-- 完成后操作 -->
          <div class="progress-actions" v-if="scanProgress.status === 'completed' || scanProgress.status === 'failed'">
            <button class="view-findings-btn" @click="viewFindings">查看发现</button>
            <button class="view-report-btn" @click="viewReport" v-if="scanProgress.status === 'completed'">查看报告</button>
            <button class="close-btn" @click="closeScanProgress">关闭</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, onUnmounted } from 'vue'
import { getOrgs, createOrg, updateOrg, deleteOrg, triggerScan, getScanTasks, getScanStatus, getOrgScanStatus, getActiveTask, getScanHistory, triggerScanWithDimensions, getSubtaskProgress, getScanProgress, pauseScan, resumeScan, cancelScan, forceResetScan, getCurrentRunningRepo, forceStopTask, connectProgressStream, getScanReport } from '../api/dashboard.js'
import MarkdownRenderer from './MarkdownRenderer.vue'

const orgs = ref([])
const orgRepos = ref([])
const selectedOrg = ref(null)
const showCreateModal = ref(false)
const showScanHistory = ref(false)
const showScanProgress = ref(false)
const editingOrg = ref(null)
const scanning = ref(false)
const scanningOrg = ref('')
const scanTasks = ref([])

// 活跃任务状态（点击组织时显示）
const activeTask = ref(null)
const subtasks = ref([])
const progressSummary = ref(null)
const activeTaskLoading = ref(false)
const expandedSubtasks = ref([])  // 展开的子任务 ID 列表

// 报告弹窗状态
const showReportModal = ref(false)
const reportLoading = ref(false)
const reportData = ref(null)

// 扫描进度状态
const scanProgress = ref({
  run_id: '',
  org_name: '',
  scan_type: '',
  scan_mode: '',
  status: 'pending',
  phase: 'init',  // 扫描阶段
  phase_progress: {},  // 各维度进度
  total_repos: 0,
  scanned_repos: 0,
  findings_count: 0,
  high_severity_count: 0,
  estimated_time_minutes: 0,
  error_message: '',
  started_at: null,
  completed_at: null,
  dimensions: {},
  // 仓库级进度
  subtasks: [],
  current_repo: null,
  percent: 0,
  // 进度统计
  progress_stats: {
    pending: 0, running: 0, completed: 0, failed: 0, paused: 0
  }
})
let progressPollTimer = null

const orgValidation = ref({ status: '', message: '' })

const form = ref({
  org_name: '',
  display_name: '',
  scan_frequency: 'daily',
  scan_depth: 'L1_LIGHT',
  scan_enabled: true,
  scan_dimensions: {
    cve: true,
    secret: true,
    license: true,
    community: false,
    trend: false,
    code_quality: false,
    supply_chain: false
  },
  llm_enabled: false,
  generate_report: true,
  secret_filter_config: {
    exclude_vendor: true,
    exclude_node_modules: true,
    exclude_test_files: false,
    example_whitelist: true,
    doc_file_lower_severity: true
  },
  dingtalk_webhook: '',
  dingtalk_secret: '',
  feishu_webhook: '',
  alert_rules: {
    CRITICAL: 'immediate',
    HIGH: 'immediate',
    MEDIUM: 'disabled',
    LOW: 'disabled',
    INFO: 'disabled'
  },
  repo_filter: '',
  path_exclude: ''
})

// 严重等级配置（用于推送规则 UI）
const severityLevels = [
  { key: 'CRITICAL', label: '严重', icon: '🔴' },
  { key: 'HIGH', label: '高危', icon: '🟠' },
  { key: 'MEDIUM', label: '中危', icon: '🟡' },
  { key: 'LOW', label: '低危', icon: '🟢' },
  { key: 'INFO', label: '信息', icon: '🔵' },
]

// 计算是否启用了LLM维度
const hasLlmDimension = computed(() => {
  return form.value.scan_dimensions.trend ||
         form.value.scan_dimensions.supply_chain
})

// 计算扫描进度百分比
const progressPercent = computed(() => {
  // 优先使用 SSE 推送的 percent，否则自己计算
  if (scanProgress.value.percent > 0) return scanProgress.value.percent
  if (scanProgress.value.total_repos === 0) return 0
  return Math.round((scanProgress.value.scanned_repos / scanProgress.value.total_repos) * 100)
})

async function loadOrgs() {
  try {
    const data = await getOrgs()
    orgs.value = data.orgs || []
  } catch (e) {
    console.error('加载组织失败:', e)
  }
}

async function selectOrg(org) {
  // 先停止之前的 SSE
  stopSSEProgress()

  selectedOrg.value = org

  // 加载活跃任务和子任务列表
  activeTaskLoading.value = true
  activeTask.value = null
  subtasks.value = []
  progressSummary.value = null

  try {
    const data = await getActiveTask(org.org_name)

    if (data.has_active_task) {
      activeTask.value = data.task
      subtasks.value = data.subtasks || []
      progressSummary.value = data.progress_summary || null

      // 如果任务正在运行，启动 SSE 推送
      if (data.task.status === 'running' || data.task.status === 'pending') {
        startSSEProgress(org.org_name)
      }
    }
  } catch (e) {
    console.error('获取活跃任务失败:', e)
  } finally {
    activeTaskLoading.value = false
  }
}

async function loadOrgHistory(orgName) {
  try {
    const data = await getScanHistory(orgName, 20)
    if (data.histories && data.histories.length > 0) {
      scanTasks.value = data.histories
      showScanHistory.value = true
    } else {
      alert('暂无历史记录')
    }
  } catch (e) {
    console.error('获取历史失败:', e)
    alert('获取历史记录失败: ' + e.message)
  }
}

// SSE 进度推送连接
let sseConnection = null
let sseCloseFn = null

function startSSEProgress(orgName) {
  // 先关闭之前的连接
  stopSSEProgress()

  console.log('[OrgConfig] Starting SSE:', orgName)

  sseCloseFn = connectProgressStream(orgName, {
    onConnected: () => {
      console.log('[OrgConfig] SSE connected')
    },
    onProgress: (data) => {
      // 检查是否还是当前选中的组织
      if (!selectedOrg.value || selectedOrg.value.org_name !== orgName) {
        stopSSEProgress()
        return
      }

      if (data.has_task) {
        activeTask.value = {
          ...data.task,
          phase: data.task.phase || 'init',
          phase_progress: data.task.phase_progress || {}
        }
        subtasks.value = data.subtasks || []
        progressSummary.value = data.progress_summary || null

        // 更新扫描进度状态（用于进度条展示）
        scanProgress.value = {
          ...scanProgress.value,
          run_id: data.task.run_id,
          status: data.task.status,
          phase: data.task.phase || 'init',
          phase_progress: data.task.phase_progress || {},
          total_repos: data.task.total_repos,
          scanned_repos: data.progress_summary.completed,
          findings_count: data.task.findings_count,
          error_message: data.task.error_message,
          subtasks: data.subtasks || [],
          current_repo: data.current_repo,
          percent: data.percent,
          progress_stats: data.progress_summary
        }
      } else {
        activeTask.value = null
        subtasks.value = []
        progressSummary.value = null
      }
    },
    onDone: (data) => {
      console.log('[OrgConfig] SSE done:', data.status)
      // 任务完成，停止 SSE
      stopSSEProgress()
    },
    onError: (error) => {
      console.error('[OrgConfig] SSE error:', error)
      stopSSEProgress()
    },
    onDisconnected: () => {
      console.log('[OrgConfig] SSE disconnected')
      sseCloseFn = null
    }
  })
}

function stopSSEProgress() {
  if (sseCloseFn) {
    sseCloseFn()
    sseCloseFn = null
    console.log('[OrgConfig] SSE stopped')
  }
}

function toggleSubtask(subtaskId) {
  const idx = expandedSubtasks.value.indexOf(subtaskId)
  if (idx === -1) {
    expandedSubtasks.value.push(subtaskId)
  } else {
    expandedSubtasks.value.splice(idx, 1)
  }
}

async function handleViewReport() {
  if (!selectedOrg.value || !activeTask.value) return

  showReportModal.value = true
  reportLoading.value = true
  reportData.value = null

  try {
    const data = await getScanReport(selectedOrg.value.org_name, activeTask.value.id)
    reportData.value = data
  } catch (e) {
    console.error('获取报告失败:', e)
    reportData.value = { has_report: false }
  } finally {
    reportLoading.value = false
  }
}

function closeReportModal() {
  showReportModal.value = false
  reportData.value = null
}

function closeOrgDetail() {
  stopSSEProgress()
  selectedOrg.value = null
  activeTask.value = null
  subtasks.value = []
  progressSummary.value = null
  expandedSubtasks.value = []
  showReportModal.value = false
}

async function syncReposFromGithub(orgName) {
  try {
    // 调用同步 API
    const response = await fetch(`/api/orgs/${orgName}/repos/sync`, { method: 'POST' })
    const result = await response.json()
    if (result.code === 0) {
      alert(`已同步 ${result.data.synced_count} 个仓库`)
      // 刷新仓库列表
      const reposResponse = await fetch(`/api/orgs/${orgName}/repos`)
      const reposData = await reposResponse.json()
      orgRepos.value = reposData.data?.repos || []
    }
  } catch (e) {
    console.error('同步仓库失败:', e)
    alert('同步失败: ' + e.message)
  }
}

async function checkGithubOrg() {
  if (!form.value.org_name) return

  orgValidation.value = { status: 'checking', message: '验证中...' }

  try {
    // 验证 GitHub 组织是否存在
    const response = await fetch(`https://api.github.com/orgs/${form.value.org_name}`)
    if (response.ok) {
      const data = await response.json()
      orgValidation.value = { status: 'valid', message: `✓ 组织存在，共 ${data.public_repos || 0} 个公开仓库` }
      if (!form.value.display_name) {
        form.value.display_name = data.name || form.value.org_name
      }
    } else {
      orgValidation.value = { status: 'invalid', message: '✗ 组织不存在，请检查名称' }
    }
  } catch (e) {
    orgValidation.value = { status: 'invalid', message: '验证失败: ' + e.message }
  }
}

function validateOrgName() {
  // 延迟验证（输入停止后验证）
  orgValidation.value = { status: '', message: '' }
}

function editOrg(org) {
  editingOrg.value = org
  form.value = {
    org_name: org.org_name,
    display_name: org.display_name || '',
    scan_frequency: org.scan_frequency || 'daily',
    scan_depth: 'L1_LIGHT',
    scan_enabled: org.scan_enabled,
    scan_dimensions: org.scan_dimensions || {
      cve: true,
      secret: true,
      license: true,
      community: false,
      trend: false,
      code_quality: false,
      supply_chain: false
    },
    llm_enabled: org.llm_enabled || false,
    generate_report: org.generate_report !== false,  // 默认 true
    secret_filter_config: org.secret_filter_config || {
      exclude_vendor: true,
      exclude_node_modules: true,
      exclude_test_files: false,
      example_whitelist: true,
      doc_file_lower_severity: true
    },
    dingtalk_webhook: org.alert_channels?.dingtalk_webhook || '',
    dingtalk_secret: org.alert_channels?.dingtalk_secret || '',
    feishu_webhook: org.alert_channels?.feishu_webhook || '',
    alert_rules: org.alert_rules || {
      CRITICAL: 'immediate',
      HIGH: 'immediate',
      MEDIUM: 'batch_daily',
      LOW: 'batch_weekly',
      INFO: 'disabled'
    },
    repo_filter: '',
    path_exclude: ''
  }
  orgValidation.value = { status: 'valid', message: '编辑现有组织' }
  showCreateModal.value = true
}

function closeModal() {
  showCreateModal.value = false
  editingOrg.value = null
  orgValidation.value = { status: '', message: '' }
  form.value = {
    org_name: '',
    display_name: '',
    scan_frequency: 'daily',
    scan_depth: 'L1_LIGHT',
    scan_enabled: true,
    scan_dimensions: {
      cve: true,
      secret: true,
      license: true,
      community: false,
      trend: false,
      supply_chain: false
    },
    llm_enabled: false,
    generate_report: true,
    secret_filter_config: {
      exclude_vendor: true,
      exclude_node_modules: true,
      exclude_test_files: false,
      example_whitelist: true,
      doc_file_lower_severity: true
    },
    dingtalk_webhook: '',
    dingtalk_secret: '',
    feishu_webhook: '',
    alert_rules: {
      CRITICAL: 'immediate',
      HIGH: 'immediate',
      MEDIUM: 'batch_daily',
      LOW: 'batch_weekly',
      INFO: 'disabled'
    },
    repo_filter: '',
    path_exclude: ''
  }
}

async function submitForm() {
  // 验证必填字段
  if (!form.value.org_name || form.value.org_name.trim() === '') {
    alert('请输入 GitHub 组织名称')
    return
  }

  // 验证组织是否存在（新建时）
  if (!editingOrg.value && orgValidation.value.status !== 'valid') {
    alert('请先验证 GitHub 组织是否存在')
    return
  }

  try {
    const orgData = {
      org_name: form.value.org_name,
      display_name: form.value.display_name,
      scan_frequency: form.value.scan_frequency,
      scan_enabled: form.value.scan_enabled,
      scan_dimensions: form.value.scan_dimensions,
      llm_enabled: form.value.llm_enabled,
      generate_report: form.value.generate_report,
      secret_filter_config: form.value.secret_filter_config,
      alert_channels: {},
      alert_rules: form.value.alert_rules
    }

    if (form.value.dingtalk_webhook) {
      orgData.alert_channels.dingtalk_webhook = form.value.dingtalk_webhook
    }
    if (form.value.dingtalk_secret) {
      orgData.alert_channels.dingtalk_secret = form.value.dingtalk_secret
    }
    if (form.value.feishu_webhook) {
      orgData.alert_channels.feishu_webhook = form.value.feishu_webhook
    }

    if (editingOrg.value) {
      await updateOrg(form.value.org_name, orgData)
    } else {
      await createOrg(orgData)
    }

    closeModal()
    await loadOrgs()
  } catch (e) {
    console.error('操作失败:', e)

    // 处理 409 Conflict（任务运行中不允许修改）
    if (e.message && e.message.includes('409')) {
      alert('⚠️ 无法修改：该组织有正在执行的扫描任务。\n\n请先暂停任务或等待任务完成后再修改配置。')
    } else {
      alert('操作失败: ' + e.message)
    }
  }
}

async function handleTriggerScan(orgName) {
  scanning.value = true
  scanningOrg.value = orgName

  try {
    // 1. 先获取活跃任务（检查是否已有任务）
    const activeData = await getActiveTask(orgName)

    if (activeData.has_active_task) {
      const task = activeData.task

      // 如果任务正在执行，提示用户
      if (task.status === 'running' || task.status === 'paused' || task.status === 'pending') {
        alert(`组织 ${orgName} 已有活跃任务（状态: ${getStatusLabel(task.status)}）\n点击该组织可查看子任务进度`)
        // 如果当前选中的就是这个组织，刷新任务数据
        if (selectedOrg.value && selectedOrg.value.org_name === orgName) {
          await selectOrg(selectedOrg.value)
        }
        return
      }
    }

    // 2. 触发新扫描
    const result = await triggerScanWithDimensions(orgName)

    if (result.code === 1) {
      // 服务端返回已有运行任务的提示
      alert(result.data.message || '已有任务在运行')
      return
    }

    // 3. 扫描任务已创建成功，不弹窗，只提示
    const totalRepos = result.data?.total_repos || 0
    alert(`✅ 扫描任务已创建\n组织: ${orgName}\n仓库数: ${totalRepos}\n\n点击该组织可查看子任务进度`)

    // 如果当前选中的就是这个组织，刷新任务数据
    if (selectedOrg.value && selectedOrg.value.org_name === orgName) {
      // 延迟刷新，等待后端创建子任务
      setTimeout(async () => {
        // 再次确认选中的组织
        if (selectedOrg.value && selectedOrg.value.org_name === orgName) {
          await selectOrg(selectedOrg.value)
        }
      }, 2000)
    }

  } catch (e) {
    console.error('触发扫描失败:', e)
    alert('触发失败: ' + e.message)
  } finally {
    scanning.value = false
    scanningOrg.value = ''
  }
}

async function pollForTaskId(orgName) {
  // 查找刚创建的任务
  try {
    const statusData = await getOrgScanStatus(orgName)
    if (statusData.has_running_task) {
      scanProgress.value.run_id = statusData.task.run_id
      startProgressPolling(statusData.task.run_id)
    } else {
      // 继续等待
      setTimeout(() => pollForTaskId(orgName), 3000)
    }
  } catch (e) {
    console.error('查找任务失败:', e)
    setTimeout(() => pollForTaskId(orgName), 3000)
  }
}

function startProgressPolling(runId) {
  // 清除之前的轮询
  if (progressPollTimer) {
    clearInterval(progressPollTimer)
  }
  // 每2秒轮询一次状态
  progressPollTimer = setInterval(async () => {
    try {
      // 获取主任务状态
      const status = await getScanStatus(runId)
      // 获取子任务进度
      const progress = await getScanProgress(runId)
      const subtasks = await getSubtaskProgress(runId)

      scanProgress.value = {
        run_id: status.run_id,
        org_name: status.org_name,
        scan_type: status.scan_type,
        status: status.status,
        total_repos: status.total_repos || 0,
        scanned_repos: status.scanned_repos || 0,
        findings_count: progress?.findings?.total || status.findings_count || 0,
        high_severity_count: progress?.findings?.high_severity || 0,
        error_message: status.error_message || '',
        started_at: status.started_at,
        completed_at: status.completed_at,
        percent: progress?.percent || 0,
        progress_stats: progress?.progress || {
          pending: 0, running: 0, completed: 0, failed: 0, paused: 0
        },
        subtasks: subtasks?.subtasks || [],
        current_repo: null
      }

      // 尝试获取当前正在扫描的仓库
      try {
        const runningRepo = await getCurrentRunningRepo(runId)
        scanProgress.value.current_repo = runningRepo?.current_repo || null
      } catch (e) {
        // 忽略此错误
      }

      // 如果完成或失败，停止轮询
      if (status.status === 'completed' || status.status === 'failed') {
        stopProgressPolling()
      }
    } catch (e) {
      console.error('获取进度失败:', e)
    }
  }, 2000)
}

function stopProgressPolling() {
  if (progressPollTimer) {
    clearInterval(progressPollTimer)
    progressPollTimer = null
  }
}

function closeScanProgress() {
  showScanProgress.value = false
  stopProgressPolling()
}

function formatTime(timeStr) {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN')
}

function getDimensionLabel(dim) {
  const labels = {
    cve: 'CVE漏洞',
    secret: '敏感信息',
    license: '许可证',
    community: '社区健康',
    trend: '趋势分析',
    supply_chain: '供应链风险'
  }
  return labels[dim] || dim
}

function getStatusLabel(status) {
  const labels = {
    pending: '启动中',
    running: '扫描中',
    completed: '已完成',
    failed: '失败',
    paused: '已暂停'
  }
  return labels[status] || status
}

function getAlertStatusLabel(alertStatus) {
  const labels = {
    pending: '等待推送',
    sending: '正在推送',
    sent: '已推送',
    skipped: '已跳过',
    failed: '推送失败'
  }
  return labels[alertStatus] || alertStatus
}

// 阶段标签映射
const phaseSteps = [
  { key: 'init', label: '初始化', icon: '🔄' },
  { key: 'scanning', label: '批量扫描', icon: '🔍' },
  { key: 'llm_analysis', label: 'LLM分析', icon: '🤖' },
  { key: 'generating_report', label: '生成报告', icon: '📊' },
  { key: 'alert_sending', label: '发送告警', icon: '🔔' },
  { key: 'done', label: '完成', icon: '✅' }
]

function getPhaseLabel(phase) {
  const labels = {
    init: '初始化',
    scanning: '批量扫描',
    llm_analysis: 'LLM深度分析',
    generating_report: '生成报告',
    alert_sending: '发送告警',
    done: '完成'
  }
  return labels[phase] || phase
}

function isPhaseDone(phaseKey, currentPhase) {
  const order = ['init', 'scanning', 'llm_analysis', 'generating_report', 'alert_sending', 'done']
  const phaseIdx = order.indexOf(phaseKey)
  const currentIdx = order.indexOf(currentPhase)
  return phaseIdx < currentIdx
}

function getDimProgressPercent(progress) {
  if (!progress || !progress.total) return 0
  return Math.round((progress.done / progress.total) * 100)
}

// 判断阶段是否待执行（未到达且未完成）
function isPhasePending(phaseKey, currentPhase) {
  const order = ['init', 'scanning', 'llm_analysis', 'generating_report', 'alert_sending', 'done']
  const phaseIdx = order.indexOf(phaseKey)
  const currentIdx = order.indexOf(currentPhase)
  return phaseIdx > currentIdx
}

// 判断箭头是否激活（正在从前一阶段过渡到下一阶段）
function isArrowActive(idx, currentPhase) {
  const order = ['init', 'scanning', 'llm_analysis', 'generating_report', 'alert_sending', 'done']
  const currentIdx = order.indexOf(currentPhase)
  // 箭头 idx 在 currentIdx 和 currentIdx+1 之间时激活
  return idx === currentIdx
}

// 判断箭头是否已完成（已经过了这个箭头）
function isArrowDone(idx, currentPhase) {
  const order = ['init', 'scanning', 'llm_analysis', 'generating_report', 'alert_sending', 'done']
  const currentIdx = order.indexOf(currentPhase)
  return idx < currentIdx
}

// 判断箭头是否需要流动动画（当前阶段正在向下一阶段过渡）
function isArrowFlowing(idx, currentPhase) {
  // 只有在当前阶段刚刚开始时，箭头才显示流动效果
  return isArrowActive(idx, currentPhase)
}

function getDuration(startAt, endAt) {
  const start = new Date(startAt)
  const end = new Date(endAt)
  const diffMs = end - start
  const minutes = Math.floor(diffMs / 60000)
  const seconds = Math.floor((diffMs % 60000) / 1000)
  if (minutes > 0) {
    return `${minutes}分${seconds}秒`
  }
  return `${seconds}秒`
}

function getElapsedTime(startAt) {
  const start = new Date(startAt)
  const now = new Date()
  const diffMs = now - start
  const minutes = Math.floor(diffMs / 60000)
  const seconds = Math.floor((diffMs % 60000) / 1000)
  if (minutes > 0) {
    return `${minutes}分${seconds}秒`
  }
  return `${seconds}秒`
}

// 计算剩余预估时间
const getRemainingTime = computed(() => {
  if (scanProgress.value.total_repos === 0 || scanProgress.value.estimated_time_minutes === 0) return 0
  const percentRemaining = 100 - progressPercent.value
  const remaining = Math.ceil(scanProgress.value.estimated_time_minutes * percentRemaining / 100)
  return remaining
})

function viewFindings() {
  // 跳转到发现列表页面
  closeScanProgress()
  // 可以通过 emit 或者路由跳转
  alert('请前往「发现列表」页面查看扫描结果')
}

async function handlePauseScan() {
  // 使用 activeTask 或 scanProgress 的 run_id
  const runId = activeTask.value?.run_id || scanProgress.value.run_id

  console.log('handlePauseScan called, runId:', runId, 'activeTask:', activeTask.value)

  if (!runId) {
    alert('无法获取任务ID，请刷新页面重试')
    return
  }

  try {
    const result = await pauseScan(runId)
    if (result) {
      // 更新两个状态
      if (activeTask.value) {
        activeTask.value.status = 'paused'
      }
      if (scanProgress.value) {
        scanProgress.value.status = 'paused'
        scanProgress.value.scanned_repos = result.scanned_repos || scanProgress.value.scanned_repos
        scanProgress.value.total_repos = result.total_repos || scanProgress.value.total_repos
      }
      alert('扫描任务已暂停')
    }
  } catch (e) {
    console.error('暂停失败:', e)
    alert('暂停失败: ' + e.message)
  }
}

async function handleResumeScan() {
  // 使用 activeTask 或 scanProgress 的 run_id
  const runId = activeTask.value?.run_id || scanProgress.value.run_id
  if (!runId) {
    alert('无法获取任务ID')
    return
  }

  try {
    const result = await resumeScan(runId)
    if (result) {
      // 更新两个状态
      if (activeTask.value) {
        activeTask.value.status = 'running'
      }
      if (scanProgress.value) {
        scanProgress.value.status = 'running'
      }
      alert('扫描任务已恢复')
      // 重新开始 SSE 推送（SSE 已经提供进度更新，不需要额外轮询）
      if (selectedOrg.value) {
        startSSEProgress(selectedOrg.value.org_name)
      }
    }
  } catch (e) {
    console.error('恢复失败:', e)
    alert('恢复失败: ' + e.message)
  }
}

async function handleForceStop() {
  const orgName = selectedOrg.value?.org_name
  if (!orgName) {
    alert('无法获取组织名称')
    return
  }

  // 确认操作
  if (!confirm(`确认强制终止组织 ${orgName} 的任务？\n\n此操作会将任务状态设为失败，并清理所有相关数据。\n适用于任务卡住或异常状态的情况。`)) {
    return
  }

  try {
    const result = await forceStopTask(orgName)
    if (result.force_stopped) {
      alert(`✅ 任务已强制终止\n${result.message}`)

      // 清空当前显示的任务数据
      activeTask.value = null
      subtasks.value = []
      progressSummary.value = null

      // 停止 SSE
      stopSSEProgress()

      // 刷新组织列表
      await loadOrgs()
    } else {
      alert(result.message)
    }
  } catch (e) {
    console.error('强制终止失败:', e)
    alert('强制终止失败: ' + e.message)
  }
}

async function handleCancelScan() {
  const runId = activeTask.value?.run_id || scanProgress.value?.run_id
  if (!runId) {
    alert('无法获取任务ID')
    return
  }

  if (!confirm('确定要取消此扫描任务吗？取消后无法恢复，需要重新触发新任务。')) {
    return
  }

  try {
    const result = await cancelScan(runId)
    if (result) {
      // 更新状态
      if (activeTask.value) {
        activeTask.value.status = 'cancelled'
      }
      if (scanProgress.value) {
        scanProgress.value.status = 'cancelled'
      }
      alert('扫描任务已取消')

      // 停止 SSE
      stopSSEProgress()
    }
  } catch (e) {
    console.error('取消失败:', e)
    alert('取消失败: ' + e.message)
  }
}

async function handleForceResetScan() {
  const runId = activeTask.value?.run_id || scanProgress.value?.run_id
  if (!runId) {
    alert('无法获取任务ID')
    return
  }

  if (!confirm(`此操作将强制将任务 ${runId} 标记为失败状态。\n\n适用于服务异常终止后任务状态仍为 running 的情况。\n\n确定要强制重置吗？`)) {
    return
  }

  try {
    const result = await forceResetScan(runId)
    if (result) {
      // 更新状态
      if (activeTask.value) {
        activeTask.value.status = 'failed'
        activeTask.value.error_message = '任务被强制重置（服务异常终止）'
      }
      if (scanProgress.value) {
        scanProgress.value.status = 'failed'
      }
      alert('任务已强制重置为失败状态，可以重新触发新任务')

      // 停止 SSE
      stopSSEProgress()
    }
  } catch (e) {
    console.error('强制重置失败:', e)
    alert('强制重置失败: ' + e.message)
  }
}

function viewReport() {
  // 打开报告页面或弹窗
  alert('报告正在生成中，请稍后在「报告」页面查看')
  // TODO: 导航到报告页面或打开报告详情弹窗
}

async function handleDeleteOrg(orgName) {
  if (!confirm(`确定删除组织 ${orgName}?\n这将删除所有关联的仓库监控配置。`)) return

  try {
    await deleteOrg(orgName)
    await loadOrgs()
    if (selectedOrg.value?.org_name === orgName) {
      selectedOrg.value = null
    }
  } catch (e) {
    console.error('删除失败:', e)

    // 处理 409 Conflict（任务运行中不允许删除）
    if (e.message && e.message.includes('409')) {
      alert('⚠️ 无法删除：该组织有正在执行的扫描任务。\n\n请先暂停任务或等待任务完成后再删除组织。')
    } else {
      alert('删除失败: ' + e.message)
    }
  }
}

function applyTemplate(templateName) {
  const templates = {
    basic: { dimensions: { cve: true, secret: true, license: true, community: false, trend: false, supply_chain: false }, llm_enabled: false },
    standard: { dimensions: { cve: true, secret: true, license: true, community: true, trend: false, supply_chain: false }, llm_enabled: false },
    deep: { dimensions: { cve: true, secret: true, license: true, community: true, trend: true, supply_chain: true }, llm_enabled: true },
    compliance_only: { dimensions: { cve: false, secret: false, license: true, community: false, trend: false, supply_chain: false }, llm_enabled: false },
    security_focus: { dimensions: { cve: true, secret: true, license: false, community: false, trend: false, supply_chain: true }, llm_enabled: true }
  }

  const template = templates[templateName]
  if (template) {
    form.value.scan_dimensions = template.dimensions
    form.value.llm_enabled = template.llm_enabled
  }
}

async function updateRepoPriority(repo) {
  // TODO: 调用更新 API
  console.log('更新优先级:', repo.repo_full_name, repo.priority_tier)
}

async function updateRepoActive(repo) {
  // TODO: 调用更新 API
  console.log('更新监控状态:', repo.repo_full_name, repo.is_active)
}

onMounted(() => {
  loadOrgs()
})

onUnmounted(() => {
  stopProgressPolling()
  stopSSEProgress()
})
</script>

<style scoped>
.org-config {
  padding: 24px;
  background: #f8fafc;
  min-height: 100vh;
}

.org-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.org-header h1 {
  font-size: 24px;
  color: #1e293b;
}

.create-btn {
  padding: 12px 24px;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
}

/* 组织列表 */
.org-list {
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.org-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #f1f5f9;
}

.org-main {
  flex: 1;
  cursor: pointer;
}

.org-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.org-name {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}

.org-display-name {
  font-size: 14px;
  color: #64748b;
}

.org-status-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.org-status-badge.enabled {
  background: #dcfce7;
  color: #16a34a;
}

.org-status-badge:not(.enabled) {
  background: #f1f5f9;
  color: #94a3b8;
}

.org-meta {
  display: flex;
  gap: 16px;
  margin-top: 8px;
}

.meta-item {
  font-size: 12px;
  color: #94a3b8;
}

.org-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.action-btn.scan {
  background: #0ea5e9;
  color: white;
}

.action-btn.scan:disabled {
  opacity: 0.5;
}

.action-btn.edit {
  background: #f1f5f9;
  color: #1e293b;
}

.action-btn.delete {
  background: #fef2f2;
  color: #dc2626;
}

/* 组织详情面板 */
.org-detail-panel {
  margin-top: 24px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  padding: 20px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.panel-header h2 {
  font-size: 18px;
  color: #1e293b;
}

.sync-btn {
  padding: 10px 16px;
  background: #f1f5f9;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.close-panel {
  background: none;
  border: none;
  font-size: 24px;
  color: #94a3b8;
  cursor: pointer;
}

/* 仓库列表 */
.repo-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.repo-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f8fafc;
  border-radius: 8px;
}

.repo-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.repo-name {
  font-size: 14px;
  color: #1e293b;
}

.repo-stars {
  font-size: 12px;
  color: #94a3b8;
}

.repo-config {
  display: flex;
  align-items: center;
  gap: 16px;
}

.priority-select {
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 12px;
}

.toggle-active {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Modal */
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
  width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-large {
  width: 700px;
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

.section {
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f1f5f9;
}

.section:last-child {
  border-bottom: none;
}

.section h3 {
  font-size: 16px;
  color: #1e293b;
  margin-bottom: 16px;
}

.section-hint {
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 12px;
  margin-top: -12px;
}

.secret-config-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

.config-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.config-item input[type="checkbox"] {
  width: 18px;
  height: 18px;
  margin-top: 2px;
  cursor: pointer;
}

.config-item label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
}

.config-title {
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
}

.config-desc {
  font-size: 12px;
  color: #64748b;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 14px;
  color: #1e293b;
  margin-bottom: 8px;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 14px;
}

.form-group textarea {
  min-height: 60px;
  resize: vertical;
}

.form-group input:focus,
.form-group select:focus {
  border-color: #0ea5e9;
  outline: none;
}

.form-group input:disabled {
  background: #f8fafc;
}

.field-hint {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}

.validation-status {
  font-size: 12px;
  margin-left: 8px;
}

.validation-status.valid {
  color: #16a34a;
}

.validation-status.invalid {
  color: #dc2626;
}

.validate-btn {
  padding: 6px 12px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  margin-top: 8px;
}

.toggle-group {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toggle-switch {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toggle-switch input {
  width: 20px;
  height: 20px;
}

.toggle-label {
  font-size: 14px;
  color: #64748b;
}

/* 预警规则 */
.alert-rules {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #f8fafc;
  padding: 12px;
  border-radius: 8px;
}

.rule-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.severity {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.severity.critical { background: #fef2f2; color: #dc2626; }
.severity.high { background: #fff7ed; color: #ea580c; }
.severity.medium { background: #fefce8; color: #eab308; }
.severity.low { background: #f0fdf4; color: #22c55e; }

.rule {
  font-size: 12px;
  color: #64748b;
}

/* 可配置推送规则 */
.alert-rules-config {
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #f8fafc;
  padding: 12px;
  border-radius: 8px;
}

.rule-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.severity-badge {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
}

.severity-badge.critical { background: #fef2f2; color: #dc2626; }
.severity-badge.high { background: #fff7ed; color: #ea580c; }
.severity-badge.medium { background: #fefce8; color: #eab308; }
.severity-badge.low { background: #f0fdf4; color: #22c55e; }
.severity-badge.info { background: #eff6ff; color: #3b82f6; }

.rule-select {
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 13px;
  background: white;
  cursor: pointer;
  min-width: 120px;
}

.rule-select:focus {
  outline: none;
  border-color: #3b82f6;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid #f1f5f9;
}

.cancel-btn {
  padding: 10px 20px;
  background: #f1f5f9;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
}

.submit-btn {
  padding: 10px 20px;
  background: #0ea5e9;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: #94a3b8;
}

.empty-state .hint {
  font-size: 12px;
  margin-top: 8px;
}

/* 扫描历史 */
.scan-history-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.scan-task-item {
  padding: 12px 16px;
  background: #f8fafc;
  border-radius: 8px;
}

.task-main {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}

.task-id {
  font-size: 12px;
  color: #94a3b8;
}

.task-type {
  font-size: 12px;
  color: #0ea5e9;
}

.task-org {
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
}

.task-status {
  display: flex;
  gap: 12px;
  align-items: center;
}

.status-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.status-badge.running { background: #dbeafe; color: #2563eb; }
.status-badge.completed { background: #dcfce7; color: #16a34a; }
.status-badge.failed { background: #fef2f2; color: #dc2626; }
.status-badge.pending { background: #f1f5f9; color: #94a3b8; }

.task-time {
  font-size: 12px;
  color: #94a3b8;
}

.task-progress {
  font-size: 12px;
  color: #64748b;
}

/* 扫描维度配置 */
.template-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.template-btn {
  padding: 8px 14px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: #1e293b;
  white-space: nowrap;
}

.template-btn:hover {
  background: #dbeafe;
  border-color: #0ea5e9;
}

.dimension-section {
  margin-bottom: 12px;
}

.dimension-header {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 8px;
  font-weight: 500;
}

.dimension-header.llm-header {
  color: #ea580c;
}

.dimension-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
  background: #f8fafc;
  padding: 12px;
  border-radius: 8px;
}

.dimension-grid.llm-grid {
  background: #fff7ed;
}

.dimension-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
}

.dimension-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.dimension-item label {
  font-size: 14px;
  color: #1e293b;
  cursor: pointer;
  flex-shrink: 0;
}

.dimension-item .hint {
  font-size: 11px;
  color: #94a3b8;
  margin-left: 4px;
}

.llm-section-block {
  margin-top: 16px;
  padding: 12px;
  background: #fff7ed;
  border-radius: 8px;
  border: 1px solid #fed7aa;
}

.llm-toggle {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #fed7aa;
}

.llm-toggle .toggle-switch {
  display: flex;
  align-items: center;
  gap: 8px;
}

.llm-toggle .toggle-label {
  font-size: 13px;
  color: #ea580c;
}

/* 报告配置样式 */
.report-section {
  background: #f0fdf4;
  border-radius: 8px;
  border: 1px solid #bbf7d0;
}

.report-section h3 {
  color: #15803d;
}

.report-section .toggle-label {
  color: #166534;
}

.report-section .toggle-status {
  font-size: 12px;
  color: #22c55e;
}

/* 扫描进度弹窗 */
.scan-progress-modal {
  width: 500px;
}

.progress-info {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
  background: #f8fafc;
  padding: 16px;
  border-radius: 8px;
}

.progress-info .label {
  font-size: 12px;
  color: #64748b;
}

.progress-info .value {
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
}

.progress-info .value.estimate {
  color: #0ea5e9;
}

.progress-dimensions {
  margin-bottom: 16px;
  padding: 12px;
  background: #f1f5f9;
  border-radius: 8px;
}

.progress-dimensions .label {
  font-size: 12px;
  color: #64748b;
  margin-right: 8px;
}

.dimension-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.dimension-tag {
  padding: 4px 10px;
  background: #dbeafe;
  color: #2563eb;
  border-radius: 4px;
  font-size: 12px;
}

.progress-bar-container {
  margin-bottom: 20px;
}

.progress-bar {
  height: 24px;
  background: #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #0ea5e9, #22c55e);
  border-radius: 12px;
  transition: width 0.3s ease;
}

.progress-text {
  text-align: center;
  margin-top: 8px;
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
}

.progress-status {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
  margin-bottom: 16px;
}

/* 阶段进度样式 */
.phase-progress {
  margin: 16px 0;
  padding: 16px;
  background: #f8fafc;
  border-radius: 8px;
}

/* 面板中的阶段进度样式 */
.phase-progress-panel {
  margin-bottom: 12px;
  padding: 12px;
  background: #f0f9ff;
  border-radius: 8px;
  border: 1px solid #bae6fd;
}

.phase-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.phase-name {
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 4px;
  background: #e2e8f0;
}

.phase-name.init { background: #fef3c7; color: #92400e; }
.phase-name.scanning { background: #dbeafe; color: #1e40af; }
.phase-name.llm_analysis { background: #fce7f3; color: #9f1239; }
.phase-name.generating_report { background: #d1fae5; color: #065f46; }
.phase-name.done { background: #dcfce7; color: #16a34a; }
.phase-name.alert_sending { background: #fef3c7; color: #b45309; }

.phase-status-badge {
  margin-left: 8px;
  padding: 2px 8px;
  background: #22c55e;
  color: #fff;
  font-size: 12px;
  border-radius: 4px;
  font-weight: 500;
}

.phase-steps {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
  gap: 0;
}

.phase-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 12px;
  border-radius: 12px;
  background: #fff;
  border: 2px solid #e2e8f0;
  transition: all 0.4s ease;
  min-width: 70px;
  position: relative;
}

.phase-step.pending {
  opacity: 0.6;
  background: #f8fafc;
}

.phase-step.active {
  border-color: #3b82f6;
  background: #eff6ff;
  animation: pulse-step 1.5s ease-in-out infinite;
}

.phase-step.done {
  border-color: #22c55e;
  background: #f0fdf4;
}

/* 当前步骤的脉冲动画 */
@keyframes pulse-step {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
  50% { transform: scale(1.02); box-shadow: 0 0 0 8px rgba(59, 130, 246, 0.2); }
}

/* 当前步骤的圆环动画 */
.step-ring {
  position: absolute;
  top: -4px;
  left: -4px;
  right: -4px;
  bottom: -4px;
  border: 2px solid #3b82f6;
  border-radius: 14px;
  animation: ring-pulse 2s ease-in-out infinite;
}

@keyframes ring-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.1); }
}

/* 箭头连接器样式 */
.phase-arrow {
  display: flex;
  align-items: center;
  position: relative;
  width: 40px;
  height: 30px;
  margin: 0 -2px;
}

.arrow-line {
  width: 100%;
  height: 3px;
  background: #e2e8f0;
  border-radius: 2px;
  transition: all 0.4s ease;
}

.arrow-head {
  position: absolute;
  right: 0;
  font-size: 14px;
  color: #e2e8f0;
  transition: all 0.4s ease;
}

/* 已完成的箭头 */
.phase-arrow.done .arrow-line {
  background: #22c55e;
}

.phase-arrow.done .arrow-head {
  color: #22c55e;
}

/* 正在过渡的箭头 - 激活状态 */
.phase-arrow.active .arrow-line {
  background: linear-gradient(90deg, #22c55e 0%, #3b82f6 100%);
  animation: arrow-progress 1s ease-in-out infinite;
}

.phase-arrow.active .arrow-head {
  color: #3b82f6;
  animation: arrow-bounce 0.6s ease-in-out infinite;
}

/* 箭头流动动画 */
.arrow-flow {
  position: absolute;
  top: 0;
  left: 0;
  width: 20px;
  height: 3px;
  background: linear-gradient(90deg, transparent, #3b82f6, transparent);
  animation: flow-move 1.5s linear infinite;
}

@keyframes arrow-progress {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

@keyframes arrow-bounce {
  0%, 100% { transform: translateX(0); }
  50% { transform: translateX(3px); }
}

@keyframes flow-move {
  0% { left: 0; opacity: 0; }
  20% { opacity: 1; }
  80% { opacity: 1; }
  100% { left: calc(100% - 20px); opacity: 0; }
}

.step-icon {
  font-size: 20px;
  margin-bottom: 4px;
  transition: all 0.3s ease;
}

/* 当前步骤图标动画 */
.phase-step.active .step-icon {
  animation: icon-bounce 0.8s ease-in-out infinite;
}

@keyframes icon-bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}

.step-label {
  font-size: 12px;
  color: #64748b;
}

.phase-step.active .step-label {
  color: #1e40af;
  font-weight: 600;
}

.phase-step.done .step-label {
  color: #16a34a;
}

.phase-step.pending .step-label {
  color: #94a3b8;
}

.dimension-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dim-progress-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dim-name {
  font-size: 12px;
  color: #64748b;
  width: 80px;
}

.dim-bar {
  flex: 1;
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}

.dim-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #60a5fa);
  transition: width 0.3s;
}

.dim-count {
  font-size: 12px;
  color: #64748b;
  width: 60px;
  text-align: right;
}

.status-message {
  font-size: 14px;
  color: #64748b;
}

.status-message.success {
  color: #16a34a;
}

.status-message.error {
  color: #dc2626;
}

.progress-findings {
  text-align: center;
  padding: 12px;
  background: #fef3c7;
  border-radius: 8px;
  margin-bottom: 16px;
}

.findings-count {
  font-size: 16px;
  color: #d97706;
  font-weight: 600;
}

.high-count {
  font-size: 14px;
  color: #dc2626;
}

.progress-time {
  display: flex;
  gap: 24px;
  justify-content: center;
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 16px;
}

.progress-time .duration {
  color: #16a34a;
}

.progress-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.view-findings-btn {
  padding: 10px 24px;
  background: #0ea5e9;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
}

.progress-actions .close-btn {
  padding: 10px 24px;
  background: #f1f5f9;
  color: #1e293b;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
}

.view-report-btn {
  padding: 10px 24px;
  background: #22c55e;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
}

/* 进度控制按钮 */
.progress-controls {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-bottom: 16px;
}

.pause-btn {
  padding: 10px 24px;
  background: #fbbf24;
  color: #1e293b;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.pause-btn:hover {
  background: #f59e0b;
}

.resume-btn {
  padding: 10px 24px;
  background: #22c55e;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.resume-btn:hover {
  background: #16a34a;
}

.cancel-btn {
  padding: 10px 24px;
  background: #fee2e2;
  color: #dc2626;
  border: 1px solid #fecaca;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.cancel-btn:hover {
  background: #fecaca;
}

/* 仓库进度列表 */
.progress-repo-list {
  margin-top: 16px;
  background: #f8fafc;
  border-radius: 8px;
  padding: 12px;
}

.repo-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
}

.repo-stats {
  font-size: 12px;
  color: #64748b;
}

.repo-list-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.repo-list-items .repo-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: white;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.repo-list-items .repo-name {
  font-size: 13px;
  color: #1e293b;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.repo-list-items .repo-status {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.repo-list-items .repo-status.pending { background: #f1f5f9; color: #94a3b8; }
.repo-list-items .repo-status.running { background: #dbeafe; color: #2563eb; }
.repo-list-items .repo-status.completed { background: #dcfce7; color: #16a34a; }
.repo-list-items .repo-status.failed { background: #fef2f2; color: #dc2626; }
.repo-list-items .repo-status.paused { background: #fef3c7; color: #d97706; }

.repo-list-items .repo-findings {
  font-size: 12px;
  color: #dc2626;
  margin-left: 8px;
}

/* 暂停状态徽章 */
.status-badge.paused {
  background: #fef3c7;
  color: #d97706;
}

.status-message.warning {
  color: #d97706;
}

/* 组织详情面板 - 任务卡片 */
.panel-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.scan-btn {
  padding: 10px 20px;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
}

.scan-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state {
  padding: 40px;
  text-align: center;
  color: #64748b;
}

.hint {
  font-size: 13px;
  color: #94a3b8;
  margin-top: 8px;
}

/* 任务卡片 */
.task-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
  border: 1px solid #e2e8f0;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.task-run-id {
  font-size: 13px;
  color: #64748b;
}

.task-status-badge {
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
}

.task-status-badge.running { background: #dbeafe; color: #2563eb; }
.task-status-badge.paused { background: #fef3c7; color: #d97706; }
.task-status-badge.completed { background: #dcfce7; color: #16a34a; }
.task-status-badge.failed { background: #fef2f2; color: #dc2626; }
.task-status-badge.pending { background: #f1f5f9; color: #64748b; }

.task-trigger-badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  background: #f1f5f9;
  color: #64748b;
}

.task-trigger-badge.manual { background: #e0f2fe; color: #0369a1; }
.task-trigger-badge.scheduler { background: #fef3c7; color: #b45309; }

.task-type-badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  background: #f8fafc;
  color: #475569;
  border: 1px solid #e2e8f0;
}

/* 运行中状态展示 */
.task-running-info {
  padding: 12px 0;
  margin-bottom: 12px;
}

.running-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.pulse-icon {
  color: #2563eb;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.current-repo {
  font-size: 12px;
  color: #64748b;
  margin-left: 8px;
}

/* 结果展示 */
.task-result-info {
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
  margin-bottom: 12px;
}

.task-result-info.failed {
  background: #fef2f2;
}

.task-result-info.paused {
  background: #fef3c7;
}

.result-summary {
  display: flex;
  align-items: center;
  gap: 8px;
}

.result-icon {
  font-size: 18px;
}

.result-icon.success { color: #16a34a; }
.result-icon.failed { color: #dc2626; }
.result-icon.paused { color: #d97706; }

.result-detail {
  font-size: 13px;
  color: #64748b;
  margin-left: 8px;
}

.high-alert {
  color: #dc2626;
  font-weight: 600;
}

/* 告警推送状态样式 */
.alert-status-info {
  margin-top: 12px;
  padding: 10px;
  background: #f1f5f9;
  border-radius: 6px;
}

.alert-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.alert-label {
  font-size: 13px;
  color: #64748b;
}

.alert-status-badge {
  padding: 4px 10px;
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
  margin-top: 6px;
  font-size: 12px;
}

.alert-details.warning {
  color: #dc2626;
}

.alert-details.info {
  color: #94a3b8;
}

.alert-detail, .alert-error, .alert-info {
  font-size: 12px;
}

.alert-error {
  color: #dc2626;
}

.error-message {
  font-size: 13px;
  color: #dc2626;
  margin-left: 8px;
}

.task-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  color: #64748b;
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: #1e293b;
}

.stat-value.findings {
  color: #f59e0b;
}

.stat-value.high {
  color: #dc2626;
}

/* 进度条（迷你版） */
.progress-section {
  margin-top: 16px;
}

.progress-bar-mini {
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill-mini {
  height: 100%;
  background: linear-gradient(90deg, #0ea5e9, #22c55e);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-text-mini {
  text-align: right;
  font-size: 12px;
  color: #64748b;
  margin-top: 4px;
}

/* 任务控制按钮 */
.task-controls {
  display: flex;
  gap: 8px;
  margin-top: 16px;
  justify-content: flex-end;
}

.pause-btn-mini, .resume-btn-mini {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.pause-btn-mini {
  background: #fbbf24;
  color: #1e293b;
}

.resume-btn-mini {
  background: #22c55e;
  color: white;
}

.force-stop-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  background: #dc2626;
  color: white;
}

.force-stop-btn:hover {
  background: #b91c1c;
}

.cancel-btn-mini {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  background: #fee2e2;
  color: #dc2626;
}

.cancel-btn-mini:hover {
  background: #fecaca;
}

.force-reset-btn {
  padding: 8px 16px;
  border: 1px dashed #94a3b8;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  background: #f1f5f9;
  color: #64748b;
}

.force-reset-btn:hover {
  background: #e2e8f0;
  color: #475569;
}

/* 子任务列表 */
.subtask-list {
  background: white;
  border-radius: 12px;
  padding: 16px;
  border: 1px solid #e2e8f0;
}

.subtask-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
}

.subtask-summary {
  font-size: 12px;
  color: #64748b;
}

.subtask-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 400px;
  overflow-y: auto;
}

.subtask-item {
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.subtask-item.expanded {
  background: #ffffff;
  border-color: #cbd5e1;
}

.subtask-main {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
}

.expand-icon {
  font-size: 10px;
  color: #64748b;
  margin-right: 8px;
}

.subtask-repo {
  font-size: 13px;
  color: #1e293b;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.subtask-status {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
}

.subtask-status.pending { background: #f1f5f9; color: #94a3b8; }
.subtask-status.running { background: #dbeafe; color: #2563eb; }
.subtask-status.completed { background: #dcfce7; color: #16a34a; }
.subtask-status.failed { background: #fef2f2; color: #dc2626; }
.subtask-status.paused { background: #fef3c7; color: #d97706; }

.subtask-findings {
  font-size: 12px;
  color: #dc2626;
  margin-left: 8px;
}

.subtask-findings-detail {
  padding: 8px 12px 12px 28px;
  background: #fefefe;
  border-top: 1px solid #e2e8f0;
}

.subtask-findings-detail.empty {
  color: #94a3b8;
  font-size: 12px;
}

.finding-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
}

.finding-severity {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.finding-severity.critical { background: #fef2f2; color: #dc2626; }
.finding-severity.high { background: #fee2e2; color: #b91c1c; }
.finding-severity.medium { background: #fef3c7; color: #d97706; }
.finding-severity.low { background: #dbeafe; color: #2563eb; }
.finding-severity.info { background: #f1f5f9; color: #64748b; }

.finding-type {
  padding: 2px 6px;
  background: #f1f5f9;
  border-radius: 4px;
  font-size: 11px;
  color: #475569;
}

.finding-title {
  color: #1e293b;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.finding-more {
  padding: 6px 0;
  font-size: 12px;
  color: #94a3b8;
}

/* 历史记录按钮 */
.history-section {
  margin-top: 16px;
  text-align: center;
}

.history-btn {
  padding: 10px 20px;
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: pointer;
}

.history-btn:hover {
  background: #e2e8f0;
  color: #1e293b;
}

.report-btn {
  padding: 10px 20px;
  background: #3b82f6;
  color: white;
  border: 1px solid #2563eb;
  border-radius: 8px;
  cursor: pointer;
  margin-left: 12px;
}

.report-btn:hover {
  background: #2563eb;
}

/* 报告弹窗样式 */
.report-body {
  max-height: 70vh;
  overflow-y: auto;
}

.report-loading {
  text-align: center;
  padding: 40px;
  color: #64748b;
}

.report-empty {
  text-align: center;
  padding: 40px;
  color: #64748b;
}

.report-empty .hint {
  font-size: 12px;
  margin-top: 8px;
}

.report-content {
  padding: 20px;
}

.report-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e2e8f0;
}

.report-title {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
}

.report-time {
  font-size: 12px;
  color: #94a3b8;
}

.report-summary-text {
  padding: 12px 16px;
  background: #fef3c7;
  border-radius: 8px;
  margin-bottom: 16px;
  color: #92400e;
}

.report-recommendations {
  margin-bottom: 16px;
  padding: 16px;
  background: #f1f5f9;
  border-radius: 8px;
}

.report-recommendations h4 {
  margin-bottom: 12px;
  color: #1e293b;
}

.report-recommendations ul {
  list-style: none;
  padding: 0;
}

.report-recommendations li {
  padding: 8px 0;
  border-bottom: 1px solid #e2e8f0;
}

.report-recommendations li:last-child {
  border-bottom: none;
}

.report-markdown {
  border-top: 1px solid #e2e8f0;
  padding-top: 16px;
}
</style>