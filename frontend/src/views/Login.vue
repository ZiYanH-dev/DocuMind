<script setup lang="ts">

import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'

import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useUserStore } from '@/stores/user'


const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const isLogin = ref(true)
const loading = ref(false)

interface LoginForm {
  username: string
  password: string
  email: string
}

const formRef = ref<FormInstance>()
const form = ref<LoginForm>({
  username: '',
  password: '',
  email: '',
})

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度为 3-50 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 128, message: '密码长度为 6-128 个字符', trigger: 'blur' },
  ],
  email: [
    { type: 'email', message: '请输入正确的邮箱地址', trigger: 'blur' },
  ],
}

/** 切换登录/注册模式 */
function toggleMode(): void {
  isLogin.value = !isLogin.value
  form.value = { username: '', password: '', email: '' }
}

/** 提交表单 */
async function handleSubmit(): Promise<void> {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (!valid) return

    loading.value = true
    try {
      if (isLogin.value) {
        await userStore.login(form.value.username, form.value.password)
        ElMessage.success('登录成功')
        const redirect: string = (route.query.redirect as string) || '/chat'
        router.push(redirect)
      } else {
        await userStore.register(
          form.value.username,
          form.value.password,
          form.value.email || undefined,
        )
        ElMessage.success('注册成功，请登录')
        toggleMode()
      }
    } catch (error) {
      // 错误已在拦截器中处理
    } finally {
      loading.value = false
    }
  })
}
</script>

<template>
  <div class="login-container">
    <div class="login-box">
      <h1 class="title">AI 学习助手</h1>
      <p class="subtitle">{{ isLogin ? '欢迎回来！' : '创建新账号' }}</p>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
        @submit.prevent="handleSubmit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>

        <el-form-item v-if="!isLogin" label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱（可选）" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            show-password
          />
        </el-form-item>

        <el-button
          type="primary"
          :loading="loading"
          class="submit-btn"
          @click="handleSubmit"
        >
          {{ isLogin ? '登 录' : '注 册' }}
        </el-button>
      </el-form>

      <p class="toggle-text">
        {{ isLogin ? '还没有账号？' : '已有账号？' }}
        <el-link type="primary" @click="toggleMode">
          {{ isLogin ? '立即注册' : '立即登录' }}
        </el-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-box {
  width: 420px;
  padding: 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

.title {
  text-align: center;
  margin: 0 0 8px;
  font-size: 28px;
  color: #333;
}

.subtitle {
  text-align: center;
  margin: 0 0 32px;
  color: #999;
}

.submit-btn {
  width: 100%;
  margin-top: 16px;
}

.toggle-text {
  text-align: center;
  margin-top: 24px;
  color: #666;
}
</style>
