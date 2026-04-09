<template>
  <el-card class="chat-card">
    <div ref="chatContainer" class="chat-container">
      <div v-if="chatStore.messages.length === 0" class="empty-state">
        <el-empty description="开始对话，生成你的PPT吧！" />
      </div>

      <div v-else class="messages">
        <div
          v-for="(message, index) in chatStore.messages"
          :key="index"
          class="message"
          :class="message.role"
        >
          <div class="message-header">
            <span class="role-icon">{{ getRoleEmoji(message.role) }}</span>
            <span class="role-name">{{ getRoleName(message.role) }}</span>
          </div>
          <div class="message-content">
            <div v-html="renderMarkdown(message.content)" class="markdown-body"></div>
          </div>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'
import MarkdownIt from 'markdown-it'

const chatStore = useChatStore()
const chatContainer = ref<HTMLElement | null>(null)

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: true,
})

function getRoleEmoji(role: string): string {
  const emojis: Record<string, string> = {
    user: '👤',
    assistant: '🤖',
    system: '⚙️',
    tool: '📝',
  }
  return emojis[role] || '💬'
}

function getRoleName(role: string): string {
  const names: Record<string, string> = {
    user: 'User',
    assistant: 'Assistant',
    system: 'System',
    tool: 'Tool',
  }
  return names[role] || role
}

function renderMarkdown(content: string): string {
  if (!content) return ''
  return md.render(content)
}

// 自动滚动到底部
watch(
  () => chatStore.messages,
  async () => {
    await nextTick()
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  },
  { deep: true }
)
</script>

<style scoped>
.chat-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  min-height: 0;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.messages {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message {
  padding: 12px 16px;
  border-radius: 8px;
  max-width: 90%;
}

.message.user {
  align-self: flex-end;
  background: #e3f2fd;
  border: 1px solid #bbdefb;
}

.message.assistant,
.message.system,
.message.tool {
  align-self: flex-start;
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #666;
}

.role-icon {
  font-size: 16px;
}

.role-name {
  font-weight: bold;
}

.message-content {
  line-height: 1.6;
}

.markdown-body {
  word-wrap: break-word;
}

.markdown-body :deep(pre) {
  background: #f6f8fa;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}

.markdown-body :deep(code) {
  background: #f6f8fa;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.9em;
}

.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
}

/* 滚动条样式 */
.chat-container::-webkit-scrollbar {
  width: 8px;
}

.chat-container::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.chat-container::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.chat-container::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>
