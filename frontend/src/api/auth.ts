/**
 * 认证相关 API。
 */

import { http } from './request'


/** 登录请求参数 */
interface LoginParams {
  username: string
  password: string
}

/** 注册请求参数 */
interface RegisterParams {
  username: string
  email?: string
  password: string
}

/** 用户信息 */
export interface UserInfo {
  id: number
  username: string
  email: string | null
  is_active: boolean
  created_at: string
}

/** 登录响应 */
interface LoginResult {
  access_token: string
  token_type: string
}

/** 登录 */
export function login(params: LoginParams): Promise<LoginResult> {
  return http.post<LoginResult>('/auth/login', params)
}

/** 注册 */
export function register(params: RegisterParams): Promise<UserInfo> {
  return http.post<UserInfo>('/auth/register', params)
}

/** 获取当前用户信息 */
export function getCurrentUser(): Promise<UserInfo> {
  return http.get<UserInfo>('/auth/me')
}
