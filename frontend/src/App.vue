<template>
  <div class="app-container">
    <!-- 侧边栏 -->
    <Sidebar
      :sessions="sessions"
      :current-session-id="currentSessionId"
      :current-view="currentView"
      @select-session="handleSelectSession"
      @new-chat="handleNewChat"
      @delete-session="handleDeleteSession"
      @switch-view="handleSwitchView"
    />

    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 对话视图 -->
      <template v-if="currentView === 'chat'">
        <ChatArea
          :messages="messages"
          :streaming="isStreaming"
          :show-tool-calls="showToolCalls"
          :repo-status="repoStatusData"
        />
        <InputArea
          @send="handleSend"
          @stop="handleStop"
          @toggle-tool-calls="showToolCalls = $event"
          :streaming="isStreaming"
          :show-tool-calls="showToolCalls"
        />
      </template>

      <!-- 仪表板视图 -->
      <Dashboard
        v-else-if="currentView === 'dashboard'"
        @switch-view="handleSwitchView"
        @filter-alerts="handleFilterAlerts"
      />

      <!-- 预警列表视图 -->
      <AlertList v-else-if="currentView === 'alerts'" ref="alertListRef" />

      <!-- 定时任务视图 -->
      <ScheduledTask v-else-if="currentView === 'scheduled-tasks'" @goto-channels="handleSwitchView('channels')" />

      <!-- 告警渠道视图 -->
      <AlertChannel v-else-if="currentView === 'channels'" />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatArea from './components/ChatArea.vue'
import InputArea from './components/InputArea.vue'
import Dashboard from './components/Dashboard.vue'
import AlertList from './components/AlertList.vue'
import ScheduledTask from './components/ScheduledTask.vue'
import AlertChannel from './components/AlertChannel.vue'
import { streamChat } from './api/chat.js'

// 状态
const sessions = ref([])
const currentSessionId = ref(null)
const currentView = ref('chat')
const messages = ref([])
const isStreaming = ref(false)
const showToolCalls = ref(true)
const repoStatusData = ref(null)  // 仓库状态数据
const alertListRef = ref(null)
const streamingAiMsgId = ref(null)  // 当前正在流式输出的 AI 消息 ID
let abortController = null

// 自动触发文件下载
function triggerDownload(url, filename = '') {
  const a = document.createElement('a')
  a.href = url
  if (filename) {
    a.download = filename
  }
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  console.log('[App] 自动下载已触发:', url, filename)
}

// 从 base64 内容触发下载（直接下载，不需要额外的 HTTP 请求）
function triggerDownloadFromContent(contentB64, filename, contentType = 'application/octet-stream') {
  try {
    // 解码 base64
    const byteCharacters = atob(contentB64)
    const byteNumbers = new Array(byteCharacters.length)
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i)
    }
    const byteArray = new Uint8Array(byteNumbers)

    // 创建 Blob
    const blob = new Blob([byteArray], { type: contentType })

    // 创建下载链接
    const url = URL.createObjectURL(blob)
    triggerDownload(url, filename)

    // 清理 URL
    setTimeout(() => URL.revokeObjectURL(url), 100)

    console.log('[App] 内容下载已触发:', filename, 'size:', byteArray.length)
  } catch (e) {
    console.error('[App] 内容下载失败:', e)
    // 回退到 URL 方式
    triggerDownload(`/api/download/sandbox/${filename}`, filename)
  }
}

