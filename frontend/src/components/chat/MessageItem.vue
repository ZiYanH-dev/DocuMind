<script setup lang="ts">

import { computed } from 'vue'

import type { MessageInfo } from '@/api/conversation'


const props = defineProps<{
  message: MessageInfo
}>()

const isUser = computed(() => props.message.role === 'user')

/** 格式化时间（时:分） */
function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div :class="['message-item', message.role]">
    <div class="message-avatar">
      {{ isUser ? '👤' : '🤖' }}
    </div>

    <div class="message-body">
      <div class="message-meta">
        <span class="message-role">{{ isUser ? '我' : 'AI 助手' }}</span>
        <span class="message-time">{{ formatTime(message.created_at) }}</span>
      </div>

      <div class="message-text">{{ message.content }}</div>

      <div v-if="message.sources && message.sources.length > 0" class="message-sources">
        <el-collapse>
          <el-collapse-item title="参考来源">
            <div
              v-for="(source, index) in message.sources"
              :key="index"
              class="source-item"
            >
              <div class="source-header">
                <strong>{{ source.document_title }}</strong>
                <span class="score">相关度: {{ (source.score * 100).toFixed(1) }}%</span>
              </div>
              <p class="source-snippet">{{ source.snippet }}</p>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-item {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message-item.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
  background: #e6e6e6;
}

.message-item.user .message-avatar {
  background: #409eff;
}

.message-body {
  max-width: 70%;
}

.message-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}

.message-item.user .message-meta {
  justify-content: flex-end;
}

.message-text {
  padding: 12px 16px;
  border-radius: 12px;
  background: #f5f5f5;
  line-height: 1.6;
  white-space: pre-wrap;
}

.message-item.user .message-text {
  background: #409eff;
  color: #fff;
}

.message-sources {
  margin-top: 8px;
}

.source-item {
  margin-bottom: 8px;
  font-size: 13px;
}

.source-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.source-header .score {
  color: #409eff;
}

.source-snippet {
  margin: 4px 0;
  color: #666;
  line-height: 1.4;
}
</style>
