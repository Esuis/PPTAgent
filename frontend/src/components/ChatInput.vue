<template>
  <el-card class="input-card">
    <div class="input-container">
      <!-- 设置区域 -->
      <div class="settings-row">
        <el-select v-model="settings.numPages" style="width: 160px" size="small">
          <el-option label="自动页数（Auto）" value="auto" />
          <el-option
            v-for="i in 30"
            :key="i"
            :label="`${i} 页`"
            :value="String(i)"
          />
        </el-select>
      </div>

      <!-- 输入框 -->
      <div class="input-row">
        <el-input
          v-model="inputText"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          placeholder="请输入PPT主题，添加具体要求和参考资料。例如，基于现有知识介绍交通银行，生成10页ppt，禁止联网"
          :disabled="chatStore.isGenerating"
          @keyup.enter="handleSend"
          class="message-input"
        />
      </div>

      <!-- 上传附件与发送 -->
      <div class="action-row">
        <el-upload
          v-model:file-list="fileList"
          :auto-upload="false"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          multiple
          :show-file-list="true"
          class="file-upload"
        >
          <div class="upload-hover-wrapper" :class="{ disabled: chatStore.isGenerating }">
            <img :src="uploadIcon" alt="上传" class="icon-img" />
            <span class="upload-label">上传附件</span>
          </div>
        </el-upload>

        <el-button
          type="primary"
          :loading="chatStore.isGenerating"
          :disabled="!inputText && fileList.length === 0"
          @click="handleSend"
          class="send-button"
        >
          {{ chatStore.isGenerating ? '生成中...' : '发送' }}
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import type { UploadFile } from 'element-plus'
import uploadIcon from '@/assets/upload.png'

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
}

.input-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.message-input {
  flex: 1;
}

.action-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.upload-hover-wrapper {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.upload-hover-wrapper:hover:not(.disabled) {
  background-color: #e0e0e0;
}

.upload-hover-wrapper.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-label {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
}

.file-upload {
  display: inline-flex;
}

.send-button {
  flex-shrink: 0;
}

:deep(.el-upload-list) {
  margin-top: 8px;
}

.icon-img {
  width: 20px;
  height: 20px;
}
</style>
