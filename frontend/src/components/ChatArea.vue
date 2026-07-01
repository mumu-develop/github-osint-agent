<template>
  <div class="chat-area">
    <div class="message-list" ref="messageListRef" @scroll="handleScroll">
      <!-- 空状态 -->
      <div v-if="displayMessages.length === 0" class="empty-state">
        <div class="empty-icon">🔍</div>
        <h2>GitHub 开源情报分析系统</h2>
        <p>智能分析 GitHub 仓库的技术趋势、安全风险、社区健康度</p>
        <div class="feature-list">
          <div class="feature-item">
            <span class="feature-icon">📊</span>
            <span>技术趋势分析</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">🛡️</span>
            <span>安全漏洞扫描</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">👥</span>
            <span>社区健康评估</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">⚖️</span>
            <span>合规审计检查</span>
          </div>
        </div>
      </div>

      <!-- 消息列表 -->
      <div v-else class="messages">
        <MessageItem
          v-for="(message, index) in displayMessages"
          :key="message.id || index"
          :message="message"
          :is-streaming="isStreamingForMessage(message)"
          :repo-status="message.role === 'tool' && message.tool_status === 'calling' ? repoStatus : null"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import MessageItem from './MessageItem.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  streaming: { type: Boolean, default: false },
  showToolCalls: { type: Boolean, default: true },
  repoStatus: { type: Object, default: null }
})

const displayMessages = computed(() => {
  if (props.showToolCalls) return props.messages
  return props.messages.filter(m => m.role !== 'tool')
})

const messageListRef = ref(null)
const userScrolledUp = ref(false)  // 用户是否手动向上滚动

// 检测用户滚动行为
function handleScroll() {
  if (!messageListRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = messageListRef.value
  // 如果用户距离底部超过 150px，标记为手动向上滚动
  const nearBottom = scrollHeight - scrollTop - clientHeight < 150
  userScrolledUp.value = !nearBottom
}

function isStreamingForMessage(msg) {
  if (!props.streaming || msg.role !== 'assistant') return false
  const lastAssistant = [...props.messages].reverse().find(m => m.role === 'assistant')
  return lastAssistant === msg
}

watch(() => props.messages, () => {
  nextTick(() => {
    // 只有用户没有手动向上滚动时才自动滚动到底部
    if (!userScrolledUp.value) {
      scrollToBottom()
    }
  })
}, { deep: true })

// 流式结束时重置滚动状态
watch(() => props.streaming, (newVal) => {
  if (!newVal) {
    userScrolledUp.value = false
  }
})

function scrollToBottom() {
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #ffffff;
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0;
}

.empty-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  text-align: center;
  background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
}

.empty-icon {
  font-size: 80px;
  margin-bottom: 24px;
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

.empty-state h2 {
  font-size: 28px;
  font-weight: 700;
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom: 12px;
}

.empty-state p {
  font-size: 15px;
  color: #64748b;
  margin-bottom: 40px;
}

.feature-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  max-width: 540px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 20px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  transition: all 0.2s;
}

.feature-item:hover {
  transform: translateY(-2px);
  border-color: #0ea5e9;
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.1);
}

.feature-icon {
  font-size: 24px;
}

.feature-item span:last-child {
  font-size: 14px;
  color: #1e293b;
  font-weight: 500;
}

.messages {
  max-width: 1200px;
  margin: 0 auto;
}
</style>