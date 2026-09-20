<script setup lang="ts">

import { onMounted } from 'vue'

import ChatSidebar from '@/components/chat/ChatSidebar.vue'
import MessageList from '@/components/chat/MessageList.vue'
import ChatInputBar from '@/components/chat/ChatInputBar.vue'
import { useChat } from '@/composables/useChat'


const {
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
} = useChat()

onMounted(loadConversations)
</script>

<template>
  <div class="chat-container">
    <ChatSidebar
      :conversations="conversations"
      :current-conversation-id="currentConversationId"
      @select="loadMessages"
      @create="createNewConversation"
      @delete="removeConversation"
    />

    <div class="chat-main">
      <MessageList :messages="messages" />

      <ChatInputBar
        v-model="inputText"
        :is-generating="isGenerating"
        @send="send"
        @stop="stop"
      />
    </div>
  </div>
</template>

<style scoped>
.chat-container {
  display: flex;
  height: calc(100vh - 120px);
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
}
</style>
