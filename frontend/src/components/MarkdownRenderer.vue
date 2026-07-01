<template>
  <div class="markdown-wrapper">
    <div class="markdown-renderer" v-html="renderedContent"></div>
    <!-- 复制按钮 -->
    <button
      v-if="showCopyButton && props.content"
      class="copy-btn"
      @click="copyContent"
      :title="copied ? '已复制' : '复制原文'"
    >
      {{ copied ? '✓ 已复制' : '📋 复制' }}
    </button>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

const props = defineProps({
  content: { type: String, default: '' },
  showCopyButton: { type: Boolean, default: false }  // 是否显示复制按钮
})

const renderedContent = ref('')
const copied = ref(false)
let md = null

// 高危关键词列表
const HIGH_RISK_KEYWORDS = [
  'CRITICAL', 'HIGH', 'RCE', 'Log4Shell', 'CVE-', '漏洞', '敏感信息',
  'secret', 'password', 'token', 'api_key', 'private_key', ' credential'
]

// 文件路径正则（匹配常见路径格式）
const FILE_PATH_REGEX = /(?:\/[\w\-\.]+\/[\w\-\.]+|reports\/[\w\-\.\/]+|\.[\w]+文件|[\w\-]+\.md|[\w\-]+\.json)/g

onMounted(() => {
  md = new MarkdownIt({
    html: true,
    breaks: true,
    linkify: true,
    typographer: true,
    highlight: (str, lang) => {
      if (lang && hljs.getLanguage(lang)) {
        try {
          return hljs.highlight(str, { language: lang }).value
        } catch {}
      }
      return ''
    }
  })
  renderContent()
})

watch(() => props.content, renderContent)

function renderContent() {
  if (!md) return
  try {
    let html = md.render(props.content || '')
    // 后处理：高危关键词高亮 + 文件路径样式
    html = enhanceContent(html)
    renderedContent.value = html
  } catch {
    renderedContent.value = escapeHtml(props.content || '')
  }
}

function enhanceContent(html) {
  // 1. 高危关键词高亮（不处理已存在于 code 或 标签内的）
  HIGH_RISK_KEYWORDS.forEach(keyword => {
    // 匹配文本中的关键词（不在 code 标签内，不在已有 risk-badge 内）
    const regex = new RegExp(`(?<![<>])(${keyword})(?![<>])`, 'gi')
    html = html.replace(regex, (match) => {
      // 检查是否在危险级别（CRITICAL/HIGH）
      if (keyword === 'CRITICAL' || match.toUpperCase() === 'CRITICAL') {
        return `<span class="risk-badge critical">⚠️ ${match}</span>`
      }
      if (keyword === 'HIGH' || match.toUpperCase() === 'HIGH') {
        return `<span class="risk-badge high">🔴 ${match}</span>`
      }
      if (keyword === 'RCE' || match.toUpperCase() === 'RCE') {
        return `<span class="risk-badge critical">⚠️ ${match}</span>`
      }
      if (keyword === 'Log4Shell') {
        return `<span class="risk-badge critical">⚠️ Log4Shell</span>`
      }
      // 其他关键词用普通高亮
      return `<span class="keyword-highlight">${match}</span>`
    })
  })

  // 2. 文件路径样式（添加图标）
  html = html.replace(FILE_PATH_REGEX, (match) => {
    // 如果路径已经被包裹在 code 标签内，跳过
    if (match.includes('<code>') || match.includes('</code>')) return match
    return `<span class="file-path">📁 ${match}</span>`
  })

  return html
}

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.content)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch (e) {
    console.error('复制失败:', e)
  }
}
</script>

<style scoped>
.markdown-wrapper {
  position: relative;
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 6px 12px;
  background: rgba(14, 165, 233, 0.1);
  border: 1px solid rgba(14, 165, 233, 0.3);
  border-radius: 6px;
  font-size: 12px;
  color: #0ea5e9;
  cursor: pointer;
  transition: all 0.2s;
  opacity: 0.8;
}

