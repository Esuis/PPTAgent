<template>
  <div class="slide-preview-container">
    <div class="preview-header">
      <h3>实时预览</h3>
      <div class="header-right">
        <span class="slide-count">已生成 {{ previews.length }} 页</span>
        <button
          class="download-icon-btn"
          :disabled="!downloadUrl || isGenerating"
          @click="handleDownload"
          title="下载PPT"
        >
          <img :src="downloadIcon" alt="下载" class="download-icon-img" />
        </button>
      </div>
    </div>

    <!-- 主预览区域 - 上下滚动 -->
    <div class="preview-main" ref="scrollContainerRef">
      <!-- 空状态或正在生成 -->
      <div v-if="previews.length === 0" class="empty-state">
        <el-icon :size="48" color="#409eff" class="loading-icon">
          <Loading />
        </el-icon>
        <p class="generating-text">等待生成中</p>
      </div>

      <!-- 幻灯片列表 -->
      <div v-else class="slide-list">
        <div
          v-for="(preview, index) in previews"
          :key="`slide-${index}-${preview.number}`"
          class="slide-card"
        >
          <!-- 页码标签 -->
          <div class="slide-label">第 {{ preview.number }} 页</div>

          <!-- Design模式 - HTML预览 -->
          <div v-if="preview.type === 'html'" class="slide-iframe-wrapper">
            <div class="slide-iframe-scaler" :style="iframeScalerStyle">
              <iframe
                :srcdoc="preview.content"
                sandbox="allow-same-origin"
                class="preview-iframe"
              ></iframe>
            </div>
          </div>

          <!-- PPTAgent模式 - 图片预览 -->
          <img
            v-else-if="preview.type === 'image'"
            :src="preview.content"
            :alt="`第 ${preview.number} 页`"
            class="preview-image"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import type { SlidePreview } from '@/types'
import downloadIcon from '@/assets/download.png'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()
const downloadUrl = computed(() => chatStore.downloadUrl)

const props = defineProps<{
  previews: SlidePreview[]
  isGenerating?: boolean
}>()

const scrollContainerRef = ref<HTMLElement | null>(null)
const scaleFactor = ref(1)

// 计算缩放比例（基于容器宽度）
function calculateScale() {
  if (!scrollContainerRef.value) return

  const container = scrollContainerRef.value
  // 减去 slide-list 的 padding (20px * 2)
  const availableWidth = container.clientWidth - 40

  const slideWidth = 1280
  const scale = availableWidth / slideWidth

  scaleFactor.value = scale
}

const iframeScalerStyle = computed(() => ({
  width: '1280px',
  height: '720px',
  transform: `scale(${scaleFactor.value})`,
  transformOrigin: 'top left'
}))

// 当预览列表变化时重新计算尺寸
watch(() => props.previews.length, () => {
  nextTick(() => {
    setTimeout(() => calculateScale(), 100)
  })
})

// 监听窗口大小变化
let resizeTimer: number | null = null
function debouncedCalculate() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = window.setTimeout(() => {
    calculateScale()
  }, 150)
}

onMounted(() => {
  setTimeout(() => calculateScale(), 200)
  window.addEventListener('resize', debouncedCalculate)
})

onUnmounted(() => {
  window.removeEventListener('resize', debouncedCalculate)
  if (resizeTimer) clearTimeout(resizeTimer)
})

function handleDownload() {
  if (downloadUrl.value) {
    window.open(downloadUrl.value, '_blank')
  }
}
</script>

<style scoped>
.slide-preview-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.preview-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fafafa;
  flex-shrink: 0;
}

.preview-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #2c3e50;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.slide-count {
  font-size: 12px;
  color: #666;
  background: #e8e8e8;
  padding: 4px 12px;
  border-radius: 12px;
}

.download-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s;
  padding: 0;
}

.download-icon-btn:hover:not(:disabled) {
  background-color: #e0e0e0;
}

.download-icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.download-icon-img {
  width: 20px;
  height: 20px;
}

/* ============ 主预览区域 - 滚动容器 ============ */
.preview-main {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: #f5f5f5;
}

.preview-main::-webkit-scrollbar {
  width: 8px;
}

.preview-main::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.preview-main::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.preview-main::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  color: #999;
}

.empty-state p {
  margin-top: 12px;
  font-size: 14px;
}

.loading-icon {
  animation: rotate 2s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.generating-text {
  animation: blink 1.5s ease-in-out infinite;
  color: #409eff;
  font-weight: 500;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ============ 幻灯片列表 ============ */
.slide-list {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.slide-card {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.slide-label {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  color: #666;
  background: #fafafa;
  border-bottom: 1px solid #f0f0f0;
}

/* HTML幻灯片预览 */
.slide-iframe-wrapper {
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  position: relative;
  background: #fff;
}

.slide-iframe-scaler {
  position: absolute;
  top: 0;
  left: 0;
  width: 1280px;
  height: 720px;
  transform-origin: top left;
}

.preview-iframe {
  width: 1280px;
  height: 720px;
  border: none;
  background: #fff;
}

/* 图片幻灯片预览 */
.preview-image {
  width: 100%;
  display: block;
}

/* ============ 响应式设计 ============ */
@media (max-width: 768px) {
  .preview-header {
    padding: 12px 16px;
  }

  .preview-header h3 {
    font-size: 14px;
  }

  .slide-list {
    padding: 12px;
    gap: 12px;
  }
}
</style>
