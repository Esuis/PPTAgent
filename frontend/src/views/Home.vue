<template>
  <div class="home-container">
    <!-- 标题区域 -->
    <div class="header">
      <h1 class="center-title">AI驱动的PPT智能生成平台</h1>
    </div>

    <!-- 中间主要内容区域 -->
    <div class="main-content">
      <!-- 左侧区域：聊天 + 输入 -->
      <div class="left-panel">
        <!-- 聊天区域 -->
        <div class="chat-area">
          <ChatMessages />
        </div>

        <!-- 输入和设置区域 -->
        <div class="input-area">
          <ChatInput />
        </div>
      </div>

      <!-- 右侧预览区域（常驻） -->
      <div class="preview-area">
        <SlidePreview :previews="slidePreviews" :is-generating="isGenerating" />
      </div>
    </div>

    <!-- 排队弹窗 -->
    <QueueDialog />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatStore } from '@/stores/chat'
import ChatMessages from '@/components/ChatMessages.vue'
import ChatInput from '@/components/ChatInput.vue'
import SlidePreview from '@/components/SlidePreview.vue'
import QueueDialog from '@/components/QueueDialog.vue'

const chatStore = useChatStore()
const { slidePreviews, isGenerating } = storeToRefs(chatStore)

onMounted(() => {
  // 初始化用户ID
  chatStore.initUserId()
  // 加载模板列表
  chatStore.loadTemplates()
})
</script>

<style scoped>
.home-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
  padding: 20px;
  gap: 20px;
}

.header {
  text-align: center;
  flex-shrink: 0;
}

.center-title {
  font-size: 32px;
  font-weight: bold;
  color: #2c3e50;
  margin: 0 0 10px 0;
}

.center-subtitle {
  font-size: 14px;
  color: #666;
  margin: 0;
  opacity: 0.8;
}

.main-content {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 20px;
}

.left-panel {
  flex: 0 0 50%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
  background: #F5F5F5;
  border-radius: 8px;
  padding: 16px;
}

.chat-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.preview-area {
  flex: 0 0 50%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #F5F5F5;
  border-radius: 8px;
  padding: 16px;
}

.input-area {
  flex-shrink: 0;
}

@media (max-width: 1200px) {
  .main-content {
    flex-direction: column;
  }

  .chat-area,
  .preview-area {
    flex: 0 0 100%;
  }

  .preview-area {
    min-height: 400px;
    max-height: 500px;
  }
}

@media (max-width: 768px) {
  .home-container {
    padding: 10px;
  }

  .center-title {
    font-size: 24px;
  }

  .main-content {
    gap: 10px;
  }
}
</style>
