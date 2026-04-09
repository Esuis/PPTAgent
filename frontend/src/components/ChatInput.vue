<template>
  <el-card class="input-card">
    <div class="input-container">
      <!-- 设置区域 -->
      <div class="settings-row">
        <div class="setting-item">
          <span class="setting-label">幻灯片页数：</span>
          <el-select v-model="settings.numPages" style="width: 120px" size="small">
            <el-option label="Auto" value="auto" />
            <el-option
              v-for="i in 30"
              :key="i"
              :label="`${i} 页`"
              :value="String(i)"
            />
          </el-select>
        </div>
      </div>

      <!-- 文件上传区域 -->
      <div class="file-upload-area">
        <el-upload
          v-model:file-list="fileList"
          :auto-upload="false"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          multiple
          :show-file-list="true"
          class="file-upload"
        >
          <el-button type="primary" :disabled="chatStore.isGenerating" size="small">
            📎 上传附件
          </el-button>
          <template #tip>
            <div class="el-upload__tip">
              支持上传多个文件（PDF、Word、Excel等）
            </div>
          </template>
        </el-upload>
      </div>

      <!-- 输入框和按钮 -->
      <div class="input-row">
        <el-input
          v-model="inputText"
          placeholder="输入你的指令，例如：制作一个关于AI发展的PPT..."
          :disabled="chatStore.isGenerating"
          @keyup.enter="handleSend"
          class="message-input"
        />
        
        <el-button
          type="primary"
          :loading="chatStore.isGenerating"
          :disabled="!inputText && fileList.length === 0"
          @click="handleSend"
          class="send-button"
        >
          {{ chatStore.isGenerating ? '生成中...' : '发送' }}
        </el-button>

        <el-button
          type="success"
          :disabled="!chatStore.downloadUrl || chatStore.isGenerating"
          @click="handleDownload"
          class="download-button"
        >
          📥 下载PPT
          <span v-if="!chatStore.downloadUrl" class="button-hint">（等待生成完成）</span>
          <span v-else-if="chatStore.isGenerating" class="button-hint">（生成中...）</span>
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import type { UploadFile } from 'element-plus'
import { ElMessage } from 'element-plus'

const chatStore = useChatStore()
const inputText = ref('')
const fileList = ref<UploadFile[]>([])
const uploadedFiles = ref<File[]>([])

// 设置项
const settings = ref({
  numPages: 'auto',
  convertType: 'freeform', // 固定为自由生成
  template: 'auto',
})

function handleFileChange(file: UploadFile) {
  if (file.raw) {
    uploadedFiles.value.push(file.raw)
  }
}

function handleFileRemove(file: UploadFile) {
  const index = uploadedFiles.value.findIndex((f) => f.name === file.name)
  if (index !== -1) {
    uploadedFiles.value.splice(index, 1)
  }
}

async function handleSend() {
  await chatStore.sendMessage(inputText.value, uploadedFiles.value, settings.value)
  
  // 清空输入
  if (!chatStore.isGenerating) {
    inputText.value = ''
    fileList.value = []
    uploadedFiles.value = []
  }
}

function handleDownload() {
  if (chatStore.downloadUrl) {
    window.open(chatStore.downloadUrl, '_blank')
  } else {
    ElMessage.warning('暂无可下载的文件')
  }
}
</script>

<style scoped>
.input-card {
  margin-top: 0;
}

.input-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.settings-row {
  display: flex;
  gap: 16px;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 1px solid #e0e0e0;
}

.setting-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.setting-label {
  font-size: 14px;
  color: #606266;
  white-space: nowrap;
}

.file-upload-area {
  border-bottom: 1px solid #e0e0e0;
  padding-bottom: 16px;
}

.file-upload {
  width: 100%;
}

.el-upload__tip {
  font-size: 12px;
  color: #999;
  margin-top: 8px;
}

.input-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.message-input {
  flex: 1;
}

.send-button,
.download-button {
  flex-shrink: 0;
}

.button-hint {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}

:deep(.el-upload-list) {
  margin-top: 8px;
}
</style>
