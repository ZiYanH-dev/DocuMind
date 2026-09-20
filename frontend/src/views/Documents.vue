<script setup lang="ts">

import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { getDocumentList, uploadDocument, deleteDocument, type DocumentInfo } from '@/api/document'
import FileUploadArea from '@/components/documents/FileUploadArea.vue'
import DocumentTable from '@/components/documents/DocumentTable.vue'


const documents = ref<DocumentInfo[]>([])
const total = ref(0)
const loading = ref(false)

/** 加载文档列表 */
async function loadDocuments(): Promise<void> {
  loading.value = true
  try {
    const result = await getDocumentList(0, 50)
    documents.value = result.items
    total.value = result.total
  } catch (error) {
    console.error('加载文档列表失败:', error)
  } finally {
    loading.value = false
  }
}

/** 上传文档 */
async function handleUpload(file: File): Promise<void> {
  try {
    await uploadDocument(file)
    ElMessage.success(`"${file.name}" 上传成功`)
    await loadDocuments()
  } catch (error) {
    console.error('上传失败:', error)
  }
}

/** 删除文档 */
async function handleDelete(doc: DocumentInfo): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定要删除文档 "${doc.title}" 吗？`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    await deleteDocument(doc.id)
    ElMessage.success('删除成功')
    await loadDocuments()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
    }
  }
}

onMounted(loadDocuments)
</script>

<template>
  <div class="documents-container">
    <FileUploadArea @upload="handleUpload" />

    <DocumentTable
      :documents="documents"
      :loading="loading"
      :total="total"
      @delete="handleDelete"
    />
  </div>
</template>

<style scoped>
.documents-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
</style>
