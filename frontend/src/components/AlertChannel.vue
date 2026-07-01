<template>
  <div class="channel-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <span class="title-icon">📢</span>
          告警渠道管理
        </h1>
        <p class="page-desc">配置钉钉、飞书、Slack、Discord、Email等告警推送渠道，绑定到定时任务实现自动通知</p>
      </div>
      <button class="create-btn" @click="openCreateModal">
        <span class="btn-icon">+</span>
        新建渠道
      </button>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-section">
      <div class="filter-tabs">
        <button
          class="filter-tab"
          :class="{ active: filterType === '' }"
          @click="filterType = ''; loadChannels()"
        >
          全部
        </button>
        <button
          class="filter-tab dingtalk"
          :class="{ active: filterType === 'dingtalk' }"
          @click="filterType = 'dingtalk'; loadChannels()"
        >
          钉钉
        </button>
        <button
          class="filter-tab feishu"
          :class="{ active: filterType === 'feishu' }"
          @click="filterType = 'feishu'; loadChannels()"
        >
          飞书
        </button>
        <button
          class="filter-tab slack"
          :class="{ active: filterType === 'slack' }"
          @click="filterType = 'slack'; loadChannels()"
        >
          Slack
        </button>
        <button
          class="filter-tab discord"
          :class="{ active: filterType === 'discord' }"
          @click="filterType = 'discord'; loadChannels()"
        >
          Discord
        </button>
        <button
          class="filter-tab email"
          :class="{ active: filterType === 'email' }"
          @click="filterType = 'email'; loadChannels()"
        >
          Email
        </button>
        <button
          class="filter-tab webhook"
          :class="{ active: filterType === 'webhook' }"
          @click="filterType = 'webhook'; loadChannels()"
        >
          Webhook
        </button>
      </div>
      <div class="stats-info">
        共 <span class="count">{{ channels.length }}</span> 个渠道
      </div>
    </div>

    <!-- 渠道列表 -->
    <div class="channel-grid" v-if="channels.length">
      <div class="channel-card" v-for="channel in channels" :key="channel.id" :class="channel.channel_type">
        <!-- 渠道类型标识 -->
        <div class="card-type-badge" :class="channel.channel_type">
          <span class="type-icon">{{ getTypeIcon(channel.channel_type) }}</span>
          <span class="type-name">{{ getTypeLabel(channel.channel_type) }}</span>
        </div>

        <!-- 渠道内容 -->
        <div class="card-content">
          <div class="card-header">
            <h3 class="channel-name">{{ channel.name }}</h3>
            <div class="status-switch" :class="{ on: channel.enabled }" @click="toggleChannel(channel)">
              <span class="switch-slider"></span>
            </div>
          </div>

          <p class="channel-desc" v-if="channel.description">{{ channel.description }}</p>

          <div class="channel-webhook">
            <span class="webhook-label">Webhook:</span>
            <span class="webhook-value">{{ maskWebhook(channel.webhook_url) }}</span>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="card-actions">
          <button class="action-btn test" @click="handleTestChannel(channel)" :disabled="testingChannel === channel.id">
            <span class="action-icon">📨</span>
            <span class="action-text">{{ testingChannel === channel.id ? '发送中...' : '测试' }}</span>
          </button>
          <button class="action-btn edit" @click="openEditModal(channel)">
            <span class="action-icon">✏️</span>
            <span class="action-text">编辑</span>
          </button>
          <button class="action-btn delete" @click="confirmDelete(channel)">
            <span class="action-icon">🗑️</span>
            <span class="action-text">删除</span>
          </button>
        </div>

        <!-- 状态角标 -->
        <div class="status-corner" :class="channel.enabled ? 'enabled' : 'disabled'">
          {{ channel.enabled ? '启用' : '禁用' }}
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div class="empty-state" v-else>
      <div class="empty-icon">📭</div>
      <h3 class="empty-title">暂无告警渠道</h3>
      <p class="empty-desc">点击上方"新建渠道"按钮，添加钉钉、飞书等告警推送配置</p>
      <div class="empty-tips">
        <div class="tip-item">
          <span class="tip-icon">💡</span>
          <span>钉钉机器人：需要在钉钉群设置中创建自定义机器人</span>
        </div>
        <div class="tip-item">
          <span class="tip-icon">💡</span>
          <span>飞书机器人：需要在飞书群设置中创建自定义机器人</span>
        </div>
      </div>
    </div>

    <!-- 创建/编辑弹窗 -->
    <div class="modal-overlay" v-if="showModal" @click.self="closeModal">
      <div class="modal-container">
        <div class="modal-header">
          <h2 class="modal-title">{{ isEditing ? '编辑渠道' : '新建渠道' }}</h2>
          <button class="modal-close" @click="closeModal">×</button>
        </div>

        <div class="modal-body">
          <!-- 渠道类型选择 -->
          <div class="form-section">
            <label class="section-label">渠道类型</label>
            <div class="type-selector">
              <div
                class="type-option"
                :class="{ selected: formData.channel_type === 'dingtalk' }"
                @click="formData.channel_type = 'dingtalk'"
              >
                <span class="option-icon">🔵</span>
                <span class="option-name">钉钉</span>
              </div>
              <div
                class="type-option"
                :class="{ selected: formData.channel_type === 'feishu' }"
                @click="formData.channel_type = 'feishu'"
              >
                <span class="option-icon">🟣</span>
                <span class="option-name">飞书</span>
              </div>
              <div
                class="type-option"
                :class="{ selected: formData.channel_type === 'slack' }"
                @click="formData.channel_type = 'slack'"
              >
                <span class="option-icon">🟡</span>
                <span class="option-name">Slack</span>
              </div>
              <div
                class="type-option"
                :class="{ selected: formData.channel_type === 'discord' }"
                @click="formData.channel_type = 'discord'"
              >
                <span class="option-icon">🟠</span>
                <span class="option-name">Discord</span>
              </div>
              <div
                class="type-option"
                :class="{ selected: formData.channel_type === 'email' }"
                @click="formData.channel_type = 'email'"
              >
                <span class="option-icon">📧</span>
                <span class="option-name">Email</span>
              </div>
              <div
                class="type-option"
                :class="{ selected: formData.channel_type === 'webhook' }"
                @click="formData.channel_type = 'webhook'"
              >
                <span class="option-icon">🟢</span>
                <span class="option-name">Webhook</span>
              </div>
            </div>
          </div>

          <!-- 基本信息 -->
          <div class="form-section">
            <label class="section-label">基本信息</label>
            <div class="form-group">
              <input
                type="text"
                v-model="formData.name"
                placeholder="渠道名称，如：安全组-钉钉"
                class="form-input"
              />
            </div>
            <div class="form-group">
              <textarea
                v-model="formData.description"
                placeholder="渠道用途说明（可选）"
                class="form-textarea"
                rows="2"
              ></textarea>
            </div>
          </div>

          <!-- Webhook 配置 -->
          <div class="form-section">
            <label class="section-label">Webhook 配置</label>
            <div class="form-group">
              <input
                type="text"
                v-model="formData.webhook_url"
                placeholder="Webhook URL"
                class="form-input"
              />
            </div>
            <div class="form-group" v-if="formData.channel_type === 'dingtalk'">
              <input
                type="text"
                v-model="formData.secret"
                placeholder="签名密钥（可选，用于加签验证）"
                class="form-input"
              />
            </div>
          </div>

          <!-- 启用状态 -->
          <div class="form-section toggle-section">
            <div class="toggle-row">
              <span class="toggle-label">启用此渠道</span>
              <div class="status-switch" :class="{ on: formData.enabled }" @click="formData.enabled = !formData.enabled">
                <span class="switch-slider"></span>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button class="footer-btn cancel" @click="closeModal">取消</button>
          <button class="footer-btn save" @click="saveChannel" :disabled="saving">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div class="modal-overlay small" v-if="showDeleteModal" @click.self="showDeleteModal = false">
      <div class="modal-container small">
        <div class="modal-header warning">
          <span class="warning-icon">⚠️</span>
          <h2 class="modal-title">确认删除</h2>
        </div>
        <div class="modal-body center">
          <p class="confirm-text">确定要删除渠道 <strong>{{ deleteTarget?.name }}</strong> 吗？</p>
          <p class="confirm-warning">删除后，绑定此渠道的定时任务将无法发送告警消息</p>
        </div>
        <div class="modal-footer">
          <button class="footer-btn cancel" @click="showDeleteModal = false">取消</button>
          <button class="footer-btn delete" @click="doDelete" :disabled="deleting">
            {{ deleting ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 测试结果弹窗 -->
    <div class="modal-overlay small" v-if="showTestModal" @click.self="showTestModal = false">
      <div class="modal-container small">
        <div class="modal-header" :class="testResult?.code === 0 ? 'success' : 'error'">
          <span class="result-icon">{{ testResult?.code === 0 ? '✅' : '❌' }}</span>
          <h2 class="modal-title">测试结果</h2>
        </div>
        <div class="modal-body center">
          <p class="result-text" :class="testResult?.code === 0 ? 'success' : 'error'">
            {{ testResult?.message }}
          </p>
        </div>
        <div class="modal-footer center">
          <button class="footer-btn primary" @click="showTestModal = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import {
  getChannels,
  createChannel,
  updateChannel,
  deleteChannel,
  enableChannel,
  disableChannel,
  testChannel
} from '../api/dashboard'

export default {
  name: 'AlertChannel',
  data() {
    return {
      channels: [],
      filterType: '',
      showModal: false,
      showDeleteModal: false,
      showTestModal: false,
      isEditing: false,
      formData: {
        name: '',
        channel_type: 'dingtalk',
        webhook_url: '',
        secret: '',
        description: '',
        enabled: true
      },
      editTarget: null,
      deleteTarget: null,
      testResult: null,
      testingChannel: null,
      saving: false,
      deleting: false
    }
  },
  async mounted() {
    await this.loadChannels()
  },
  methods: {
    async loadChannels() {
      try {
        const result = await getChannels(this.filterType)
        this.channels = result.channels || []
      } catch (err) {
        console.error('加载渠道失败:', err)
      }
    },
    getTypeIcon(type) {
      const icons = { dingtalk: '🔵', feishu: '🟣', slack: '🟡', discord: '🟠', email: '📧', webhook: '🟢' }
      return icons[type] || '⚪'
    },
    getTypeLabel(type) {
      const labels = { dingtalk: '钉钉', feishu: '飞书', slack: 'Slack', discord: 'Discord', email: 'Email', webhook: 'Webhook' }
      return labels[type] || type
    },
    maskWebhook(url) {
      if (!url) return ''
      try {
        const urlObj = new URL(url)
        return urlObj.origin + '/...'
      } catch {
        return url.length > 40 ? url.substring(0, 40) + '...' : url
      }
    },
    openCreateModal() {
      this.isEditing = false
      this.editTarget = null
      this.formData = {
        name: '',
        channel_type: 'dingtalk',
        webhook_url: '',
        secret: '',
        description: '',
        enabled: true
      }
      this.showModal = true
    },
    openEditModal(channel) {
      this.isEditing = true
      this.editTarget = channel
      this.formData = {
        name: channel.name,
        channel_type: channel.channel_type,
        webhook_url: channel.webhook_url,
        secret: channel.secret || '',
        description: channel.description || '',
        enabled: channel.enabled
      }
      this.showModal = true
    },
    closeModal() {
      this.showModal = false
      this.isEditing = false
      this.editTarget = null
    },
    async saveChannel() {
      if (!this.formData.name) {
        alert('请填写渠道名称')
        return
      }
      if (!this.formData.webhook_url) {
        alert('请填写 Webhook URL')
        return
      }

      this.saving = true
      try {
        if (this.isEditing && this.editTarget) {
          await updateChannel(this.editTarget.id, this.formData)
        } else {
          await createChannel(this.formData)
        }
        await this.loadChannels()
        this.closeModal()
      } catch (err) {
        alert('保存失败: ' + err.message)
      }
      this.saving = false
    },
    async toggleChannel(channel) {
      try {
        if (channel.enabled) {
          await disableChannel(channel.id)
        } else {
          await enableChannel(channel.id)
        }
        await this.loadChannels()
      } catch (err) {
        alert('操作失败: ' + err.message)
      }
    },
    async handleTestChannel(channel) {
      this.testingChannel = channel.id
      try {
        const result = await testChannel(channel.id)
        this.testResult = result
        this.showTestModal = true
      } catch (err) {
        this.testResult = { code: 1, message: err.message }
        this.showTestModal = true
      }
      this.testingChannel = null
    },
    confirmDelete(channel) {
      this.deleteTarget = channel
      this.showDeleteModal = true
    },
    async doDelete() {
      this.deleting = true
      try {
        await deleteChannel(this.deleteTarget.id)
        await this.loadChannels()
        this.showDeleteModal = false
        this.deleteTarget = null
      } catch (err) {
        alert('删除失败: ' + err.message)
      }
      this.deleting = false
    }
  }
}
</script>

<style scoped>
.channel-container {
  padding: 32px 40px;
  min-height: 100vh;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
}

/* 页面头部 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 32px;
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  display: flex;
  align-items: center;
  gap: 12px;
}

.title-icon {
  font-size: 32px;
}

.page-desc {
  font-size: 14px;
  color: #64748b;
  margin-top: 8px;
}

.create-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.25);
}

.create-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(14, 165, 233, 0.35);
}

.btn-icon {
  font-size: 18px;
  font-weight: 300;
}

/* 筛选栏 */
.filter-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.filter-tabs {
  display: flex;
  gap: 8px;
}

.filter-tab {
  padding: 10px 20px;
  background: #fff;
  border: 2px solid #e2e8f0;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-tab:hover {
  border-color: #cbd5e1;
}

.filter-tab.active {
  background: #e0f2fe;
  border-color: #0ea5e9;
  color: #0ea5e9;
}

.filter-tab.dingtalk.active {
  background: #eff6ff;
  border-color: #2563eb;
  color: #2563eb;
}

.filter-tab.feishu.active {
  background: #f5f3ff;
  border-color: #7c3aed;
  color: #7c3aed;
}

.filter-tab.webhook.active {
  background: #f0fdf4;
  border-color: #16a34a;
  color: #16a34a;
}

.filter-tab.slack.active {
  background: #fffbeb;
  border-color: #f59e0b;
  color: #f59e0b;
}

.filter-tab.discord.active {
  background: #fff7ed;
  border-color: #ea580c;
  color: #ea580c;
}

.filter-tab.email.active {
  background: #f0f9ff;
  border-color: #0284c7;
  color: #0284c7;
}

.stats-info {
  font-size: 14px;
  color: #94a3b8;
}

.count {
  font-weight: 600;
  color: #1e293b;
}

/* 渠道网格 */
.channel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.channel-card {
  background: #fff;
  border-radius: 16px;
  padding: 20px;
  position: relative;
  transition: all 0.3s;
  border: 2px solid transparent;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.channel-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.08);
}

