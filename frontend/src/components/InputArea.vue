<template>
  <div class="input-area">
    <div class="input-container">
      <div class="tool-toggle">
        <label class="toggle-label">
          <input type="checkbox" :checked="showToolCalls" @change="$emit('toggle-tool-calls', $event.target.checked)" class="toggle-checkbox" />
          <span class="toggle-switch"></span>
          <span class="toggle-text">显示工具调用</span>
        </label>
      </div>

      <div class="input-wrapper" :class="{ focused: isFocused, streaming: streaming }">
        <textarea
          ref="textareaRef"
          v-model="inputText"
          @focus="isFocused = true"
          @blur="isFocused = false"
          @keydown.enter.exact.prevent="handleSend"
          @input="autoResize"
          placeholder="输入分析请求，如：分析 antgroup 组织的技术趋势..."
          rows="1"
          :disabled="streaming"
          class="input-textarea"
        ></textarea>
        <button v-if="!streaming" class="send-btn" @click="handleSend" :disabled="!inputText.trim()">
          <span>发送</span>
        </button>
        <button v-else class="stop-btn" @click="$emit('stop')">
          <span class="stop-icon">■</span>
          <span>停止</span>
        </button>
      </div>

      <div class="input-hint">
        <span v-if="!streaming">按 Enter 发送</span>
        <span v-else class="streaming-hint">正在分析中...</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const props = defineProps({
  streaming: { type: Boolean, default: false },
  showToolCalls: { type: Boolean, default: true }
})

const emit = defineEmits(['send', 'stop', 'toggle-tool-calls'])

const inputText = ref('')
const isFocused = ref(false)
const textareaRef = ref(null)

function handleSend() {
  const text = inputText.value.trim()
  if (!text) return
  emit('send', text)
  inputText.value = ''
  nextTick(() => {
    if (textareaRef.value) textareaRef.value.style.height = 'auto'
  })
}

function autoResize() {
  const textarea = textareaRef.value
  if (!textarea) return
  textarea.style.height = 'auto'
  textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px'
}
</script>

<style scoped>
.input-area {
  padding: 16px 24px 24px;
  background: #ffffff;
  border-top: 1px solid #e2e8f0;
}

.input-container {
  max-width: 1100px;
  margin: 0 auto;
}

.tool-toggle {
  margin-bottom: 12px;
}

.toggle-label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.toggle-checkbox {
  display: none;
}

.toggle-switch {
  width: 44px;
  height: 24px;
  background: #e2e8f0;
  border-radius: 12px;
  position: relative;
  transition: all 0.2s;
}

.toggle-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  background: #fff;
  border-radius: 50%;
  transition: all 0.2s;
}

.toggle-checkbox:checked + .toggle-switch {
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
}

.toggle-checkbox:checked + .toggle-switch::after {
  transform: translateX(20px);
}

.toggle-text {
  font-size: 13px;
  color: #64748b;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 14px 16px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  transition: all 0.2s;
}

.input-wrapper.focused {
  border-color: #0ea5e9;
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.1);
}

.input-wrapper.streaming {
  background: #fef2f2;
  border-color: #fecaca;
}

.input-textarea {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 15px;
  line-height: 1.6;
  resize: none;
  outline: none;
  min-height: 24px;
  max-height: 200px;
  color: #1e293b;
}

.input-textarea::placeholder {
  color: #94a3b8;
}

.send-btn {
  padding: 10px 20px;
  background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
  color: #fff;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
}

.send-btn:disabled {
  background: #e2e8f0;
  color: #94a3b8;
  cursor: not-allowed;
}

.stop-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: #fff;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.input-hint {
  margin-top: 10px;
  text-align: center;
}

.input-hint span {
  font-size: 12px;
  color: #94a3b8;
}

.streaming-hint {
  color: #ef4444 !important;
}
</style>