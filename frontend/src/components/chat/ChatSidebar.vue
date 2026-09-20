<script setup lang="ts">

import type { ConversationInfo } from '@/api/conversation'


defineProps<{
  conversations: ConversationInfo[]
  currentConversationId: number | null
}>()

const emit = defineEmits<{
  select: [id: number]
  create: []
  delete: [id: number]
}>()
</script>

<template>
  <div class="chat-sidebar">
    <div class="new-chat-wrap">
      <el-button type="primary" class="new-chat-btn" @click="emit('create')">
        <el-icon><Plus /></el-icon>
        新对话
      </el-button>
    </div>

    <div class="conversation-list">
      <div
        v-for="conv in conversations"
        :key="conv.id"
        :class="['conversation-item', { active: conv.id === currentConversationId }]"
        @click="emit('select', conv.id)"
      >
        <el-icon><ChatDotRound /></el-icon>
        <span class="conv-title">{{ conv.title }}</span>
        <el-icon class="delete-btn" @click.stop="emit('delete', conv.id)">
          <Delete />
        </el-icon>
      </div>
      <el-empty v-if="conversations.length === 0" description="暂无对话" />
    </div>
  </div>
</template>

<style scoped>
.chat-sidebar {
  width: 240px;
  background: #f8f9fa;
  border-right: 1px solid #e6e6e6;
  display: flex;
  flex-direction: column;
}

.new-chat-wrap {
  padding: 16px;
}

.new-chat-btn {
  width: 100%;
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  cursor: pointer;
  border-bottom: 1px solid #eee;
  transition: background 0.2s;
}

.conversation-item:hover {
  background: #e8eaed;
}

.conversation-item.active {
  background: #e3f2fd;
  color: #409eff;
}

.conversation-item .conv-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-item .delete-btn {
  opacity: 0;
  transition: opacity 0.2s;
  color: #c0c4cc;
  cursor: pointer;
  font-size: 14px;
}

.conversation-item:hover .delete-btn {
  opacity: 1;
}

.conversation-item .delete-btn:hover {
  color: #f56c6c;
}
</style>