// 解析工具返回字符串（处理多种格式）
function parsePythonDict(str) {
  if (!str) return null

  console.log('[App] 原始字符串长度:', str.length, '前100字符:', str.slice(0, 100))

  // 尝试标准 JSON（整个字符串就是 JSON）
  try {
    return JSON.parse(str)
  } catch {}

  // 处理 content='...' 格式（LangChain 工具返回格式）
  // 格式: content='{"success": true, ...}' name='xxx' tool_call_id='xxx'
  try {
    // 找到 content=' 后面的内容
    const contentStart = str.indexOf("content='")
    if (contentStart !== -1) {
      // 从 content=' 后面开始找
      let start = contentStart + 9 // "content='".length = 9
      // 找到结束的单引号（注意转义）
      let end = start
      let depth = 0
      while (end < str.length) {
        const ch = str[end]
        if (ch === '{') depth++
        else if (ch === '}') depth--
        if (depth === 0 && str[end] === "'") {
          break
        }
        end++
      }
      const contentStr = str.slice(start, end)
      console.log('[App] 提取 content 长度:', contentStr.length)
      // 直接解析 JSON（因为 content 已经是 JSON 格式）
      return JSON.parse(contentStr)
    }
  } catch (e) {
    console.warn('[App] content= 格式解析失败:', e.message)
  }

  // 处理 Python dict 格式: {'key': 'value'} -> {"key": "value"}
  try {
    let jsonStr = str
      .replace(/True/g, 'true')
      .replace(/False/g, 'false')
      .replace(/None/g, 'null')
      .replace(/'/g, '"')
      .replace(/\s+/g, ' ')
    return JSON.parse(jsonStr)
  } catch (e) {
    console.warn('[App] Python dict 格式解析失败:', e.message)
  }

  console.warn('[App] 所有解析尝试都失败')
  return null
}

onMounted(async () => {
  // 从 localStorage 加载历史会话列表
  const savedSessions = localStorage.getItem('osint-sessions')
  if (savedSessions) {
    try {
      sessions.value = JSON.parse(savedSessions)
      console.log('[App] 加载历史会话:', sessions.value.length, '个')
    } catch (e) {
      console.warn('[App] 加载会话列表失败:', e)
    }
  }
})

// 保存会话列表到 localStorage
function saveSessionsToStorage() {
  localStorage.setItem('osint-sessions', JSON.stringify(sessions.value))
  console.log('[App] 保存会话列表:', sessions.value.length, '个')
}

function handleSelectSession(sessionId) {
  if (sessionId === currentSessionId.value) return
  currentSessionId.value = sessionId
  // 从 localStorage 加载会话消息
  const saved = localStorage.getItem(`osint-session-${sessionId}`)
  if (saved) {
    messages.value = JSON.parse(saved)
  }
}

function handleNewChat() {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  isStreaming.value = false
  repoStatusData.value = null
  streamingAiMsgId.value = null
  currentSessionId.value = null
  messages.value = []
}

function handleSwitchView(view) {
  currentView.value = view
}

function handleFilterAlerts(filters) {
  // 切换到预警列表后，设置筛选条件
  if (filters.severity) {
    // 等待组件渲染后设置筛选条件
    setTimeout(() => {
      if (alertListRef.value) {
        alertListRef.value.setFilters(filters)
      }
    }, 100)
  }
}

function handleDeleteSession(sessionId) {
  localStorage.removeItem(`osint-session-${sessionId}`)
  sessions.value = sessions.value.filter(s => s.id !== sessionId)
  saveSessionsToStorage()
  if (currentSessionId.value === sessionId) {
    handleNewChat()
  }
}

function handleStop() {
  if (abortController) {
    abortController.abort()
    abortController = null
    isStreaming.value = false
    repoStatusData.value = null
    streamingAiMsgId.value = null
    // 将所有正在执行的工具标记为已停止
    for (const m of messages.value) {
      if (m.role === 'tool' && m.tool_status === 'calling') {
        m.tool_status = 'stopped'
        m.output = '(已停止)'
      }
    }
    // 如果 AI 消息为空，添加提示
    const aiMsg = messages.value.find(m => m.id === streamingAiMsgId.value)
    if (aiMsg && !aiMsg.content) {
      aiMsg.content = '(已停止)'
    }
  }
}

async function handleSend(message) {
  if (isStreaming.value) return

  // 添加用户消息
  messages.value.push({
    id: `user-${Date.now()}`,
    role: 'user',
    content: message
  })

  isStreaming.value = true
  abortController = new AbortController()

  // 添加空的 AI 消息用于流式填充
  const aiMsgId = `assistant-${Date.now()}`
  streamingAiMsgId.value = aiMsgId  // 保存当前流式 AI 消息 ID
  messages.value.push({
    id: aiMsgId,
    role: 'assistant',
    content: '',
    source: 'main'
  })

  try {
    const result = await streamChat(
      message,
      currentSessionId.value,
      {
        onStart: (data) => {
          if (!currentSessionId.value) {
            currentSessionId.value = data.session_id
            // 保存到会话列表
            sessions.value.unshift({
              id: data.session_id,
              title: message.slice(0, 30),
              updated_at: new Date().toISOString()
            })
            // 保存会话列表到 localStorage
            saveSessionsToStorage()
          }
        },
        onToken: (content) => {
          console.log('[App] onToken 回调触发, streamingAiMsgId:', streamingAiMsgId.value)
          // 使用保存的 streamingAiMsgId 找到正确的 AI 消息
          const aiMsg = messages.value.find(m => m.id === streamingAiMsgId.value)
          console.log('[App] 找到的消息:', aiMsg ? { id: aiMsg.id, contentLen: aiMsg.content?.length } : '未找到')
          if (aiMsg) {
            aiMsg.content += content
          }
        },
        onToolStart: (tool) => {
          messages.value.push({
            id: tool.id,
            role: 'tool',
            tool_name: tool.name,
            input: tool.input,
            output: '',
            tool_status: 'calling',
            source: 'main'
          })
        },
        onToolEnd: (data) => {
          const toolMsg = messages.value.find(m => m.role === 'tool' && m.tool_name === data.name && m.tool_status === 'calling')
          if (toolMsg) {
            toolMsg.output = data.output
            toolMsg.tool_status = 'done'
          }
          // 处理报告下载 - 直接使用返回的内容触发下载
          if (data.name === 'return_report_for_download') {
            console.log('[App] 收到下载工具返回:', data.output)
            const result = parsePythonDict(data.output)
            console.log('[App] 解析结果:', result)
            if (result && result.success && result.action === 'download') {
              // 如果有 content_b64，直接从内容下载
              if (result.content_b64) {
                console.log('[App] 使用内容下载, filename:', result.filename, 'content_type:', result.content_type)
                triggerDownloadFromContent(
                  result.content_b64,
                  result.filename,
                  result.content_type || 'text/markdown'
                )
              } else if (result.sandbox_path) {
                // 回退：构建 API 下载 URL
                console.log('[App] 使用URL下载, sandbox_path:', result.sandbox_path)
                const downloadUrl = `/api/download/sandbox${result.sandbox_path}`
                triggerDownload(downloadUrl, result.filename)
              } else {
                console.log('[App] 既没有 content_b64 也没有 sandbox_path')
              }
            } else {
              console.log('[App] 解析失败或 success/action 不正确')
              // 尝试从字符串中提取 sandbox_path（兼容旧版本）
              const match = data.output.match(/sandbox_path[=:]\s*['"]?([^'"}\s]+)['"]?/)
              if (match) {
                console.log('[App] 兜底提取 sandbox_path:', match[1])
                const downloadUrl = `/api/download/sandbox${match[1]}`
                triggerDownload(downloadUrl)
              }
            }
          }
        },
        onRepoStatus: (data) => {
          // 更新仓库状态数据
          repoStatusData.value = data
        },
        onDone: (data) => {
          isStreaming.value = false
          // 清理状态
          repoStatusData.value = null
          streamingAiMsgId.value = null
          // 保存会话消息到 localStorage
          if (currentSessionId.value) {
            localStorage.setItem(`osint-session-${currentSessionId.value}`, JSON.stringify(messages.value))
            // 更新会话列表的时间戳和标题（如果有内容）
            const session = sessions.value.find(s => s.id === currentSessionId.value)
            if (session) {
              session.updated_at = new Date().toISOString()
              // 从 AI 最后回复提取更好的标题
              const lastAiMsg = messages.value.filter(m => m.role === 'assistant' && m.content).pop()
              if (lastAiMsg && lastAiMsg.content) {
                const firstLine = lastAiMsg.content.split('\n')[0].slice(0, 30)
                if (firstLine && firstLine.length > 5) {
                  session.title = firstLine
                }
              }
            }
            saveSessionsToStorage()
          }
        },
        onError: (error) => {
          console.error('[App] 错误:', error)
          // 清理仓库状态数据
          repoStatusData.value = null
          streamingAiMsgId.value = null
          // 将所有执行中的工具标记为错误
          for (const m of messages.value) {
            if (m.role === 'tool' && m.tool_status === 'calling') {
              m.tool_status = 'error'
              m.output = `(执行失败)`
            }
          }
          // 使用 streamingAiMsgId 找到正确的 AI 消息
          const aiMsg = messages.value.find(m => m.id === streamingAiMsgId.value)
          if (aiMsg && !aiMsg.content) {
            aiMsg.content = `错误: ${error.message}`
          } else {
            // 添加错误消息
            messages.value.push({
              id: `error-${Date.now()}`,
              role: 'assistant',
              content: `❌ **错误**: ${error.message}`,
              source: 'main'
            })
          }
          isStreaming.value = false
        }
      },
      abortController.signal
    )
  } catch (error) {
    if (error.name !== 'AbortError') {
      console.error('[App] 发送失败:', error)
    }
    isStreaming.value = false
  } finally {
    abortController = null
  }
}
</script>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  background: #f8fafc;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;  /* 允许滚动 */
  background: #ffffff;
  border-left: 1px solid #e2e8f0;
}
</style>