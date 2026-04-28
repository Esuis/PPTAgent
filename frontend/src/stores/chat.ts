import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ChatMessage, TaskSettings, SlidePreview } from '@/types'
import { startGeneration, createWebSocket, createQueueWebSocket, getTemplates, cancelQueue as cancelQueueApi } from '@/api/presentation'
import { ElMessage } from 'element-plus'
import queueIcon from '@/assets/queue.png'
import cancelIcon from '@/assets/cancel.png'

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

  // 生成UUID的兼容方法（crypto.randomUUID在非HTTPS环境下不可用）
  function generateUUID(): string {
    // if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    //   return crypto.randomUUID()
    // }
    // Fallback: UUID v4
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0
      const v = c === 'x' ? r : (r & 0x3) | 0x8
      return v.toString(16)
    })
  }

  // 获取用户标识
  function getUserId(): string {


    // 4. 生成UUID并存入localStorage
    const newId = generateUUID()
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

    // 添加助手占位消息（所有assistant内容合并到此消息中）
    messages.value.push({
      role: 'assistant',
      content: '',
      steps: [],
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
          lastMessage.content = `<img src="${queueIcon}" style="width:18px;height:18px;vertical-align:middle;margin-right:4px;"> 正在排队等待，当前位置：第${response.queue_position}位`
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
          lastMessage.content = `<img src="${cancelIcon}" style="width:18px;height:18px;vertical-align:middle;margin-right:4px;"> ${response.message}`
        }
      } else if (response.status === 'failed') {
        // 后端返回失败（配置未加载、文件格式不支持等）
        isGenerating.value = false
        isInQueue.value = false
        ElMessage.error(response.message || '任务启动失败')

        // 更新最后一条消息
        const lastMessage = messages.value[messages.value.length - 1]
        if (lastMessage && lastMessage.content === '') {
          lastMessage.content = `<img src="${cancelIcon}" style="width:18px;height:18px;vertical-align:middle;margin-right:4px;"> ${response.message || '任务启动失败'}`
        }
      }
    } catch (error: any) {
      console.error('Failed to start generation:', error)
      const errorMsg = error.response?.data?.message || error.message || '启动生成任务失败'
      ElMessage.error(errorMsg)
      isGenerating.value = false
      isInQueue.value = false

      // 更新最后一条消息
      if (messages.value.length > 0) {
        messages.value[messages.value.length - 1].content = `<img src="${cancelIcon}" style="width:18px;height:18px;vertical-align:middle;margin-right:4px;"> 启动任务失败：${errorMsg}`
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
          lastMessage.content = `<img src="${queueIcon}" style="width:18px;height:18px;vertical-align:middle;margin-right:4px;"> 正在排队等待，当前位置：第${data.position}位`
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
          lastMsg.content = `<img src="${cancelIcon}" style="width:18px;height:18px;vertical-align:middle;margin-right:4px;"> 排队已取消`
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

  // 需要过滤的内部工具名（模型推理等，不是真实工具）
  const INTERNAL_TOOLS = new Set(['think', 'thinking', 'thought', 'reflection'])

  // 判断是否为过程型消息（系统消息/含tool_calls的assistant消息/含thinking的content）
  function isProcessMessage(data: any): boolean {
    const role = data.role || ''
    // 系统消息是过程步骤
    if (role === 'system' || role === 'System') {
      return true
    }
    // assistant消息如果有tool_calls（包括thinking等内部工具），是过程步骤
    if (data.tool_calls && data.tool_calls.length > 0) {
      return true
    }
    // 兼容旧后端：content是thinking工具调用序列化的JSON，也算过程步骤
    if ((role === 'assistant' || role === 'Assistant')) {
      const content = (data.content || '').trim()
      if (content && isThinkingJsonContent(content)) {
        return true
      }
    }
    return false
  }

  // 检测content是否为thinking工具调用序列化的JSON
  function isThinkingJsonContent(content: string): boolean {
    if (!content.startsWith('{') && !content.startsWith('[')) return false
    try {
      const parsed = JSON.parse(content)
      // 单个thinking工具调用
      if (parsed.name && INTERNAL_TOOLS.has(parsed.name)) return true
      // 多个工具调用的数组
      if (Array.isArray(parsed) && parsed.some((item: any) => item.name && INTERNAL_TOOLS.has(item.name))) return true
    } catch {
      // 不是JSON，当做普通文本
    }
    return false
  }

  // 过滤掉内部工具调用（think/thinking等）
  function filterRealToolCalls(toolCalls: any[]): any[] {
    if (!toolCalls) return []
    return toolCalls.filter((tc: any) => !INTERNAL_TOOLS.has(tc.name || ''))
  }

  // 检查消息是否应该完全跳过
  function shouldSkipMessage(data: any): boolean {
    const role = data.role || ''
    // 所有tool消息都跳过（工具调用摘要已在assistant消息中显示）
    if (role === 'tool' || role === 'Tool') {
      return true
    }
    // assistant消息：检查是否有任何有效内容
    if ((role === 'assistant' || role === 'Assistant')) {
      const content = (data.content || '').trim()
      // 有tool_calls的情况
      if (data.tool_calls) {
        const realToolCalls = filterRealToolCalls(data.tool_calls)
        const hasThinkingInToolCalls = extractThinkingContent(data.tool_calls).trim().length > 0
        // 没有真实工具、没有文本、也没有thinking内容 → 跳过
        if (realToolCalls.length === 0 && !content && !hasThinkingInToolCalls) {
          return true
        }
      }
      // 没有tool_calls但有content的情况
      // 兼容旧后端：content可能是thinking序列化JSON
      if (!data.tool_calls && content) {
        // content是thinking JSON → 不跳过
        if (isThinkingJsonContent(content)) return false
        // content是普通文本 → 不跳过
        return false
      }
      // 没有tool_calls且没有content → 跳过
      if (!data.tool_calls && !content) {
        return true
      }
    }
    return false
  }

  // 从tool_calls中提取thinking/thought等内部工具的思考内容
  function extractThinkingContent(toolCalls: any[]): string {
    if (!toolCalls) return ''
    const parts: string[] = []
    toolCalls.forEach((tc: any) => {
      if (INTERNAL_TOOLS.has(tc.name || '')) {
        try {
          const args = typeof tc.arguments === 'string' ? JSON.parse(tc.arguments) : tc.arguments
          const thought = args?.thought || args?.thinking || args?.content || ''
          if (thought && thought.trim()) {
            parts.push(thought.trim())
          }
        } catch {
          // JSON解析失败，忽略
        }
      }
    })
    return parts.join('\n')
  }

  // 获取最后一条assistant消息（用于向其追加步骤/内容）
  function getLastAssistantMessage(): ChatMessage | null {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].role === 'assistant') return messages.value[i]
    }
    return null
  }

  function handleWebSocketMessage(data: any) {
    console.log('📨 WebSocket message received:', data)
    console.log('📦 Current messages count:', messages.value.length)

    switch (data.type) {
      case 'message': {
        // 跳过纯内部工具消息（think/thinking等）
        if (shouldSkipMessage(data)) {
          break
        }

        const formattedContent = formatMessageContent(data)
        const isProcess = isProcessMessage(data)
        const lastAssistant = getLastAssistantMessage()

        if (isProcess) {
          // 过程型消息：追加到最后一条assistant消息的steps中
          if (lastAssistant) {
            if (!lastAssistant.steps) lastAssistant.steps = []
            lastAssistant.steps.push({ content: formattedContent })
          }
        } else {
          // 非过程型消息（普通assistant回复）
          if (lastAssistant && lastAssistant.content === '') {
            // 更新占位消息的主体内容
            lastAssistant.content = formattedContent
          } else if (lastAssistant) {
            // 已有内容，追加到现有assistant消息
            lastAssistant.content = lastAssistant.content
              ? lastAssistant.content + '\n\n' + formattedContent
              : formattedContent
          } else {
            // 兜底：没有assistant消息时才新增
            messages.value.push({
              role: data.role || 'assistant',
              content: formattedContent,
              toolCalls: data.tool_calls,
              steps: [],
            })
          }
        }
        break
      }

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

      case 'completed': {
        // 处理完成状态
        if (data.file) {
          downloadUrl.value = `/api/download/${taskId.value}`
          const lastAssistant = getLastAssistantMessage()
          if (lastAssistant && !lastAssistant.content) {
            lastAssistant.content = '幻灯片生成完成，点击右侧按钮下载文件'
          } else if (lastAssistant) {
            lastAssistant.content = lastAssistant.content
              ? lastAssistant.content + '\n\n幻灯片生成完成，点击右侧按钮下载文件'
              : '幻灯片生成完成，点击右侧按钮下载文件'
          }
        }
        isGenerating.value = false
        break
      }

      case 'error': {
        // 处理错误
        ElMessage.error(data.message || '生成过程中发生错误')
        const lastAssistant = getLastAssistantMessage()
        if (lastAssistant && !lastAssistant.content) {
          lastAssistant.content = `错误: ${data.message}`
        } else if (lastAssistant) {
          lastAssistant.content = lastAssistant.content
            ? lastAssistant.content + `\n\n错误: ${data.message}`
            : `错误: ${data.message}`
        }
        isGenerating.value = false
        break
      }
    }
  }

  // 工具调用凝练描述映射
  const TOOL_SUMMARIES: Record<string, string> = {
    web_search: '搜索资料',
    search: '搜索资料',
    read_file: '读取文件',
    read: '读取文件',
    write_file: '写入文件',
    write: '写入文件',
    execute_command: '执行命令',
    finalize: '完成任务',
    create_slide: '生成幻灯片',
    edit_slide: '编辑幻灯片',
    generate_slide: '生成幻灯片',
  }

  function summarizeToolCall(name: string, argsStr?: string): string {
    const base = TOOL_SUMMARIES[name] || `调用 ${name}`
    if (!argsStr) return base

    try {
      const args = typeof argsStr === 'string' ? JSON.parse(argsStr) : argsStr
      // 为常见工具提取关键参数做简要描述
      if (name === 'web_search' || name === 'search') {
        const query = args.query || args.keywords || args.q || ''
        return query ? `搜索: ${truncate(query, 30)}` : base
      }
      if (name === 'read_file' || name === 'read') {
        const path = args.path || args.file_path || args.filename || ''
        return path ? `读取: ${truncate(path.split('/').pop() || path, 30)}` : base
      }
      if (name === 'write_file' || name === 'write') {
        const path = args.path || args.file_path || args.filename || ''
        return path ? `写入: ${truncate(path.split('/').pop() || path, 30)}` : base
      }
      if (name === 'execute_command') {
        const cmd = args.command || args.cmd || ''
        return cmd ? `执行: ${truncate(cmd, 40)}` : base
      }
      if (name === 'finalize') {
        const outcome = args.outcome || ''
        return outcome ? `完成: ${truncate(outcome, 30)}` : base
      }
      if (name === 'create_slide' || name === 'generate_slide') {
        const num = args.slide_number || args.number || args.page || ''
        return num ? `生成第 ${num} 页幻灯片` : base
      }
      if (name === 'edit_slide') {
        const num = args.slide_number || args.number || args.page || ''
        return num ? `编辑第 ${num} 页幻灯片` : base
      }
    } catch {
      // JSON解析失败，使用默认描述
    }
    return base
  }

  function truncate(str: string, maxLen: number): string {
    if (str.length <= maxLen) return str
    return str.slice(0, maxLen - 3) + '...'
  }

  function formatMessageContent(data: any): string {
    const role = data.role || 'assistant'

    // system 消息：凝练为阶段描述
    if (role === 'system' || role === 'System') {
      const content = data.content || ''
      // 替换冗长的系统消息
      if (content.includes('DeepPresenter running')) {
        return '启动任务，正在准备...'
      }
      // 已经是简洁描述的直接返回
      return content
    }

    // tool 消息：跳过，因为assistant消息已显示工具调用摘要
    if (role === 'tool' || role === 'Tool') {
      return ''
    }

    // assistant 消息
    const parts: string[] = []
    const content = (data.content || '').trim()

    // 如果有工具调用，处理工具调用摘要
    if (data.tool_calls && data.tool_calls.length > 0) {
      // 先提取内部工具（thinking）的思考内容
      const thinkingContent = extractThinkingContent(data.tool_calls)
      if (thinkingContent) {
        parts.push(thinkingContent)
      }

      // 再提取真实工具调用的摘要
      const realToolCalls = filterRealToolCalls(data.tool_calls)
      realToolCalls.forEach((tool: any) => {
        parts.push(summarizeToolCall(tool.name, tool.arguments))
      })

      if (parts.length > 0) {
        // 如果同时有文本内容（非tool_call JSON），也附带
        if (content && !isThinkingJsonContent(content) && content.length < 100) {
          parts.unshift(content)
        }
        return parts.join('\n')
      }
    }

    // 没有tool_calls字段时，尝试从content中提取thinking内容
    // 兼容旧后端：旧版yield_msg.text会把thinking工具调用序列化进content
    if (content) {
      const extractedFromContent = tryExtractThinkingFromContent(content)
      if (extractedFromContent) {
        return extractedFromContent
      }

      // 普通文本内容
      if (content.length < 150) {
        return content
      }
      const lines = content.split('\n').filter((l: string) => l.trim())
      if (lines.length <= 3) {
        return content
      }
      return lines.slice(0, 2).join('\n') + '\n...'
    }

    return ''
  }

  // 从content字段中提取thinking内容（兼容旧后端）
  // 旧后端yield_msg.text会将tool_calls序列化进content，格式如：
  //   {"name":"thinking","arguments":"{\"thought\":\"...\"}"}
  //   或多个tool_call的数组字符串
  function tryExtractThinkingFromContent(content: string): string {
    // 单个tool_call JSON
    if (content.startsWith('{')) {
      try {
        const obj = JSON.parse(content)
        if (obj.name && INTERNAL_TOOLS.has(obj.name) && obj.arguments) {
          const args = typeof obj.arguments === 'string' ? JSON.parse(obj.arguments) : obj.arguments
          const thought = args?.thought || args?.thinking || args?.content || ''
          if (thought && thought.trim()) return thought.trim()
        }
      } catch {
        // 不是有效JSON，当做普通文本处理
      }
    }
    // 多个tool_call的数组字符串
    if (content.startsWith('[')) {
      try {
        const arr = JSON.parse(content)
        if (Array.isArray(arr)) {
          const thoughts: string[] = []
          for (const item of arr) {
            if (item.name && INTERNAL_TOOLS.has(item.name) && item.arguments) {
              const args = typeof item.arguments === 'string' ? JSON.parse(item.arguments) : item.arguments
              const thought = args?.thought || args?.thinking || args?.content || ''
              if (thought && thought.trim()) thoughts.push(thought.trim())
            }
          }
          if (thoughts.length > 0) return thoughts.join('\n')
        }
      } catch {
        // 不是有效JSON
      }
    }
    return ''
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
        lastMsg.content = `<img src="${cancelIcon}" style="width:18px;height:18px;vertical-align:middle;margin-right:4px;"> 排队已取消`
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
