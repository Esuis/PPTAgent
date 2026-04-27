<template>
  <div class="home-container">
    <!-- 阶段1：初始空状态 - 居中输入界面 -->
    <div v-if="uiPhase === 'initial'" class="centered-layout">
      <div class="centered-content">
        <div class="centered-title-row">
          <svg class="centered-logo" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="6" y="4" width="28" height="36" rx="3" fill="#E8EDF3" stroke="#4A6A8A" stroke-width="2.5"/>
            <rect x="14" y="8" width="28" height="36" rx="3" fill="#fff" stroke="#4A6A8A" stroke-width="2.5"/>
            <line x1="19" y1="17" x2="37" y2="17" stroke="#B2C5E8" stroke-width="2" stroke-linecap="round"/>
            <line x1="19" y1="23" x2="33" y2="23" stroke="#B2C5E8" stroke-width="2" stroke-linecap="round"/>
            <line x1="19" y1="29" x2="30" y2="29" stroke="#B2C5E8" stroke-width="2" stroke-linecap="round"/>
            <rect x="19" y="33" width="12" height="5" rx="1.5" fill="#5B8BD4"/>
          </svg>
          <h1 class="centered-title">PPT生成平台</h1>
        </div>
        <p class="centered-subtitle">输入主题，AI 为你生成专业演示文稿</p>
        <ChatInput />
      </div>
    </div>

    <!-- 阶段2：有聊天但无预览 - 居中聊天+输入 -->
    <div v-else-if="uiPhase === 'chatting'" class="centered-layout">
      <div class="centered-chat-content">
        <div class="centered-chat-messages">
          <ChatMessages />
        </div>
        <div class="centered-chat-input">
          <ChatInput />
        </div>
      </div>
    </div>

    <!-- 阶段3：有预览 - 左右分栏 -->
    <div v-else class="split-layout">
      <!-- 标题栏 -->
      <div class="header-bar">
        <div class="header-title-row">
          <svg class="header-logo" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="6" y="4" width="28" height="36" rx="3" fill="#E8EDF3" stroke="#4A6A8A" stroke-width="2.5"/>
            <rect x="14" y="8" width="28" height="36" rx="3" fill="#fff" stroke="#4A6A8A" stroke-width="2.5"/>
            <line x1="19" y1="17" x2="37" y2="17" stroke="#B2C5E8" stroke-width="2" stroke-linecap="round"/>
            <line x1="19" y1="23" x2="33" y2="23" stroke="#B2C5E8" stroke-width="2" stroke-linecap="round"/>
            <line x1="19" y1="29" x2="30" y2="29" stroke="#B2C5E8" stroke-width="2" stroke-linecap="round"/>
            <rect x="19" y="33" width="12" height="5" rx="1.5" fill="#5B8BD4"/>
          </svg>
          <h2 class="header-title">PPT生成平台</h2>
        </div>
      </div>

      <!-- 左右分栏 -->
      <div class="main-content">
        <div class="left-panel">
          <div class="chat-area">
            <ChatMessages />
          </div>
          <div class="input-area">
            <ChatInput />
          </div>
        </div>

        <transition name="slide-preview">
          <div class="preview-area">
            <SlidePreview :previews="slidePreviews" :is-generating="isGenerating" />
          </div>
        </transition>
      </div>
    </div>

    <!-- 排队弹窗 -->
    <QueueDialog />
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatStore } from '@/stores/chat'
import ChatMessages from '@/components/ChatMessages.vue'
import ChatInput from '@/components/ChatInput.vue'
import SlidePreview from '@/components/SlidePreview.vue'
import QueueDialog from '@/components/QueueDialog.vue'

const chatStore = useChatStore()
const { slidePreviews, isGenerating, messages } = storeToRefs(chatStore)

// 三阶段渐进式UI状态
type UIPhase = 'initial' | 'chatting' | 'previewing'
const uiPhase = computed<UIPhase>(() => {
  if (messages.value.length === 0) return 'initial'
  if (slidePreviews.value.length === 0) return 'chatting'
  return 'previewing'
})

onMounted(() => {
  // 初始化用户ID
  chatStore.initUserId()
  // 加载模板列表
  chatStore.loadTemplates()
})
</script>

<style scoped>
/* ============ 全局容器 ============ */
.home-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}

/* ============ 阶段1 & 2：居中布局 ============ */
.centered-layout {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, #f5f5f5 0%, #e8ecf2 100%);
}

.centered-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 28px;
  width: 780px;
  max-width: 92vw;
}

.centered-content :deep(.input-box) {
  width: 100%;
  min-height: 33vh;
}

/* 阶段2：居中聊天内容 */
.centered-chat-content {
  display: flex;
  flex-direction: column;
  width: 780px;
  max-width: 92vw;
  height: 90vh;
  max-height: 90vh;
}

.centered-chat-messages {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.centered-chat-input {
  flex-shrink: 0;
  margin-top: 16px;
}

.centered-chat-input :deep(.input-box) {
  width: 100%;
}

/* ============ 标题样式 ============ */
.centered-title-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.centered-logo {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
}

.centered-title {
  font-size: 40px;
  font-weight: 700;
  color: #2c3e50;
  margin: 0;
  letter-spacing: 2px;
}

.centered-subtitle {
  font-size: 16px;
  color: #8899aa;
  margin: 0;
}

/* ============ 阶段3：左右分栏 ============ */
.split-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.header-bar {
  flex-shrink: 0;
  padding: 12px 24px;
  border-bottom: 1px solid #e8e8e8;
  background: #fff;
}

.header-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-logo {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}

.header-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #2c3e50;
}

.main-content {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 0;
  overflow: hidden;
}

.left-panel {
  flex: 0 0 50%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #F5F5F5;
  border-right: 1px solid #e8e8e8;
}

.chat-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.input-area {
  flex-shrink: 0;
  padding: 12px 16px;
}

.input-area :deep(.input-box) {
  box-shadow: none;
  border-radius: 10px;
}

.preview-area {
  flex: 0 0 50%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #F5F5F5;
}

/* ============ 预览区域过渡动画 ============ */
.slide-preview-enter-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.slide-preview-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.slide-preview-enter-from {
  opacity: 0;
  transform: translateX(40px);
}
.slide-preview-leave-to {
  opacity: 0;
  transform: translateX(40px);
}

/* ============ 响应式 ============ */
@media (max-width: 1200px) {
  .main-content {
    flex-direction: column;
  }

  .left-panel {
    flex: 0 0 100%;
  }

  .preview-area {
    flex: 0 0 100%;
    min-height: 400px;
    max-height: 500px;
  }
}

@media (max-width: 768px) {
  .centered-title {
    font-size: 28px;
  }

  .centered-subtitle {
    font-size: 14px;
  }

  .centered-content,
  .centered-chat-content {
    max-width: 96vw;
  }

  .header-title {
    font-size: 16px;
  }
}
</style>
