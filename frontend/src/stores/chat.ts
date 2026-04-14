import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatMessage, TaskSettings, SlidePreview } from '@/types'
import { startGeneration, createWebSocket, createQueueWebSocket, getTemplates, cancelQueue as cancelQueueApi } from '@/api/presentation'
import { ElMessage } from 'element-plus'

const USER_ID_KEY = 'pptagent_user_id'

export const useChatStore = defineStore('chat', () => {
  // State
  const messages = ref<ChatMessage[]>([])
  const isGenerating = ref(false)
  const taskId = ref<string | null>(null)
  const downloadUrl = ref<string | null>(null)
  const templates = ref<string[]>([])
  const ws = ref<WebSocket | null>(null)
  const slidePreviews = ref<SlidePreview[]>([])
  // 用于传递 isGenerating 状态给组件
  const isGeneratingRef = isGenerating

  // 排队相关状态
  const userId = ref<string | null>(null)
  const isInQueue = ref(false)
  const queuePosition = ref<number | null>(null)
  const queueWs = ref<WebSocket | null>(null)

  // 获取用户标识
  function getUserId(): string {
    // 1. URL参数 ?guwpToken=xxx
    const urlParams = new URLSearchParams(window.location.search)
    const urlToken = urlParams.get('guwpToken')
    if (urlToken) {
      return urlToken
    }

    // 2. Cookie中的 JSESSIONID
    const cookies = document.cookie.split(';')
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split('=')
      if (name === 'JSESSIONID') {
        return value
      }
    }

    // 3. localStorage中的 pptagent_user_id
    const storedId = localStorage.getItem(USER_ID_KEY)
    if (storedId) {
      return storedId
    }

    // 4. 生成UUID并存入localStorage
    const newId = crypto.randomUUID()
    localStorage.setItem(USER_ID_KEY, newId)
    return newId
  }

  // 初始化用户标识
  function initUserId() {
    userId.value = getUserId()
  }

  // Actions
  async function loadTemplates() {
    try {
      const response = await getTemplates()
      templates.value = response.templates
    } catch (error) {
      console.error('Failed to load templates:', error)
      templates.value = []
    }
  }

  async function sendMessage(
    instruction: string,
    files: File[],
    settings: TaskSettings
  ) {
    if (!instruction.trim() && files.length === 0) {
      ElMessage.warning('请输入指令或上传文件')
      return
    }

    // 确保用户ID已初始化
    if (!userId.value) {
      initUserId()
    }

    isGenerating.value = true
    downloadUrl.value = null
    queuePosition.value = null
    slidePreviews.value = []

    // 添加用户消息
    const userContent = instruction || '请根据上传的附件制作PPT'
    messages.value.push({
      role: 'user',
      content: userContent,
    })

    // 添加助手占位消息
    messages.value.push({
      role: 'assistant',
      content: '',
    })

    try {
      // 准备FormData
      const formData = new FormData()
      formData.append('instruction', instruction || '请根据上传的附件制作PPT')
      formData.append('num_pages', settings.numPages)
      formData.append('convert_type', settings.convertType)
      formData.append('template', settings.template)

      files.forEach((file) => {
        formData.append('files', file)
      })

      // 启动生成任务，传递userId
      const response = await startGeneration(formData, userId.value || undefined)

      if (response.status === 'queued') {
        // 进入排队状态
        isInQueue.value = true
        queuePosition.value = response.queue_position ?? null
        taskId.value = null

        // 更新占位消息
        const lastMessage = messages.value[messages.value.length - 1]
        if (lastMessage && lastMessage.content === '') {
          lastMessage.content = `⏳ 正在排队等待，当前位置：第${response.queue_position}位`
        }

        // 建立队列WebSocket连接
        connectQueueWebSocket(userId.value!)
      } else if (response.status === 'running') {
        // 直接开始执行
        isInQueue.value = false
        queuePosition.value = null
        taskId.value = response.task_id

        // 建立WebSocket连接
        connectWebSocket(response.task_id)
      } else if (response.status === 'rejected') {
        // 被拒绝
        isGenerating.value = false
        isInQueue.value = false
        ElMessage.warning(response.message)

        // 更新最后一条消息
        const lastMessage = messages.value[messages.value.length - 1]
        if (lastMessage && lastMessage.content === '') {
          lastMessage.content = `❌ ${response.message}`
        }
      }
    } catch (error: any) {
      console.error('Failed to start generation:', error)
      ElMessage.error(error.response?.data?.message || '启动生成任务失败')
      isGenerating.value = false
      isInQueue.value = false

      // 更新最后一条消息
      if (messages.value.length > 0) {
        messages.value[messages.value.length - 1].content = '❌ 启动任务失败'
      }
    }
  }

  function connectQueueWebSocket(uid: string) {
    // 关闭旧连接
    if (queueWs.value) {
      queueWs.value.close()
    }

    const websocket = createQueueWebSocket(uid)
    queueWs.value = websocket

    websocket.onopen = () => {
      console.log('Queue WebSocket connected')
    }

    websocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleQueueWebSocketMessage(data)
      } catch (error) {
        console.error('Failed to parse queue WebSocket message:', error)
      }
    }

    websocket.onerror = (error) => {
      console.error('Queue WebSocket error:', error)
    }

    websocket.onclose = (event) => {
      console.log('Queue WebSocket closed:', event.code, event.reason)
      // 如果是因为轮到用户而关闭，不提示
      if (isInQueue.value && event.code !== 1000 && event.code !== 1001) {
        ElMessage.warning('排队连接已断开')
      }
    }
  }

  function handleQueueWebSocketMessage(data: any) {
    console.log('📨 Queue WebSocket message received:', data)

    switch (data.type) {
      case 'queue_update':
        // 更新排队位置
        queuePosition.value = data.position
        // 更新消息内容
        const lastMessage = messages.value[messages.value.length - 1]
        if (lastMessage && lastMessage.content.includes('正在排队等待')) {
          lastMessage.content = `⏳ 正在排队等待，当前位置：第${data.position}位`
        }
        break

      case 'queue_started':
        // 轮到用户，开始执行
        isInQueue.value = false
        queuePosition.value = null
        taskId.value = data.task_id

        // 关闭队列WebSocket
        if (queueWs.value) {
          queueWs.value.close()
          queueWs.value = null
        }

        // 更新消息
        const msg = messages.value[messages.value.length - 1]
        if (msg && msg.content.includes('正在排队等待')) {
          msg.content = '🎉 轮到您了，正在启动生成任务...'
        }

        // 建立任务WebSocket连接
        connectWebSocket(data.task_id)
        break

      case 'queue_cancelled':
        // 排队被取消
        isInQueue.value = false
        queuePosition.value = null
        isGenerating.value = false

        // 关闭队列WebSocket
        if (queueWs.value) {
          queueWs.value.close()
          queueWs.value = null
        }

        ElMessage.info(data.reason || '排队已取消')

        // 更新消息
        const lastMsg = messages.value[messages.value.length - 1]
        if (lastMsg && lastMsg.content.includes('正在排队等待')) {
          lastMsg.content = '❌ 排队已取消'
        }
        break
    }
  }

  function connectWebSocket(newTaskId: string) {
    // 关闭旧连接
    if (ws.value) {
      ws.value.close()
    }

    const websocket = createWebSocket(newTaskId)
    ws.value = websocket

    websocket.onopen = () => {
      console.log('WebSocket connected')
    }

    websocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleWebSocketMessage(data)
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error)
      ElMessage.error('WebSocket连接错误')
    }

    websocket.onclose = (event) => {
      console.log('WebSocket closed:', event.code, event.reason)
      // 只有在生成中且非正常关闭时才提示
      // 1000 = 正常关闭, 1001 = 离开
      if (isGenerating.value && event.code !== 1000 && event.code !== 1001) {
        ElMessage.warning('WebSocket连接异常断开')
      }
    }
  }

  function handleWebSocketMessage(data: any) {
    console.log('📨 WebSocket message received:', data)
    console.log('📦 Current messages count:', messages.value.length)
    
    const lastMessage = messages.value[messages.value.length - 1]

    switch (data.type) {
      case 'message':
        // 处理聊天消息
        if (lastMessage && lastMessage.content === '') {
          // 更新占位消息
          lastMessage.content = formatMessageContent(data)
        } else {
          // 添加新消息
          messages.value.push({
            role: data.role || 'assistant',
            content: formatMessageContent(data),
            toolCalls: data.tool_calls,
          })
        }
        break

      case 'slide_preview':
        // 处理幻灯片预览消息
        if (data.html_content) {
          // Design模式 - 更新或添加HTML预览
          const slideNumber = data.slide_number || 1
          const existingIndex = slidePreviews.value.findIndex(p => p.number === slideNumber)
          
          // 转换HTML中的本地图片路径为HTTP可访问的路径
          // 容器内workspace挂载在 /opt/workspace，后端通过 /workspace 静态文件服务映射
          // 需要将 /opt/workspace/... 转换为 /workspace/...
          let processedHtml = data.html_content
          processedHtml = processedHtml.replace(
            /src=["'](\/[^"']+)["']/g,
            (match: string, path: string) => {
              // /opt/workspace/{id}/... -> /workspace/{id}/...
              if (path.startsWith('/opt/workspace/')) {
                return `src="${path.replace('/opt/workspace/', '/workspace/')}"`
              }
              // /root/.cache/deeppresenter/{id}/... -> /workspace/{id}/... (非容器环境)
              if (path.startsWith('/root/.cache/deeppresenter/')) {
                return `src="${path.replace('/root/.cache/deeppresenter/', '/workspace/')}"`
              }
              // 已经是 /workspace/... 的路径无需转换
              // 其他路径（data:URL、http://、https://、相对路径等）保持不变
              return match
            }
          )
          
          if (existingIndex >= 0) {
            // 更新已存在的预览
            slidePreviews.value[existingIndex] = {
              number: slideNumber,
              content: processedHtml,
              type: 'html',
              mode: 'design',
            }
          } else {
            // 添加新预览
            slidePreviews.value.push({
              number: slideNumber,
              content: processedHtml,
              type: 'html',
              mode: 'design',
            })
          }
        } else if (data.images && data.images.length > 0) {
          // PPTAgent模式 - 更新或添加图片预览
          // 先清空旧的pptagent预览
          slidePreviews.value = slidePreviews.value.filter(p => p.mode !== 'pptagent')
          
          data.images.forEach((img: string, idx: number) => {
            slidePreviews.value.push({
              number: idx + 1,
              content: img,
              type: 'image',
              mode: 'pptagent',
            })
          })
          
          // 按页码排序
          slidePreviews.value.sort((a, b) => a.number - b.number)
        }
        break

      case 'completed':
        // 处理完成状态
        if (data.file) {
          downloadUrl.value = `/api/download/${taskId.value}`
          if (lastMessage && lastMessage.content === '') {
            lastMessage.content = '📄 幻灯片生成完成，点击下方按钮下载文件'
          } else {
            messages.value.push({
              role: 'assistant',
              content: '📄 幻灯片生成完成，点击下方按钮下载文件',
            })
          }
        }
        isGenerating.value = false
        break

      case 'error':
        // 处理错误
        ElMessage.error(data.message || '生成过程中发生错误')
        if (lastMessage && lastMessage.content === '') {
          lastMessage.content = `❌ 错误: ${data.message}`
        } else {
          messages.value.push({
            role: 'assistant',
            content: `❌ 错误: ${data.message}`,
          })
        }
        isGenerating.value = false
        break
    }
  }

  function formatMessageContent(data: any): string {
    let content = data.content || ''

    // 如果有工具调用，格式化显示
    if (data.tool_calls && data.tool_calls.length > 0) {
      content += '\n\n'
      data.tool_calls.forEach((tool: any) => {
        content += `\n**Tool Call: ${tool.name}**\n`
        content += '```json\n'
        try {
          const args = JSON.parse(tool.arguments)
          content += JSON.stringify(args, null, 2)
        } catch {
          content += tool.arguments
        }
        content += '\n```\n'
      })
    }

    return content
  }

  function clearChat() {
    messages.value = []
    taskId.value = null
    downloadUrl.value = null
    isGenerating.value = false
    slidePreviews.value = []
    isInQueue.value = false
    queuePosition.value = null

    if (ws.value) {
      ws.value.close()
      ws.value = null
    }

    if (queueWs.value) {
      queueWs.value.close()
      queueWs.value = null
    }
  }

  async function cancelQueue() {
    if (!userId.value) {
      return
    }

    try {
      await cancelQueueApi(userId.value)
      isInQueue.value = false
      queuePosition.value = null
      isGenerating.value = false

      if (queueWs.value) {
        queueWs.value.close()
        queueWs.value = null
      }

      // 更新消息
      const lastMsg = messages.value[messages.value.length - 1]
      if (lastMsg && lastMsg.content.includes('正在排队等待')) {
        lastMsg.content = '❌ 排队已取消'
      }
    } catch (error) {
      console.error('Failed to cancel queue:', error)
      ElMessage.error('取消排队失败')
    }
  }

  return {
    messages,
    isGenerating,
    isGeneratingRef,
    taskId,
    downloadUrl,
    templates,
    slidePreviews,
    userId,
    isInQueue,
    queuePosition,
    loadTemplates,
    sendMessage,
    clearChat,
    cancelQueue,
    initUserId,
  }
})
