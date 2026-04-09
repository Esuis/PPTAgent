<template>
  <el-card class="settings-card">
    <template #header>
      <div class="card-header">
        <span>⚙️ 生成设置</span>
      </div>
    </template>

    <el-form :model="settings" label-position="top" size="default">
      <!-- 幻灯片页数 -->
      <el-form-item label="幻灯片页数">
        <el-select v-model="settings.numPages" style="width: 100%">
          <el-option label="Auto (自动)" value="auto" />
          <el-option
            v-for="i in 30"
            :key="i"
            :label="`${i} 页`"
            :value="String(i)"
          />
        </el-select>
      </el-form-item>

      <!-- 输出类型 -->
      <el-form-item label="输出类型">
        <el-select
          v-model="settings.convertType"
          style="width: 100%"
          @change="handleConvertTypeChange"
        >
          <el-option label="自由生成 (Freeform)" value="freeform" />
          <el-option label="模板 (Templates)" value="template" />
        </el-select>
      </el-form-item>

      <!-- 模板选择（条件显示） -->
      <el-form-item v-if="showTemplateSelect" label="选择模板">
        <el-select
          v-model="settings.template"
          style="width: 100%"
          placeholder="选择模板"
        >
          <el-option label="Auto (自动)" value="auto" />
          <el-option
            v-for="template in chatStore.templates"
            :key="template"
            :label="template"
            :value="template"
          />
        </el-select>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { TaskSettings } from '@/types'
import { useChatStore } from '@/stores/chat'

const props = defineProps<{
  modelValue?: TaskSettings
}>()

const emit = defineEmits<{
  'update:modelValue': [value: TaskSettings]
}>()

const chatStore = useChatStore()

const showTemplateSelect = ref(false)

const settings = ref<TaskSettings>(
  props.modelValue || {
    numPages: 'auto',
    convertType: 'freeform',
    template: 'auto',
  }
)

function handleConvertTypeChange(value: string) {
  showTemplateSelect.value = value === 'template'
  if (!showTemplateSelect.value) {
    settings.value.template = 'auto'
  }
}

// 监听设置变化并同步到父组件
watch(
  settings,
  (newVal) => {
    emit('update:modelValue', newVal)
  },
  { deep: true }
)

// 初始化时检查
if (settings.value.convertType === 'template') {
  showTemplateSelect.value = true
}
</script>

<style scoped>
.settings-card {
  height: 100%;
}

.card-header {
  font-weight: bold;
  font-size: 16px;
}
</style>
