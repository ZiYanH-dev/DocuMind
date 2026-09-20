<script setup lang="ts">

import { ref, watch, nextTick, type Ref } from 'vue'

import type { MessageInfo } from '@/api/conversation'
import MessageItem from './MessageItem.vue'


const props = defineProps<{
  messages: MessageInfo[]
}>()

const containerRef: Ref<HTMLElement | null> = ref(null)

/** 滚动到底部 */
function scrollToBottom(): void {
  nextTick(() => {
    if (containerRef.value) {
      containerRef.value.scrollTop = containerRef.value.scrollHeight
    }
  })
}

// 消息变化时自动滚动到底部（深监听以捕获流式 token 更新）
watch(() => props.messages, scrollToBottom, { deep: true })
</script>

<template>
  <div ref="containerRef" class="message-list">
    <div v-if="messages.length === 0" class="welcome">
      <h2>👋 欢迎使用 AI 学习助手</h2>
      <p>上传文档到知识库，然后就可以基于文档内容进行问答了！</p>
    </div>

    <MessageItem
      v-for="msg in messages"
      :key="msg.id"
      :message="msg"
    />
  </div>
</template>

<style scoped>
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.welcome {
  text-align: center;
  padding: 60px 20px;
  color: #666;
}
</style>
