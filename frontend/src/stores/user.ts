/**
 * 用户状态管理。
 */

import { ref, type Ref } from 'vue'
import { defineStore } from 'pinia'

import { login as loginApi, register as registerApi, getCurrentUser } from '@/api/auth'
import type { UserInfo } from '@/api/auth'


export const useUserStore = defineStore('user', () => {
  /** Token */
  const token: Ref<string> = ref(localStorage.getItem('access_token') || '')

  /** 用户信息 */
  const userInfo: Ref<UserInfo | null> = ref(null)

  /** 是否已登录 */
  const isLoggedIn: Ref<boolean> = ref(!!token.value)

  /** 启动时自动恢复用户信息 */
  if (token.value) {
    fetchUserInfo().catch(() => {
      // token 过期或无效，清除
      token.value = ''
      isLoggedIn.value = false
      localStorage.removeItem('access_token')
    })
  }

  /** 登录 */
  async function login(username: string, password: string): Promise<void> {
    const result = await loginApi({ username, password })
    
    token.value = result.access_token
    isLoggedIn.value = true
    localStorage.setItem('access_token', result.access_token)
    await fetchUserInfo()
  }

  /** 注册 */
  async function register(username: string, password: string, email?: string): Promise<void> {
    await registerApi({ username, password, email })
  }

  /** 获取用户信息 */
  async function fetchUserInfo(): Promise<void> {
    userInfo.value = await getCurrentUser()
  }

  /** 登出 */
  function logout(): void {
    token.value = ''
    userInfo.value = null
    isLoggedIn.value = false
    localStorage.removeItem('access_token')
  }

  return {
    token,
    userInfo,
    isLoggedIn,
    login,
    register,
    fetchUserInfo,
    logout,
  }
})
