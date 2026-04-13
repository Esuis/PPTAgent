<template>
  <div class="slide-preview-container">
    <div class="preview-header">
      <h3>实时预览</h3>
      <span class="slide-count">已生成 {{ previews.length }} 页</span>
    </div>

    <!-- 缩略图导航 -->
    <div class="thumbnail-nav" v-if="previews.length > 0">
      <div
        v-for="(preview, index) in previews"
        :key="`thumb-${index}-${preview.number}`"
        :class="['thumbnail-item', { active: currentIndex === index }]"
        @click="goToSlide(index)"
      >
        <span class="thumb-number">{{ preview.number }}</span>
      </div>
    </div>

    <!-- 主预览区域 -->
    <div class="preview-main">
      <!-- 空状态或正在生成 -->
      <div v-if="previews.length === 0" class="empty-state">
        <el-icon :size="48" color="#409eff" class="loading-icon">
          <Loading />
        </el-icon>
        <p class="generating-text">等待生成中</p>
      </div>

      <div v-else-if="currentPreview" class="preview-content">
        <!-- Design模式 - HTML预览 -->
        <div v-if="currentPreview.type === 'html'" ref="wrapperRef" class="iframe-wrapper">
          <div class="iframe-scaler" :style="{
            width: '1280px',
            height: '720px',
            transform: `scale(${scaleFactor})`,
            transformOrigin: 'center center'
          }">
            <iframe
              ref="iframeRef"
              :srcdoc="currentPreview.content"
              :sandbox="'allow-same-origin'"
              class="preview-iframe"
              :key="currentIndex"
            ></iframe>
          </div>
        </div>

        <!-- PPTAgent模式 - 图片预览 -->
        <img
          v-else-if="currentPreview.type === 'image'"
          :src="currentPreview.content"
          :alt="`第 ${currentPreview.number} 页`"
          class="preview-image"
          :key="currentIndex"
        />

        <!-- 页码指示器 -->
        <div class="page-indicator">
          {{ currentIndex + 1 }} / {{ previews.length }}
        </div>
      </div>
    </div>

    <!-- 控制按钮 -->
    <div class="preview-controls" v-if="previews.length > 0">
      <el-button-group>
        <el-button
          :disabled="currentIndex === 0"
          @click="goToPrev"
          :icon="ArrowLeft"
        >
          上一页
        </el-button>
        <el-button
          :disabled="currentIndex === previews.length - 1"
          @click="goToNext"
          :icon="ArrowRight"
        >
          下一页
        </el-button>
      </el-button-group>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Loading, ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import type { SlidePreview } from '@/types'

const props = defineProps<{
  previews: SlidePreview[]
  isGenerating?: boolean
}>()

const currentIndex = ref(0)
const iframeRef = ref<HTMLIFrameElement | null>(null)
const wrapperRef = ref<HTMLDivElement | null>(null)
const scaleFactor = ref(1)  // 缩放比例

const currentPreview = computed(() => {
  if (props.previews.length === 0) return null
  return props.previews[currentIndex.value]
})

// 计算缩放比例
function calculateIframeSize() {
  if (!wrapperRef.value) return
  
  const wrapper = wrapperRef.value
  // wrapper的clientWidth已经不包含自身的padding: 10px
  // 但preview-main有padding: 20px，所以wrapper的clientWidth已经是可用空间
  const availableWidth = wrapper.clientWidth
  const availableHeight = wrapper.clientHeight
  
  // HTML幻灯片的固定尺寸
  const slideWidth = 1280
  const slideHeight = 720
  
  // 计算缩放比例（保持宽高比）
  const scaleX = availableWidth / slideWidth
  const scaleY = availableHeight / slideHeight
  const scale = Math.min(scaleX, scaleY)
  
  // 调试信息
  console.log('📏 计算缩放:', {
    wrapperClientWidth: wrapper.clientWidth,
    wrapperClientHeight: wrapper.clientHeight,
    availableWidth,
    availableHeight,
    slideWidth,
    slideHeight,
    scaleX: scaleX.toFixed(3),
    scaleY: scaleY.toFixed(3),
    scale: scale.toFixed(3)
  })
  
  scaleFactor.value = scale
}

