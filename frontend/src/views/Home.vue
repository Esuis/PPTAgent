<template>
  <div class="home-container">
    <!-- 标题区域 -->
    <div class="header">
      <h1 class="center-title">DeepPresenter</h1>
      <p class="center-subtitle">AI驱动的PPT智能生成平台</p>
    </div>

    <!-- 中间聊天区域 -->
    <div class="chat-area">
      <ChatMessages />
    </div>

    <!-- 底部输入和设置区域 -->
    <div class="input-area">
      <ChatInput />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import ChatMessages from '@/components/ChatMessages.vue'
import ChatInput from '@/components/ChatInput.vue'

const chatStore = useChatStore()

onMounted(() => {
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

.chat-area {
  flex: 1;
  min-height: 0;
}

.input-area {
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .home-container {
    padding: 10px;
  }
  
  .center-title {
    font-size: 24px;
  }
}
</style>
