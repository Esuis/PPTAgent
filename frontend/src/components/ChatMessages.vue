<template>
  <el-card class="chat-card">
    <div ref="chatContainer" class="chat-container">
      <!-- 首次进入聊天时不会是空状态，由Home.vue的初始界面处理 -->
      <div v-if="chatStore.messages.length === 0" class="empty-state">
        <el-empty description="开始对话，生成你的PPT吧！" />
      </div>

      <div v-else class="messages">
        <TransitionGroup name="msg-slide">
          <div
            v-for="(message, index) in chatStore.messages"
            :key="index"
            class="message"
            :class="[
              message.role,
              {
                'streaming': isStreaming(index),
              }
            ]"
          >
            <!-- ======== 用户消息 ======== -->
            <template v-if="message.role === 'user'">
              <div class="message-content user-content">
                <div v-html="renderMarkdown(message.content)" class="markdown-body"></div>
              </div>
            </template>

            <!-- ======== 助手消息（单框合并） ======== -->
            <template v-else>
              <!-- 头部 -->
              <div class="message-header">
                <img
                  :src="getRoleIcon(message.role)"
                  :alt="getRoleName(message.role)"
                  class="role-avatar"
                />
                <span class="role-name">{{ getRoleName(message.role) }}</span>
                <span v-if="isStreaming(index)" class="streaming-indicator"></span>
              </div>

              <!-- 过程步骤区域（可折叠） -->
              <div
                v-if="message.steps && message.steps.length > 0"
                class="steps-section"
                :class="{ 'steps-collapsed': isStepsCollapsed(index) }"
              >
                <div class="steps-toggle" @click="toggleStepsCollapse(index)">
                  <span class="steps-toggle-icon">{{ isStepsCollapsed(index) ? '▶' : '▼' }}</span>
                  <span class="steps-label">思考过程</span>
                  <span class="steps-count">{{ message.steps.length }}步</span>
                  <span v-if="isStreaming(index)" class="streaming-indicator small"></span>
                </div>
                <div class="steps-body">
                  <div
                    v-for="(step, sIdx) in message.steps"
                    :key="sIdx"
                    class="step-item"
                  >
                    <span class="step-dot"></span>
                    <span class="step-text" v-html="renderMarkdown(step.content)"></span>
                  </div>
                </div>
              </div>

              <!-- 主体内容 -->
              <div
                class="message-content assistant-content sliding-window"
                :class="{ 'window-streaming': isStreaming(index) }"
              >
                <div v-if="message.content" v-html="renderMarkdown(message.content)" class="markdown-body"></div>
                <div v-else-if="isStreaming(index)" class="thinking-placeholder">
                  <span class="thinking-dots">正在思考</span>
                  <span class="thinking-anim">...</span>
                </div>
                <!-- 流式渐变遮罩 -->
                <div v-if="isStreaming(index)" class="sliding-gradient-mask"></div>
              </div>
            </template>
          </div>
        </TransitionGroup>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, reactive } from 'vue'
import { useChatStore } from '@/stores/chat'
import MarkdownIt from 'markdown-it'
import assistantIcon from '@/assets/assistant.png'
import userIcon from '@/assets/user.png'

const chatStore = useChatStore()
const chatContainer = ref<HTMLElement | null>(null)

// 折叠状态管理（按消息index记录）
const collapsedStepsMap = reactive(new Set<number>())

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

// 判断消息是否正在流式生成
function isStreaming(index: number): boolean {
  if (!chatStore.isGenerating) return false
  const msg = chatStore.messages[index]
  if (!msg) return false
  // assistant消息且是最后一条时标记为流式
  if (msg.role === 'assistant' && index === chatStore.messages.length - 1) {
    return true
  }
  return false
}

// 过程步骤区域折叠/展开
function isStepsCollapsed(index: number): boolean {
  return collapsedStepsMap.has(index)
}