// 当预览列表变化时，确保currentIndex有效
watch(() => props.previews.length, (newLength) => {
  if (newLength === 0) {
    currentIndex.value = 0
  } else if (currentIndex.value >= newLength) {
    currentIndex.value = newLength - 1
  }
  // 预览变化后重新计算尺寸
  nextTick(() => {
    setTimeout(() => calculateIframeSize(), 100)
  })
})

// 监听窗口大小变化
let resizeTimer: number | null = null
function debouncedCalculate() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = window.setTimeout(() => {
    calculateIframeSize()
  }, 150)
}

onMounted(() => {
  // 延迟计算，等待DOM渲染完成
  setTimeout(() => calculateIframeSize(), 200)
  window.addEventListener('resize', debouncedCalculate)
})

onUnmounted(() => {
  window.removeEventListener('resize', debouncedCalculate)
  if (resizeTimer) clearTimeout(resizeTimer)
})

// 上一页
function goToPrev() {
  if (currentIndex.value > 0) {
    currentIndex.value--
  }
}

// 下一页
function goToNext() {
  if (currentIndex.value < props.previews.length - 1) {
    currentIndex.value++
  }
}

// 跳转到指定页
function goToSlide(index: number) {
  currentIndex.value = index
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
}

.preview-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #2c3e50;
}

.slide-count {
  font-size: 12px;
  color: #666;
  background: #e8e8e8;
  padding: 4px 12px;
  border-radius: 12px;
}

.thumbnail-nav {
  padding: 12px;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  flex-direction: row;
  gap: 8px;
  overflow-x: auto;
  background: #fafafa;
}

.thumbnail-nav::-webkit-scrollbar {
  height: 6px;
}

.thumbnail-nav::-webkit-scrollbar-thumb {
  background: #ccc;
  border-radius: 3px;
}

.thumbnail-item {
  width: 40px;
  height: 40px;
  border: 2px solid #e8e8e8;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  background: #fff;
  flex-shrink: 0;
}

.thumbnail-item:hover {
  border-color: #409eff;
  transform: scale(1.05);
}

.thumbnail-item.active {
  border-color: #409eff;
  background: #ecf5ff;
}

.thumb-number {
  font-size: 14px;
  font-weight: 600;
  color: #666;
}

.thumbnail-item.active .thumb-number {
  color: #409eff;
}

.preview-main {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: #f5f5f5;
  position: relative;
  overflow: hidden;
}

.empty-state {
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
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.generating-text {
  animation: blink 1.5s ease-in-out infinite;
  color: #409eff;
  font-weight: 500;
}

@keyframes blink {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}

.preview-content {
  width: 100%;
  height: 100%;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.iframe-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: visible;
  position: relative;
  padding: 10px;
}

.iframe-scaler {
  /* 固定原始尺寸，通过transform缩放 */
  flex-shrink: 0;
  transform-origin: center center;
}

.preview-iframe {
  width: 1280px;
  height: 720px;
  border: none;
  background: #fff;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  display: block;
}

.preview-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.page-indicator {
  position: absolute;
  bottom: 10px;
  right: 10px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  padding: 6px 12px;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 500;
}

.preview-controls {
  padding: 16px 20px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  justify-content: center;
  background: #fafafa;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .preview-header {
    padding: 12px 16px;
  }

  .preview-header h3 {
    font-size: 14px;
  }

  .thumbnail-nav {
    padding: 8px;
  }

  .thumbnail-item {
    width: 32px;
    height: 32px;
  }

  .thumb-number {
    font-size: 12px;
  }

  .preview-main {
    padding: 12px;
  }
}
</style>