.copy-btn:hover {
  background: rgba(14, 165, 233, 0.2);
  opacity: 1;
}

.markdown-renderer {
  font-size: 15px;
  line-height: 1.85;
  color: #1e293b;
  overflow: hidden;
}
</style>

<style>
/* === 基础排版 === */
.markdown-renderer h1 { font-size: 26px; font-weight: 700; margin: 24px 0 14px; color: #0f172a; }
.markdown-renderer h2 { font-size: 22px; font-weight: 600; margin: 20px 0 12px; color: #1e293b; }
.markdown-renderer h3 { font-size: 18px; font-weight: 600; margin: 18px 0 10px; color: #334155; }
.markdown-renderer p { margin: 12px 0; }
.markdown-renderer ul, .markdown-renderer ol { margin: 12px 0; padding-left: 30px; }
.markdown-renderer li { margin: 8px 0; }

/* === 代码样式 === */
.markdown-renderer code {
  padding: 3px 8px;
  background: #fef3c7;
  border: 1px solid #fde68a;
  border-radius: 6px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 14px;
  color: #b45309;
}

.markdown-renderer pre {
  margin: 14px 0;
  padding: 18px;
  background: #1e293b;
  border-radius: 12px;
  overflow-x: auto;
}

.markdown-renderer pre code {
  padding: 0;
  background: none;
  border: none;
  color: #e2e8f0;
  font-size: 14px;
}

/* === 链接 === */
.markdown-renderer a {
  color: #0ea5e9;
  text-decoration: none;
}
.markdown-renderer a:hover {
  text-decoration: underline;
}

/* === 表格样式（斑马条纹 + 深色表头） === */
.markdown-renderer table {
  width: 100%;
  border-collapse: collapse;
  margin: 14px 0;
  font-size: 14px;
  animation: fadeIn 0.3s ease;
}

.markdown-renderer th {
  padding: 14px 16px;
  background: #1e293b;
  color: #f8fafc;
  font-weight: 700;
  text-align: left;
  border: none;
}

.markdown-renderer td {
  padding: 12px 16px;
  border-bottom: 1px solid #e2e8f0;
  border-left: none;
  border-right: none;
}

/* 斑马条纹 */
.markdown-renderer tr:nth-child(even) td {
  background: #f8fafc;
}

.markdown-renderer tr:nth-child(odd) td {
  background: #ffffff;
}

.markdown-renderer tr:hover td {
  background: #f1f5f9;
}

/* === 引用块 === */
.markdown-renderer blockquote {
  margin: 14px 0;
  padding: 14px 18px;
  background: #f8fafc;
  border-left: 4px solid #0ea5e9;
  border-radius: 0 8px 8px 0;
  color: #64748b;
}

/* === 高危标签样式 === */
.markdown-renderer .risk-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
  margin: 0 2px;
  animation: pulseGlow 2s infinite;
}

.markdown-renderer .risk-badge.critical {
  background: #fee2e2;
  color: #dc2626;
  border: 1px solid #fecaca;
}

.markdown-renderer .risk-badge.high {
  background: #fef3c7;
  color: #b45309;
  border: 1px solid #fde68a;
}

/* === 关键词高亮 === */
.markdown-renderer .keyword-highlight {
  background: #ddd6fe;
  color: #7c3aed;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
}

/* === 文件路径样式 === */
.markdown-renderer .file-path {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 13px;
  color: #475569;
  user-select: all;
  cursor: pointer;
}

.markdown-renderer .file-path:hover {
  background: #e2e8f0;
}

/* === 动画 === */
@keyframes fadeIn {
  from { opacity: 0.5; }
  to { opacity: 1; }
}

@keyframes pulseGlow {
  0%, 100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); }
  50% { box-shadow: 0 0 8px 2px rgba(220, 38, 38, 0.3); }
}
</style>