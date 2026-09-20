<script setup lang="ts">
import { useRouter } from 'vue-router'


const router = useRouter()

/** 返回首页 */
function goHome(): void {
  router.push('/')
}
</script>

<template>
  <div class="not-found-container">
    <div class="content">
      <h1 class="code">404</h1>
      <h2 class="message">抱歉，您访问的页面不存在</h2>
      <p class="description">请检查您输入的地址是否正确，或返回首页继续浏览</p>
      <el-button type="primary" size="large" @click="goHome">返回首页</el-button>
    </div>
  </div>
</template>

<style scoped>
.not-found-container {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #f5f7fa;
}

.content {
  text-align: center;
}

.code {
  font-size: 120px;
  margin: 0;
  color: #409EFF;
  font-weight: bold;
}

.message {
  font-size: 24px;
  color: #333;
  margin: 16px 0;
}

.description {
  color: #666;
  margin-bottom: 32px;
}
</style>
