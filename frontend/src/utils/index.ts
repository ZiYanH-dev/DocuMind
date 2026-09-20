/**
 * 通用工具函数。
 */

/** 格式化日期 */
export function formatDate(dateStr: string | Date): string {
  const date: Date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr
  const year: number = date.getFullYear()
  const month: string = String(date.getMonth() + 1).padStart(2, '0')
  const day: string = String(date.getDate()).padStart(2, '0')
  const hour: string = String(date.getHours()).padStart(2, '0')
  const minute: string = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}`
}

/** 格式化文件大小 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** 防抖函数 */
export function debounce<T extends (...args: Parameters<T>) => void>(
  fn: T,
  delay: number = 300,
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout> | null = null
  return function (this: unknown, ...args: Parameters<T>): void {
    if (timer) {
      clearTimeout(timer)
    }
    timer = setTimeout(() => {
      fn.apply(this, args)
    }, delay)
  }
}

/** 节流函数 */
export function throttle<T extends (...args: Parameters<T>) => void>(
  fn: T,
  delay: number = 300,
): (...args: Parameters<T>) => void {
  let lastTime: number = 0
  return function (this: unknown, ...args: Parameters<T>): void {
    const now: number = Date.now()
    if (now - lastTime >= delay) {
      lastTime = now
      fn.apply(this, args)
    }
  }
}
