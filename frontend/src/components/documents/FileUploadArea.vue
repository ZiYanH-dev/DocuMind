<script setup lang="ts">

import { ref } from 'vue'
import { ElMessage, type UploadFile } from 'element-plus'


const emit = defineEmits<{
  upload: [file: File]
}>()

const allowedTypes: string[] = ['pdf', 'docx', 'txt']
const isDragging = ref(false)

/** 文件选择后校验并上抛 */
function handleFileChange(uploadFile: UploadFile): void {
  if (!validateFile(uploadFile)) return
  emit('upload', uploadFile.raw as File)
}

/** 校验文件类型与大小 */
function validateFile(file: UploadFile): boolean {
  const ext: string = file.name.split('.').pop()?.toLowerCase() || ''
  if (!allowedTypes.includes(ext)) {
    ElMessage.error(`只支持 ${allowedTypes.join(', ')} 格式的文件`)
    return false
  }
  const isLt50M: boolean = (file.size ?? 0) / 1024 / 1024 < 50
  if (!isLt50M) {
    ElMessage.error('文件大小不能超过 50MB')
    return false
  }
  return true
}

function onDragEnter(): void {
  isDragging.value = true
}

function onDragLeave(): void {
  isDragging.value = false
}
</script>

<template>
  <el-upload
    class="upload-area"
    drag
    :auto-upload="false"
    :show-file-list="false"
    :on-change="handleFileChange"
    :on-drag-enter="onDragEnter"
    :on-drag-leave="onDragLeave"
    multiple
  >
    <div :class="['upload-content', { dragging: isDragging }]">
      <el-icon class="upload-icon"><UploadFilled /></el-icon>
      <div class="upload-text">
        <p>将文件拖到此处，或<em>点击上传</em></p>
        <p class="upload-hint">支持 PDF、Word、TXT 格式，单个文件不超过 50MB</p>
      </div>
    </div>
  </el-upload>
</template>

<style scoped>
.upload-area {
  width: 100%;
}

.upload-content {
  padding: 40px;
  transition: all 0.3s;
}

.upload-content.dragging {
  background: #ecf5ff;
}

.upload-icon {
  font-size: 48px;
  color: #c0c4cc;
}

.upload-text {
  margin-top: 16px;
  color: #606266;
}

.upload-text em {
  color: #409eff;
  font-style: normal;
}

.upload-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
}
</style>
