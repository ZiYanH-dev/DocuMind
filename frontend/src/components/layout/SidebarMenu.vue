<script setup lang="ts">

import { useRoute } from 'vue-router'


const route = useRoute()

const menuItems = [
  { path: '/chat', title: '智能问答', icon: 'ChatDotRound' },
  { path: '/documents', title: '知识库', icon: 'Folder' },
]
</script>

<template>
  <el-aside width="220px" class="aside">
    <div class="logo">
      <span class="logo-icon">🤖</span>
      <span class="logo-text">AI 学习助手</span>
    </div>

    <el-menu
      :default-active="route.path"
      router
      background-color="#1a1a2e"
      text-color="#b8b8d0"
      active-text-color="#409EFF"
    >
      <el-menu-item
        v-for="item in menuItems"
        :key="item.path"
        :index="item.path"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.title }}</span>
      </el-menu-item>
    </el-menu>
  </el-aside>
</template>

<style scoped>
.aside {
  background-color: #1a1a2e;
  transition: width 0.3s;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #fff;
  font-size: 18px;
  font-weight: bold;
  border-bottom: 1px solid #2a2a4a;
}

.logo-icon {
  font-size: 24px;
}

.el-menu {
  border-right: none;
}
</style>
