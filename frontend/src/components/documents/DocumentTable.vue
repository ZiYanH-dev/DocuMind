<script setup lang="ts">

import { formatFileSize } from '@/utils/index'
import type { DocumentInfo } from '@/api/document'


defineProps<{
  documents: DocumentInfo[]
  loading?: boolean
  total?: number
}>()

const emit = defineEmits<{
  delete: [doc: DocumentInfo]
}>()

/** 获取状态标签类型 */
function getStatusType(status: string): string {
  const types: Record<string, string> = {
    completed: 'success',
    processing: 'warning',
    failed: 'danger',
    pending: 'info',
  }
  return types[status] || 'info'
}

/** 获取状态文本 */
function getStatusText(status: string): string {
  const texts: Record<string, string> = {
    completed: '已完成',
    processing: '处理中',
    failed: '失败',
    pending: '待处理',
  }
  return texts[status] || status
}
</script>

<template>
  <el-card class="document-list" v-loading="loading">
    <template #header>
      <div class="list-header">
        <span>文档列表</span>
        <el-tag type="info">共 {{ total }} 个文档</el-tag>
      </div>
    </template>

    <el-table :data="documents" stripe>
      <el-table-column prop="title" label="文档名称" min-width="200">
        <template #default="{ row }">
          <div class="doc-title">
            <el-icon><Document /></el-icon>
            <span>{{ row.title }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="file_type" label="类型" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.file_type === 'pdf' ? 'danger' : 'primary'">
            {{ row.file_type.toUpperCase() }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="file_size" label="大小" width="120" align="center">
        <template #default="{ row }">
          {{ formatFileSize(row.file_size) }}
        </template>
      </el-table-column>

      <el-table-column prop="status" label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)" size="small">
            {{ getStatusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="created_at" label="上传时间" width="180" align="center">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString('zh-CN') }}
        </template>
      </el-table-column>

      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button
            type="danger"
            size="small"
            text
            @click="emit('delete', row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="documents.length === 0 && !loading" description="暂无文档，开始上传吧！" />
  </el-card>
</template>

<style scoped>
.document-list {
  background: #fff;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.doc-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
