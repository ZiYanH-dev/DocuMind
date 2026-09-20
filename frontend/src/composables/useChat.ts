/**
 * 对话页面的组合式函数：会话状态管理 + SSE 流式请求。
 */

import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createConversation,
  getConversationList,
  deleteConversation,
  getMessages,
  type ConversationInfo,
  type MessageInfo,
} from '@/api/conversation'


/** 对话页面状态与操作 */
export function useChat() {
  /** 会话列表 */
  const conversations: Ref<ConversationInfo[]> = ref([])

  /** 当前会话 ID */
  const currentConversationId: Ref<number | null> = ref(null)

  /** 当前会话消息列表 */
  const messages: Ref<MessageInfo[]> = ref([])

  /** 输入框内容 */
  const inputText: Ref<string> = ref('')

  /** 是否正在生成回复 */
  const isGenerating: Ref<boolean> = ref(false)

  /** 当前 SSE 请求的取消控制器 */
  let abortController: AbortController | null = null

  /** 加载会话列表 */
  async function loadConversations(): Promise<void> {
    try {
      const result = await getConversationList()
      conversations.value = result.items
    } catch (error) {
      console.error('加载会话列表失败:', error)
    }
  }

  /** 加载指定会话的消息历史 */
  async function loadMessages(conversationId: number): Promise<void> {
    currentConversationId.value = conversationId
    messages.value = []
    try {
      messages.value = await getMessages(conversationId)
    } catch (error) {
      console.error('加载消息失败:', error)
    }
  }

  /** 创建新对话并选中 */
  async function createNewConversation(): Promise<void> {
    try {
      const conv = await createConversation('新对话')
      conversations.value.unshift(conv)
      await loadMessages(conv.id)
    } catch (error) {
      console.error('创建对话失败:', error)
    }
  }

  /** 删除会话（含确认框） */
  async function removeConversation(id: number): Promise<void> {
    try {
      await ElMessageBox.confirm('确定删除这个对话吗？', '删除确认', { type: 'warning' })
      await deleteConversation(id)
      conversations.value = conversations.value.filter((c) => c.id !== id)
      if (currentConversationId.value === id) {
        currentConversationId.value = null
        messages.value = []
      }
      ElMessage.success('已删除')
    } catch (error) {
      if ((error as Error)?.message !== 'cancel') {
        console.error('删除失败:', error)
      }
    }
  }

  /** 发送消息（SSE 流式接收回复） */
  async function send(): Promise<void> {
    const content: string = inputText.value.trim()
    if (!content || isGenerating.value) return
    inputText.value = ''

    let conversationId: number | null = currentConversationId.value
    if (conversationId === null) {
      try {
        const conv = await createConversation('新对话')
        conversations.value.unshift(conv)
        conversationId = conv.id
        currentConversationId.value = conv.id
      } catch (error) {
        ElMessage.error('创建会话失败')
        return
      }
    }

    messages.value.push({
      id: Date.now(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    })

    isGenerating.value = true

    const assistantMessage: MessageInfo = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
    }
    messages.value.push(assistantMessage)

    abortController = new AbortController()

    try {
      const response: Response = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
        body: JSON.stringify({ content, conversation_id: conversationId }),
        signal: abortController.signal,
      })

      if (!response.ok || !response.body) {
        throw new Error('请求失败')
      }

      const reader: ReadableStreamDefaultReader<Uint8Array> = response.body.getReader()
      const decoder: TextDecoder = new TextDecoder()
      let buffer: string = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines: string[] = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data: string = line.slice(6)
          if (!data) continue

          try {
            const event = JSON.parse(data)
            if (event.type === 'token') {
              assistantMessage.content += event.content
            } else if (event.type === 'sources') {
              assistantMessage.sources = event.content
            }
          } catch {
            // 忽略解析错误
          }
        }
      }
    } catch (error) {
      if ((error as Error)?.name !== 'AbortError') {
        assistantMessage.content = '抱歉，出现了错误，请重试。'
        console.error('对话请求失败:', error)
      }
    } finally {
      isGenerating.value = false
      abortController = null
      loadConversations()
    }
  }

  /** 停止生成 */
  function stop(): void {
    abortController?.abort()
  }

  return {
    conversations,
    currentConversationId,
    messages,
    inputText,
    isGenerating,
    loadConversations,
    loadMessages,
    createNewConversation,
    removeConversation,
    send,
    stop,
  }
}