.channel-card.dingtalk {
  border-color: rgba(37, 99, 235, 0.2);
}

.channel-card.feishu {
  border-color: rgba(124, 58, 237, 0.2);
}

.channel-card.webhook {
  border-color: rgba(22, 163, 74, 0.2);
}

/* 类型标识 */
.card-type-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.card-type-badge.dingtalk {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
}

.card-type-badge.feishu {
  background: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%);
}

.card-type-badge.webhook {
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
}

.card-type-badge.slack {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
}

.card-type-badge.discord {
  background: linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%);
}

.card-type-badge.email {
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
}

.type-icon {
  font-size: 16px;
}

.type-name {
  font-size: 13px;
  font-weight: 600;
}

.card-type-badge.dingtalk .type-name { color: #2563eb; }
.card-type-badge.feishu .type-name { color: #7c3aed; }
.card-type-badge.slack .type-name { color: #f59e0b; }
.card-type-badge.discord .type-name { color: #ea580c; }
.card-type-badge.email .type-name { color: #0284c7; }
.card-type-badge.webhook .type-name { color: #16a34a; }

/* 卡片内容 */
.card-content {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.channel-name {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
}

/* 开关 */
.status-switch {
  width: 48px;
  height: 26px;
  background: #e2e8f0;
  border-radius: 13px;
  cursor: pointer;
  position: relative;
  transition: all 0.3s;
}

.status-switch.on {
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
}

.switch-slider {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  background: #fff;
  border-radius: 10px;
  transition: all 0.3s;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.status-switch.on .switch-slider {
  left: 25px;
}

.channel-desc {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 12px;
  line-height: 1.5;
}

.channel-webhook {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.webhook-label {
  color: #94a3b8;
}

.webhook-value {
  color: #64748b;
  font-family: 'SF Mono', monospace;
}

/* 操作按钮 */
.card-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn.test {
  background: #f0f9ff;
  color: #0369a1;
}

.action-btn.test:hover {
  background: #e0f2fe;
}

.action-btn.edit {
  background: #fafafa;
  color: #64748b;
}

.action-btn.edit:hover {
  background: #f5f5f5;
  color: #1e293b;
}

.action-btn.delete {
  background: #fef2f2;
  color: #dc2626;
}

.action-btn.delete:hover {
  background: #fee2e2;
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-icon {
  font-size: 14px;
}

/* 状态角标 */
.status-corner {
  position: absolute;
  top: 20px;
  right: 20px;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
}

.status-corner.enabled {
  background: #dcfce7;
  color: #16a34a;
}

.status-corner.disabled {
  background: #fef3c7;
  color: #d97706;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 60px 40px;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.empty-title {
  font-size: 20px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 8px;
}

.empty-desc {
  font-size: 14px;
  color: #64748b;
  margin-bottom: 24px;
}

.empty-tips {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 400px;
  margin: 0 auto;
}

.tip-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #94a3b8;
  background: #fff;
  padding: 12px 16px;
  border-radius: 8px;
}

.tip-icon {
  font-size: 16px;
}

/* 弹窗 */
.modal-overlay {
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
  z-index: 1000;
}

.modal-container {
  background: #fff;
  border-radius: 20px;
  width: 480px;
  max-width: 90vw;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
}

.modal-container.small {
  width: 360px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 28px;
  border-bottom: 1px solid #f1f5f9;
}

.modal-header.warning {
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
}

.modal-header.success {
  background: linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%);
}

.modal-header.error {
  background: linear-gradient(135deg, #fef2f2 0%, #fecaca 100%);
}

.modal-title {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
  display: flex;
  align-items: center;
  gap: 8px;
}

.warning-icon, .result-icon {
  font-size: 20px;
}

.modal-close {
  background: none;
  border: none;
  font-size: 24px;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  line-height: 1;
}

.modal-close:hover {
  color: #64748b;
}

.modal-body {
  padding: 28px;
}

.modal-body.center {
  text-align: center;
}

/* 表单区块 */
.form-section {
  margin-bottom: 24px;
}

.section-label {
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 12px;
  display: block;
}

/* 类型选择器 */
.type-selector {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.type-option {
  flex: 1 1 calc(33.333% - 8px);
  min-width: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: #f8fafc;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.type-option:hover {
  border-color: #cbd5e1;
}

.type-option.selected {
  background: #fff;
  border-color: #0ea5e9;
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.15);
}

.type-option.selected.dingtalk {
  border-color: #2563eb;
  background: #eff6ff;
}

.type-option.selected.feishu {
  border-color: #7c3aed;
  background: #f5f3ff;
}

.type-option.selected.webhook {
  border-color: #16a34a;
  background: #f0fdf4;
}

.option-icon {
  font-size: 24px;
}

.option-name {
  font-size: 14px;
  font-weight: 500;
  color: #1e293b;
}

.form-group {
  margin-bottom: 12px;
}

.form-input {
  width: 100%;
  padding: 14px 16px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  font-size: 14px;
  color: #1e293b;
  transition: all 0.2s;
}

.form-input:focus {
  border-color: #0ea5e9;
  outline: none;
  box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.1);
}

.form-textarea {
  width: 100%;
  padding: 14px 16px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  font-size: 14px;
  color: #1e293b;
  resize: none;
  transition: all 0.2s;
}

.form-textarea:focus {
  border-color: #0ea5e9;
  outline: none;
}

/* 开关区块 */
.toggle-section {
  background: #f8fafc;
  padding: 16px;
  border-radius: 12px;
}

.toggle-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.toggle-label {
  font-size: 14px;
  color: #1e293b;
}

/* 弹窗底部 */
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 28px;
  border-top: 1px solid #f1f5f9;
}

.modal-footer.center {
  justify-content: center;
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

.footer-btn.delete {
  background: linear-gradient(135deg, #f87171 0%, #dc2626 100%);
  color: white;
  border: none;
}

.footer-btn.delete:hover {
  box-shadow: 0 4px 12px rgba(220, 38, 38, 0.3);
}

.footer-btn.delete:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.footer-btn.primary {
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  color: white;
  border: none;
}

/* 确认弹窗 */
.confirm-text {
  font-size: 16px;
  color: #1e293b;
  margin-bottom: 12px;
}

.confirm-warning {
  font-size: 13px;
  color: #f59e0b;
}

/* 结果弹窗 */
.result-text {
  font-size: 15px;
}

.result-text.success {
  color: #16a34a;
}

.result-text.error {
  color: #dc2626;
}
</style>