<script setup lang="ts">

import SidebarMenu from './SidebarMenu.vue'
import NavHeader from './NavHeader.vue'
</script>

<template>
  <el-container class="layout-container">
    <SidebarMenu />

    <el-container class="main-container">
      <NavHeader />

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout-container {
  height: 100vh;
}

.main-container {
  flex-direction: column;
}

.main {
  background: #f5f7fa;
  padding: 24px;
  overflow: auto;
}
</style>
