<template>
  <el-card class="chat-card">
    <div ref="chatContainer" class="chat-container">
      <!-- 首次进入聊天时不会是空状态，由Home.vue的初始界面处理 -->
      <div v-if="chatStore.messages.length === 0" class="empty-state">
        <el-empty description="开始对话，生成你的PPT吧！" />
      </div>

      <div v-else class="messages">
        <div
          v-for="(message, index) in chatStore.messages"
          :key="index"
          class="message"
          :class="[
            message.role,
            { 'process-step': message.isProcessStep }
          ]"
        >
          <div v-if="!message.isProcessStep" class="message-header">
            <img
              :src="getRoleIcon(message.role)"
              :alt="getRoleName(message.role)"
              class="role-avatar"
            />
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
import assistantIcon from '@/assets/assistant.png'
import userIcon from '@/assets/user.png'

const chatStore = useChatStore()
const chatContainer = ref<HTMLElement | null>(null)

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: true,
})

function getRoleIcon(role: string): string {
  const icons: Record<string, string> = {
    user: userIcon,
    assistant: assistantIcon,
    system: assistantIcon,
    tool: assistantIcon,
  }
  return icons[role] || assistantIcon
}

function getRoleName(role: string): string {
  const names: Record<string, string> = {
    user: '用户',
    assistant: '助手',
    system: '系统',
    tool: '工具',
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
  background: #F5F5F5;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.chat-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
  background: #F5F5F5;
  min-height: 0;
  border-radius: 8px;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  min-height: 0;
  background: #F5F5F5;
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
  background: #B2C5E8;
  border: 1px solid #9AB3D8;
}

.message.assistant,
.message.system,
.message.tool {
  align-self: flex-start;
  background: #FFFFFF;
  border: 1px solid #e0e0e0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

/* 过程步骤消息样式 - 更紧凑的独立气泡 */
.message.process-step {
  align-self: flex-start;
  background: #FFFFFF;
  border: 1px solid #e8ecf0;
  border-left: 3px solid #B2C5E8;
  border-radius: 0 8px 8px 0;
  padding: 6px 12px;
  max-width: 85%;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.message.process-step .markdown-body {
  font-size: 13px;
  color: #5a6a7a;
}

.message.process-step .markdown-body p {
  margin: 0;
  line-height: 1.5;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #666;
}

.role-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
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
