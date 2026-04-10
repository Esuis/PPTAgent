import axios from 'axios'
import type { GenerateResponse, TaskStatusResponse, TemplateListResponse } from '@/types'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

/**
 * 获取模板列表
 */
export async function getTemplates(): Promise<TemplateListResponse> {
  return api.get('/templates')
}

/**
 * 启动PPT生成任务
 */
export async function startGeneration(data: FormData): Promise<GenerateResponse> {
  return api.post('/generate', data, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 60000, // 生成任务可能需要更长时间
  })
}

/**
 * 查询任务状态
 */
export async function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  return api.get(`/tasks/${taskId}/status`)
}

/**
 * 获取下载URL
 */
export function getDownloadUrl(taskId: string): string {
  return `/api/download/${taskId}`
}

/**
 * 创建WebSocket连接
 */
export function createWebSocket(taskId: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/api/ws/${taskId}`
  return new WebSocket(wsUrl)
}

export default api
