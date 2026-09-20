/**
 * 对话相关 API。
 */

import { http } from './request'


/** 对话信息 */
export interface ConversationInfo {
  id: number
  title: string
  created_at: string
  updated_at: string
}

/** 对话列表 */
interface ConversationList {
  total: number
  items: ConversationInfo[]
}

/** 消息信息 */
export interface MessageInfo {
  id: number
  role: string
  content: string
  sources?: Array<{
    document_id: number
    document_title: string
    chunk_index: number
    snippet: string
    score: number
  }>
  created_at: string
}

/** 创建对话 */
export function createConversation(title: string): Promise<ConversationInfo> {
  return http.post<ConversationInfo>('/conversations', { title })
}

/** 获取对话列表 */
export function getConversationList(skip: number = 0, limit: number = 50): Promise<ConversationList> {
  return http.get<ConversationList>('/conversations', { params: { skip, limit } })
}

/** 删除对话 */
export function deleteConversation(id: number): Promise<void> {
  return http.delete<void>(`/conversations/${id}`)
}

/** 获取对话消息历史 */
export function getMessages(conversationId: number): Promise<MessageInfo[]> {
  return http.get<MessageInfo[]>(`/conversations/${conversationId}/messages`)
}
