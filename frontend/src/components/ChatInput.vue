<template>
  <div class="input-box">
    <!-- 文本输入区 -->
    <div class="input-field-row">
      <textarea
        v-model="inputText"
        :placeholder="'请输入PPT主题，添加具体要求和参考资料'"
        :disabled="chatStore.isGenerating"
        @keydown.enter.exact="handleSend"
        class="input-textarea"
        maxlength="2000"
      ></textarea>
    </div>

    <!-- 附件文件列表 -->
    <div v-if="fileList.length > 0" class="file-list">
      <div v-for="(file, idx) in fileList" :key="file.uid" class="file-item">
        <img :src="uploadIcon" alt="附件" class="file-icon" />
        <span class="file-name">{{ file.name }}</span>
        <span class="file-remove" @click="removeFile(idx)">✕</span>
      </div>
    </div>

    <!-- 底部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <!-- 页数选择 -->
        <el-select v-model="settings.numPages" size="small" class="page-select">
          <el-option label="自动页数" value="auto" />
          <el-option
            v-for="i in 30"
            :key="i"
            :label="`${i}页`"
            :value="String(i)"
          />
        </el-select>
      </div>

      <div class="toolbar-right">
        <!-- 上传附件 -->
        <el-upload
          v-model:file-list="fileList"
          :auto-upload="false"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          :limit="1"
          :on-exceed="handleExceed"
          :before-upload="beforeUpload"
          :show-file-list="false"
          accept=".txt,.md,.docx,.pdf"
          class="upload-btn"
        >
          <div class="upload-trigger" :class="{ disabled: chatStore.isGenerating }">
            <img :src="uploadIcon" alt="上传" class="toolbar-icon" />
            <span class="upload-label">上传附件</span>
          </div>
        </el-upload>

        <!-- 发送按钮 -->
        <button
          class="send-btn"
          :class="{ disabled: (!inputText && fileList.length === 0) || chatStore.isGenerating }"
          :disabled="(!inputText && fileList.length === 0) || chatStore.isGenerating"
          @click="handleSend"
        >
          <svg v-if="!chatStore.isGenerating" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="19" x2="12" y2="5"></line>
            <polyline points="5 12 12 5 19 12"></polyline>
          </svg>
          <span v-else class="loading-dot">●</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import { ElMessage } from 'element-plus'
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

const MAX_FILE_SIZE = 3 * 1024 * 1024 // 3MB
const ALLOWED_EXTENSIONS = ['.txt', '.md', '.docx', '.pdf']

function isAllowedFile(file: File): boolean {
  const fileName = file.name.toLowerCase()
  return ALLOWED_EXTENSIONS.some((ext) => fileName.endsWith(ext))
}

function beforeUpload(file: File) {
  if (!isAllowedFile(file)) {
    ElMessage.error('仅支持上传 .txt、.md、.docx、.pdf 格式的文件')
    return false
  }
  if (file.size > MAX_FILE_SIZE) {
    ElMessage.error('附件大小不能超过3MB')
    return false
  }
  return true
}

function handleExceed() {
  ElMessage.warning('最多只能上传1个附件')
}

function handleFileChange(file: UploadFile) {
  if (file.raw) {
    if (!isAllowedFile(file.raw)) {
      // 移除不支持的文件
      const index = fileList.value.findIndex((f) => f.uid === file.uid)
      if (index !== -1) {
        fileList.value.splice(index, 1)
      }
      ElMessage.error('仅支持上传 .txt、.md、.docx、.pdf 格式的文件')
      return
    }
    if (file.raw.size > MAX_FILE_SIZE) {
      // 移除超限文件
      const index = fileList.value.findIndex((f) => f.uid === file.uid)
      if (index !== -1) {
        fileList.value.splice(index, 1)
      }
      ElMessage.error('附件大小不能超过3MB')
      return
    }
    uploadedFiles.value.push(file.raw)
  }
}

function handleFileRemove(file: UploadFile) {
  const index = uploadedFiles.value.findIndex((f) => f.name === file.name)
  if (index !== -1) {
    uploadedFiles.value.splice(index, 1)
  }
}

function removeFile(index: number) {
  const removed = fileList.value.splice(index, 1)[0]
  if (removed) {
    const uploadIdx = uploadedFiles.value.findIndex((f) => f.name === removed.name)
    if (uploadIdx !== -1) {
      uploadedFiles.value.splice(uploadIdx, 1)
    }
  }
}

async function handleSend(e?: Event) {
  // 阻止默认行为（textarea的enter换行）
  if (e) e.preventDefault()
  
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
/* ============ 输入框整体容器 ============ */
.input-box {
  display: flex;
  flex-direction: column;
  border: 1px solid #dcdfe6;
  border-radius: 14px;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input-box:focus-within {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.15), 0 4px 24px rgba(0, 0, 0, 0.12);
}

/* ============ 文本输入区 ============ */
.input-field-row {
  flex: 1;
  display: flex;
  min-height: 0;
}

.input-textarea {
  flex: 1;
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  padding: 18px 20px;
  font-size: 16px;
  line-height: 1.8;
  color: #303133;
  background: transparent;
  font-family: inherit;
}

.input-textarea::placeholder {
  color: #c0c4cc;
}

/* ============ 附件文件列表 ============ */
.file-list {
  padding: 0 20px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
}

.file-icon {
  width: 14px;
  height: 14px;
}

.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-remove {
  cursor: pointer;
  color: #c0c4cc;
  font-size: 12px;
  padding: 0 4px;
}

.file-remove:hover {
  color: #f56c6c;
}

/* ============ 底部工具栏 ============ */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 页数选择 - 内嵌风格 */
.page-select {
  width: 110px;
}

.page-select :deep(.el-input__wrapper) {
  box-shadow: none !important;
  background: #f5f7fa;
  border-radius: 6px;
}

.page-select :deep(.el-input__wrapper:hover) {
  background: #eef1f5;
}

/* 上传按钮 */
.upload-btn {
  display: inline-flex;
}

.upload-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 44px;
  padding: 0 20px;
  border-radius: 8px;
  background: #f5f7fa;
  cursor: pointer;
  transition: background-color 0.2s;
}

.upload-trigger:hover:not(.disabled) {
  background: #eef1f5;
}

.upload-trigger.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-label {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
}

.toolbar-icon {
  width: 20px;
  height: 20px;
}

/* ============ 发送按钮 ============ */
.send-btn {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  background: #409eff;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.2s, transform 0.15s;
  flex-shrink: 0;
}

.send-btn:hover:not(.disabled) {
  background: #66b1ff;
  transform: scale(1.05);
}

.send-btn.disabled {
  background: #c0c4cc;
  cursor: not-allowed;
}

.loading-dot {
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