function toggleStepsCollapse(index: number) {
  if (collapsedStepsMap.has(index)) {
    collapsedStepsMap.delete(index)
  } else {
    collapsedStepsMap.add(index)
  }
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

/* ============ 消息基础样式 ============ */
.message {
  padding: 12px 16px;
  border-radius: 8px;
  max-width: 90%;
  position: relative;
}

.message.user {
  align-self: flex-end;
  background: #B2C5E8;
  border: 1px solid #9AB3D8;
}

.message.assistant {
  align-self: flex-start;
  background: #FFFFFF;
  border: 1px solid #e0e0e0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

/* ============ 滑动窗口进入动画 (TransitionGroup) ============ */
.msg-slide-enter-active {
  transition:
    max-height 0.5s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 0.4s ease,
    transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.msg-slide-enter-from {
  opacity: 0;
  transform: translateY(-12px);
  max-height: 0 !important;
}

.msg-slide-enter-to {
  opacity: 1;
  transform: translateY(0);
  max-height: 800px;
}

.msg-slide-leave-active {
  transition: opacity 0.2s ease;
}

.msg-slide-leave-to {
  opacity: 0;
}

.msg-slide-move {
  transition: transform 0.3s ease;
}

/* ============ 流式生成状态 ============ */
.message.streaming {
  animation: subtle-breathe 2s ease-in-out infinite;
}

@keyframes subtle-breathe {
  0%, 100% { box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08); }
  50% { box-shadow: 0 2px 8px rgba(64, 158, 255, 0.12); }
}

/* ============ 用户消息内容 ============ */
.user-content {
  line-height: 1.6;
}

/* ============ 助手消息头部 ============ */
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

/* ============ 流式指示器（头部脉冲点） ============ */
.streaming-indicator {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #409eff;
  margin-left: 6px;
  animation: pulse-dot 1.2s ease-in-out infinite;
  vertical-align: middle;
}

.streaming-indicator.small {
  width: 5px;
  height: 5px;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.3; transform: scale(0.7); }
}

/* ============ 过程步骤区域（助手框内） ============ */
.steps-section {
  margin-bottom: 8px;
  border: 1px solid #eef2f7;
  border-radius: 6px;
  overflow: hidden;
  background: #fafbfc;
}

.steps-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  cursor: pointer;
  user-select: none;
  font-size: 12px;
  color: #8899aa;
  transition: background-color 0.15s;
}

.steps-toggle:hover {
  background: #f0f3f7;
}

.steps-toggle-icon {
  font-size: 9px;
  color: #b2c5e8;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.steps-label {
  font-weight: 500;
  color: #6a7a8a;
}

.steps-count {
  background: #eef2f7;
  color: #8899aa;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 11px;
}

/* 折叠状态：隐藏步骤内容 */
.steps-section.steps-collapsed .steps-body {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  transition: max-height 0.3s ease, opacity 0.2s ease;
}

/* 展开状态：显示步骤内容 */
.steps-section:not(.steps-collapsed) .steps-body {
  max-height: 600px;
  opacity: 1;
  transition: max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease 0.1s;
}

/* 单个步骤条目 */
.step-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 10px 4px 14px;
  font-size: 13px;
  color: #5a6a7a;
  line-height: 1.5;
}

.step-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #b2c5e8;
  flex-shrink: 0;
  margin-top: 6px;
}

.step-text {
  flex: 1;
  min-width: 0;
}

.step-text :deep(p) {
  margin: 0;
}

/* ============ 滑动窗口内容区（助手主体） ============ */
.assistant-content {
  line-height: 1.6;
  position: relative;
  overflow: hidden;
}

/* 流式渐变遮罩 */
.sliding-window.window-streaming {
  padding-bottom: 24px;
}

.sliding-gradient-mask {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 48px;
  background: linear-gradient(
    to bottom,
    rgba(255, 255, 255, 0) 0%,
    rgba(255, 255, 255, 0.6) 40%,
    rgba(255, 255, 255, 0.95) 100%
  );
  pointer-events: none;
  z-index: 1;
}

/* 渐变遮罩上的微光扫描线 */
.sliding-gradient-mask::after {
  content: '';
  position: absolute;
  bottom: 8px;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    #409eff 50%,
    transparent 100%
  );
  animation: shimmer-line 2s ease-in-out infinite;
}

@keyframes shimmer-line {
  0% { transform: translateX(-100%); opacity: 0; }
  30% { opacity: 1; }
  70% { opacity: 1; }
  100% { transform: translateX(100%); opacity: 0; }
}

/* 正在思考占位 */
.thinking-placeholder {
  color: #b0b8c4;
  font-size: 14px;
  padding: 4px 0;
}

.thinking-dots {
  margin-right: 2px;
}

.thinking-anim {
  display: inline-block;
  animation: thinking-dots 1.4s steps(3, end) infinite;
  width: 1.2em;
  overflow: hidden;
}

@keyframes thinking-dots {
  0%   { content: ''; width: 0; }
  33%  { width: 0.4em; }
  66%  { width: 0.8em; }
  100% { width: 1.2em; }
}

/* ============ Markdown渲染 ============ */
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

/* ============ 滚动条样式 ============ */
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
