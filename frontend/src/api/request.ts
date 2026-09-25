/**
 * Axios 实例与请求拦截器配置。
 */

import axios, { type AxiosInstance, type AxiosProgressEvent, type AxiosRequestConfig, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'


/** API 响应通用结构 */
interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T | null
}

/** 后端错误响应体：优先取统一信封的 message，detail 作为兼容兜底 */
interface ApiErrorBody {
  code?: number
  message?: string
  detail?: string
}

/** 登录 / 注册接口自身的 401 表示凭证错误，不能当成会话过期 */
function isAuthEndpoint(url: string | undefined): boolean {
  if (!url) return false
  return url.includes('/auth/login') || url.includes('/auth/register')
}

/** 创建 Axios 实例 */
const request: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/** 请求拦截器：自动添加 Token */
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token: string | null = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error: unknown) => {
    return Promise.reject(error)
  },
)

/** 响应拦截器：统一错误处理 */
request.interceptors.response.use(
  (response: AxiosResponse<ApiResponse>) => {
    const res: ApiResponse = response.data

    if (res.code !== 0) {
      ElMessage.error(res.message || '请求失败')
      return Promise.reject(new Error(res.message))
    }

    return res.data as any
  },
  (error: unknown) => {
    if (axios.isAxiosError(error)) {
      const status: number | undefined = error.response?.status
      const body = error.response?.data as ApiErrorBody | undefined
      const message: string = body?.message || body?.detail || error.message

      switch (status) {
        case 401:
          if (isAuthEndpoint(error.config?.url)) {
            ElMessage.error(message || '用户名或密码错误')
            break
          }
          ElMessage.error('登录已过期，请重新登录')
          localStorage.removeItem('access_token')
          router.push('/login')
          break
        case 403:
          ElMessage.error('没有访问权限')
          break
        case 404:
          ElMessage.error('请求资源不存在')
          break
        case 500:
          ElMessage.error('服务器内部错误')
          break
        default:
          ElMessage.error(message || '请求失败')
      }
    } else {
      ElMessage.error('网络异常，请检查网络连接')
    }
    return Promise.reject(error)
  },
)

/** 通用请求方法 */
export const http = {
  get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return request.get(url, config) as Promise<T>
  },

  post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request.post(url, data, config) as Promise<T>
  },

  put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request.put(url, data, config) as Promise<T>
  },

  delete<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return request.delete(url, config) as Promise<T>
  },

  upload<T = unknown>(url: string, file: File, onProgress?: (progress: number) => void): Promise<T> {
    const formData: FormData = new FormData()
    formData.append('file', file)
    return request.post(url, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event: AxiosProgressEvent) => {
        const { loaded, total } = event
        if (loaded && total && onProgress) {
          onProgress(Math.round((loaded * 100) / total))
        }
      },
    }) as Promise<T>
  },
}

export default request
