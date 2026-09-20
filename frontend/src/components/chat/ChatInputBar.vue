<script setup lang="ts">

import { computed } from 'vue'


const props = defineProps<{
  modelValue: string
  isGenerating?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
  stop: []
}>()

const text = computed({
  get: () => props.modelValue,
  set: (val: string) => emit('update:modelValue', val),
})

function handleKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    emit('send')
  }
}
</script>

<template>
  <div class="chat-input">
    <el-input
      v-model="text"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 6 }"
      :placeholder="placeholder || '输入你的问题，Enter 发送，Shift+Enter 换行'"
      :disabled="isGenerating"
      @keydown="handleKeydown"
    />

    <el-button
      v-if="!isGenerating"
      type="primary"
      :disabled="!text.trim()"
      @click="emit('send')"
    >
      发送
    </el-button>
    <el-button v-else type="danger" @click="emit('stop')">
      停止
    </el-button>
  </div>
</template>

<style scoped>
.chat-input {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #e6e6e6;
  background: #fff;
}

.chat-input .el-input {
  flex: 1;
}
</style>
