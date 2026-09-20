/**
 * 文档相关 API。
 */

import { http } from './request'


/** 文档信息 */
export interface DocumentInfo {
  id: number
  title: string
  file_name: string
  file_size: number
  file_type: string
  status: string
  created_at: string
}

/** 文档列表 */
interface DocumentList {
  total: number
  items: DocumentInfo[]
}

/** 上传文档 */
export function uploadDocument(file: File, onProgress?: (progress: number) => void): Promise<DocumentInfo> {
  return http.upload<DocumentInfo>('/documents/upload', file, onProgress)
}

/** 获取文档列表 */
export function getDocumentList(skip: number = 0, limit: number = 20): Promise<DocumentList> {
  return http.get<DocumentList>('/documents', { params: { skip, limit } })
}

/** 删除文档 */
export function deleteDocument(id: number): Promise<void> {
  return http.delete<void>(`/documents/${id}`)
}
