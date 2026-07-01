<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="logo">
        <span class="logo-icon">🔍</span>
        <span class="logo-text">OSINT</span>
      </div>
    </div>

    <!-- 导航菜单 -->
    <div class="nav-menu">
      <div
        class="nav-item"
        :class="{ active: currentView === 'chat' }"
        @click="$emit('switch-view', 'chat')"
      >
        <span class="nav-icon">💬</span>
        <span class="nav-text">对话分析</span>
      </div>
      <div
        class="nav-item"
        :class="{ active: currentView === 'dashboard' }"
        @click="$emit('switch-view', 'dashboard')"
      >
        <span class="nav-icon">📊</span>
        <span class="nav-text">情报看板</span>
      </div>
      <div
        class="nav-item"
        :class="{ active: currentView === 'alerts' }"
        @click="$emit('switch-view', 'alerts')"
      >
        <span class="nav-icon">🔔</span>
        <span class="nav-text">预警列表</span>
      </div>
      <div
        class="nav-item"
        :class="{ active: currentView === 'scheduled-tasks' }"
        @click="$emit('switch-view', 'scheduled-tasks')"
      >
        <span class="nav-icon">⏰</span>
        <span class="nav-text">定时任务</span>
      </div>
      <div
        class="nav-item"
        :class="{ active: currentView === 'channels' }"
        @click="$emit('switch-view', 'channels')"
      >
        <span class="nav-icon">📢</span>
        <span class="nav-text">告警渠道</span>
      </div>
    </div>

    <!-- 对话视图时显示新建按钮和历史会话 -->
    <template v-if="currentView === 'chat'">
      <div class="new-chat-section">
        <button class="new-chat-btn" @click="$emit('new-chat')">
          <span class="icon">+</span>
          新建分析
        </button>
      </div>

      <div class="search-box">
        <input type="text" v-model="searchKeyword" placeholder="搜索会话..." class="search-input" />
      </div>

      <div class="session-list">
        <div class="session-list-header">
          <span>历史分析</span>
        </div>
        <div class="session-items">
          <div
            v-for="session in filteredSessions"
            :key="session.id"
            class="session-item"
            :class="{ active: session.id === currentSessionId }"
            @click="$emit('select-session', session.id)"
          >
            <div class="session-info">
              <span class="session-title">{{ session.title }}</span>
              <span class="session-time">{{ formatTime(session.updated_at) }}</span>
            </div>
            <button class="delete-btn" @click.stop="$emit('delete-session', session.id)" title="删除此会话">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </div>
          <div v-if="sessions.length === 0" class="empty-state">
            <p>暂无分析记录</p>
          </div>
        </div>
      </div>
    </template>

    <div class="sidebar-footer">
      <div class="footer-info">
        <span class="version">v3.0.0</span>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  sessions: { type: Array, default: () => [] },
  currentSessionId: { type: String, default: null },
  currentView: { type: String, default: 'chat' }
})

const emit = defineEmits(['select-session', 'new-chat', 'delete-session', 'switch-view'])

const searchKeyword = ref('')

const filteredSessions = computed(() => {
  if (!searchKeyword.value) return props.sessions
  return props.sessions.filter(s => s.title.toLowerCase().includes(searchKeyword.value.toLowerCase()))
})

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date
  if (diff < 24 * 60 * 60 * 1000) {
    const hours = Math.floor(diff / (60 * 60 * 1000))
    return hours < 1 ? '刚刚' : `${hours}小时前`
  }
  return `${date.getMonth() + 1}/${date.getDate()}`
}
</script>

<style scoped>
.sidebar {
  width: 280px;
  height: 100vh;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e2e8f0;
}

.sidebar-header {
  padding: 20px 16px;
  border-bottom: 1px solid #f1f5f9;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  font-size: 32px;
}

.logo-text {
  font-size: 20px;
  font-weight: 700;
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.nav-menu {
  padding: 12px 16px;
  border-bottom: 1px solid #f1f5f9;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 4px;
}

.nav-item:hover {
  background: #f1f5f9;
}

.nav-item.active {
  background: #e0f2fe;
  border: 1px solid #7dd3fc;
}

.nav-icon {
  font-size: 20px;
}

.nav-text {
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
}

.new-chat-section {
  padding: 16px;
}

.new-chat-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 12px 20px;
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  color: #fff;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.new-chat-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
}

.search-box {
  padding: 16px;
}

.search-input {
  width: 100%;
  padding: 12px 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  font-size: 14px;
  outline: none;
}

.search-input:focus {
  border-color: #0ea5e9;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.session-list-header {
  padding: 12px 16px 8px;
  font-size: 12px;
  color: #94a3b8;
  font-weight: 600;
}

.session-items {
  padding: 0 12px;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  margin-bottom: 4px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.session-item:hover {
  background: #f1f5f9;
}

.session-item.active {
  background: #e0f2fe;
  border: 1px solid #7dd3fc;
}

.session-info {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.session-title {
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #1e293b;
}

.session-time {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 3px;
}

.delete-btn {
  flex-shrink: 0;
  opacity: 0;
  padding: 6px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: 8px;
}

.session-item:hover .delete-btn {
  opacity: 1;
  background: #fef2f2;
  color: #dc2626;
}

.delete-btn:hover {
  background: #fee2e2;
  color: #b91c1c;
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: #94a3b8;
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid #f1f5f9;
}

.version {
  font-size: 12px;
  color: #94a3b8;
}
</style>