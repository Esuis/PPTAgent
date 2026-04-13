<template>
  <el-dialog
    v-model="visible"
    title="⏳ 正在排队等待"
    width="400px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
  >
    <div class="queue-content">
      <div class="queue-position">
        当前位置：第 <span class="position-number">{{ position }}</span> 位
      </div>
      <div class="queue-hint">
        请耐心等待，轮到您时会自动开始生成
      </div>
    </div>
    <template #footer>
      <el-button @click="handleCancel">取消排队</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { ElMessageBox } from 'element-plus'

const chatStore = useChatStore()

const visible = computed({
  get: () => chatStore.isInQueue,
  set: () => {},
})

const position = computed(() => chatStore.queuePosition || 0)

async function handleCancel() {
  try {
    await ElMessageBox.confirm('确定要取消排队吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    chatStore.cancelQueue()
  } catch {
    // 用户取消操作
  }
}
</script>

<style scoped>
.queue-content {
  text-align: center;
  padding: 20px 0;
}

.queue-position {
  font-size: 18px;
  margin-bottom: 16px;
}

.position-number {
  font-size: 32px;
  font-weight: bold;
  color: #409eff;
}

.queue-hint {
  color: #909399;
  font-size: 14px;
}
</style>
