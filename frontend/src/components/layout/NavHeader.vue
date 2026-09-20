<script setup lang="ts">

import { useRoute, useRouter } from 'vue-router'

import { useUserStore } from '@/stores/user'


const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

/** 退出登录 */
function handleLogout(): void {
  userStore.logout()
  router.push('/login')
}
</script>

<template>
  <el-header class="header">
    <div class="header-left">
      <h2 class="page-title">{{ route.meta.title }}</h2>
    </div>

    <div class="header-right">
      <el-dropdown @command="handleLogout">
        <span class="user-info">
          <el-avatar :size="32" class="avatar">
            {{ userStore.userInfo?.username?.[0]?.toUpperCase() }}
          </el-avatar>
          <span class="username">{{ userStore.userInfo?.username }}</span>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              {{ userStore.userInfo?.email || '未绑定邮箱' }}
            </el-dropdown-item>
            <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </el-header>
</template>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
  padding: 0 24px;
}

.page-title {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.avatar {
  background: #409eff;
  color: #fff;
}

.username {
  color: #666;
}
</style>
