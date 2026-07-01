/**
 * OSINT 对话 API 模块 - SSE 流式接口
 */

const API_BASE = '/api/osint'

/**
 * 流式对话
 */
export async function streamChat(message, sessionId = null, callbacks = {}, signal = null) {
  let fullContent = ''
  let toolCalls = []
  let reader = null

  try {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId }),
      signal// 传递 AbortSignal
    })

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`)
    }

    reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      // 检查是否已取消
      if (signal && signal.aborted) {
        break
      }

      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()

      for (const line of lines) {
        if (!line.trim() || !line.startsWith('data:')) continue

        try {
          const data = JSON.parse(line.slice(5).trim())

          switch (data.type) {
            case 'start':
              callbacks.onStart?.(data.data)
              break

            case 'token':
              console.log('[API] token 解析成功:', data.data.content?.slice(0, 30))
              fullContent += data.data.content
              callbacks.onToken?.(data.data.content)
              break

            case 'tool_call':
              const tool = {
                id: `tool-${Date.now()}`,
                name: data.data.tool,
                input: data.data.input,
                status: 'calling'
              }
              toolCalls.push(tool)
              callbacks.onToolStart?.(tool)
              break

            case 'tool_result':
              const finishedTool = toolCalls.find(t => t.name === data.data.tool && t.status === 'calling')
              if (finishedTool) {
                finishedTool.output = data.data.output
                finishedTool.status = 'done'
              }
              callbacks.onToolEnd?.({ name: data.data.tool, output: data.data.output })
              break

            case 'thinking':
              callbacks.onThinking?.(data.data)
              break

            case 'repo_status':
              callbacks.onRepoStatus?.(data.data)
              break

            case 'end':
              const result = {
                session_id: data.data.session_id,
                content: fullContent,
                tool_calls: toolCalls
              }
              callbacks.onDone?.(result)
              return result

            case 'error':
              const errorMsg = data.data.message || '未知错误'
              const traceback = data.data.traceback || ''
              console.error('[API] 服务端错误:', errorMsg)
              if (traceback) {
                console.error('[API] 错误堆栈:', traceback)
              }
              callbacks.onError?.(new Error(errorMsg))
              return { error: errorMsg, traceback }
          }
        } catch (e) {
          if (e.name === 'AbortError') throw e
          console.warn('[API] 解析 SSE 失败:', e)
        }
      }
    }

    // 用户取消时返回
    if (signal && signal.aborted) {
      callbacks.onDone?.({ aborted: true, content: fullContent })
      return { aborted: true, content: fullContent, tool_calls: toolCalls }
    }

    return { session_id: sessionId, content: fullContent, tool_calls: toolCalls }

  } catch (error) {
    if (error.name === 'AbortError') {
      console.log('[API] 请求已取消')
      callbacks.onDone?.({ aborted: true, content: fullContent })
      return { aborted: true, content: fullContent }
    }
    callbacks.onError?.(error)
    throw error
  } finally {
    // 确保 reader 被释放
    if (reader) {
      try {
        await reader.cancel()
      } catch (e) {
        // 忽略取消错误
      }
    }
  }
}

/**
 * 获取子Agent列表
 */
export async function getSubagents() {
  const response = await fetch(`${API_BASE}/subagents`)
  if (!response.ok) throw new Error('获取子Agent失败')
  return response.json()
}

/**
 * 健康检查
 */
export async function healthCheck() {
  const response = await fetch('/health')
  if (!response.ok) throw new Error('健康检查失败')
  return response.json()
}