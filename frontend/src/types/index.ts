// 聊天消息类型
export interface ChatMessage {
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  toolCalls?: ToolCall[]
}

export interface ToolCall {
  name: string
  arguments: string
}

// 任务设置
export interface TaskSettings {
  numPages: string
  convertType: string
  template: string
}

// Token统计
export interface AgentTokenStats {
  agent_name: string
  model: string
  prompt: number
  completion: number
  total: number
}

export interface TokenStats {
  agents: AgentTokenStats[]
  total_prompt: number
  total_completion: number
  total_all: number
}

// WebSocket消息类型
export interface WSMessage {
  type: 'message' | 'file_ready' | 'token_stats' | 'completed' | 'error' | 'slide_preview'
  role?: string
  content?: string
  tool_calls?: ToolCall[]
  file?: string
  data?: TokenStats
  message?: string
  // 幻灯片预览相关字段
  slide_number?: number
  slide_count?: number
  html_content?: string
  images?: string[]
  mode?: 'design' | 'pptagent'
}

// 幻灯片预览数据
export interface SlidePreview {
  number: number
  content: string
  type: 'html' | 'image'
  mode: 'design' | 'pptagent'
}

// API响应类型
export interface GenerateResponse {
  task_id: string
  status: string
  message: string
}

export interface TaskStatusResponse {
  task_id: string
  status: string
  progress: string | null
  result_file: string | null
  error: string | null
}

export interface TemplateListResponse {
  templates: string[]
}
