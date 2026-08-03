<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Hide, View } from '@element-plus/icons-vue'

import { AgentLoginError, agentLogin } from '../api/agents'
import { useAuthStore } from '../stores/auth'

/**
 * 坐席登录页（UI-A-2 / issue #18）。
 *
 * PRD login 条目：脱离 app-shell 全屏独立任务页（无顶栏无侧栏），垂直水平居中
 * Modal 弹层卡片（品牌 + 工号 + 密码明文切换 + 登录主按钮）。
 * 四态：default（聚焦 `shadow-focus` 环）/ error（`semantic-error 100` 环 + 「工号或密码错误」）/
 *       disabled（工号或密码为空主按钮禁用）/ loading（提交中禁用 + 白 spinner + 「登录中…」）。
 * 登录成功进入工作台待接入页（/queue）（US-19）；若带 redirect 参数（未登录被守卫
 * 拦截重定向而来），登录后跳回登录前想访问的目标路由（issue #58 验收标准 3）。
 */
const employeeId = ref('')
const password = ref('')
const showPassword = ref(false)
const focusedField = ref<'employeeId' | 'password' | ''>('')

/** 禁用变体：工号或密码为空时主按钮禁用（PRD login 变体段）。 */
const formValid = computed(() => employeeId.value !== '' && password.value !== '')

const router = useRouter()
const auth = useAuthStore()
const submitting = ref(false)
const loginError = ref('')

/** 登录成功跳转目标：redirect 查询参数（站内路径）优先，缺省回工作台待接入页 /queue。 */
function loginTarget(): string {
  const raw = router.currentRoute.value.query.redirect
  return typeof raw === 'string' && raw.startsWith('/') ? raw : '/queue'
}

/** 登录（US-19）：POST /agents/login → 写入凭证 → 跳回登录前目标路由（缺省 /queue）。 */
async function handleSubmit() {
  if (!formValid.value || submitting.value) return
  submitting.value = true
  loginError.value = ''
  try {
    const tokens = await agentLogin(employeeId.value, password.value)
    auth.setAuthenticated(
      { accessToken: tokens.access_token, refreshToken: tokens.refresh_token },
      employeeId.value,
    )
    await router.push(loginTarget())
  } catch (err) {
    loginError.value = err instanceof AgentLoginError ? err.message : '工号或密码错误'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div data-testid="login-page" class="login-page">
    <!-- Modal 弹层卡片：圆角 12px / shadow-lg / 内边距 24px / 宽 400px（DESIGN.md §5.3） -->
    <div data-testid="login-card" class="login-card">
      <div class="login-card__brand">
        <span class="login-card__logo" aria-hidden="true" />
        <h2 class="login-card__title">客服工作台</h2>
      </div>

      <form data-testid="login-form" novalidate @submit.prevent="handleSubmit">
        <div class="form-field">
          <label class="form-field__label" for="login-employee-id">
            工号<span class="form-field__required" aria-hidden="true">*</span>
          </label>
          <input
            id="login-employee-id"
            v-model="employeeId"
            data-testid="employee-id-input"
            class="text-input"
            :class="{
              'text-input--focus': focusedField === 'employeeId',
              'text-input--error': loginError !== '',
            }"
            type="text"
            autocomplete="username"
            placeholder="请输入工号"
            @focus="focusedField = 'employeeId'"
            @blur="focusedField = ''"
          />
        </div>

        <div class="form-field">
          <label class="form-field__label" for="login-password">
            密码<span class="form-field__required" aria-hidden="true">*</span>
          </label>
          <div class="password-wrap">
            <input
              id="login-password"
              v-model="password"
              data-testid="password-input"
              class="text-input password-wrap__input"
              :class="{
                'text-input--focus': focusedField === 'password',
                'text-input--error': loginError !== '',
              }"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              placeholder="请输入密码"
              @focus="focusedField = 'password'"
              @blur="focusedField = ''"
            />
            <button
              type="button"
              data-testid="password-toggle"
              class="password-wrap__toggle"
              :aria-label="showPassword ? '隐藏密码' : '显示密码'"
              @click="showPassword = !showPassword"
            >
              <el-icon :size="16" aria-hidden="true">
                <View v-if="!showPassword" />
                <Hide v-else />
              </el-icon>
            </button>
          </div>
        </div>

        <!-- 错误文案：semantic-error 500（DESIGN.md §5.2 错误态） -->
        <p v-if="loginError" data-testid="login-error" class="form-error">{{ loginError }}</p>

        <!-- 主按钮：40px 大号 Primary，空表单/提交中禁用；loading 白 spinner + 「登录中…」（PRD login / §5.1 / 状态策略） -->
        <button
          type="submit"
          data-testid="login-submit"
          class="login-submit"
          :disabled="!formValid || submitting"
        >
          <span
            v-if="submitting"
            data-testid="login-submit-spinner"
            class="login-submit__spinner"
          />
          <span>{{ submitting ? '登录中…' : '登录' }}</span>
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
/* 脱离壳层全屏独立任务页：surface-base（Neutral 50）+ 垂直水平居中（PRD login / 壳层变体）。 */
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f9fafb;
}

/* Modal 弹层卡片：圆角 12px / shadow-lg / 内边距 24px / 宽 400px（DESIGN.md §5.3）。 */
.login-card {
  width: 400px;
  padding: 24px;
  border-radius: 12px;
  background: #ffffff;
  box-shadow:
    0 10px 15px rgba(0, 0, 0, 0.1),
    0 4px 6px rgba(0, 0, 0, 0.05);
}

/* 品牌标识：Logo + 「客服工作台」，间距下 24px（PRD login）。 */
.login-card__brand {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 24px;
}

/* 品牌 Logo：电信蓝（Primary 500）圆角块，契合顶栏品牌标识。 */
.login-card__logo {
  width: 24px;
  height: 24px;
  border-radius: 5px;
  background: #1a6fff;
}

/* 品牌标题：H2 18px Neutral 800 600 字重（PRD login）。 */
.login-card__title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.form-field {
  margin-bottom: 16px;
}

.form-field__label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}

.form-field__required {
  margin-left: 2px;
  color: #e53935;
}

/* 输入框三态（DESIGN.md §5.2 输入与表单）：默认描边 / 聚焦 shadow-focus 环 / 错误 error 100 环。 */
.text-input {
  width: 100%;
  height: 36px;
  padding: 8px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #ffffff;
  font-size: 14px;
  color: #1f2937;
  box-sizing: border-box;
  transition:
    box-shadow 0.15s ease,
    border-color 0.15s ease;
}

.text-input::placeholder {
  color: #9ca3af;
}

.text-input:focus {
  outline: none;
}

/* 聚焦态：移除描边，改 shadow-focus 外发光环（Primary 100 #C9DEFF）。 */
.text-input--focus {
  border-color: transparent;
  box-shadow: 0 0 0 2px #c9deff;
}

/* 错误态：移除描边，改 semantic-error 100 环（#FFCDD2），聚焦时错误态优先。 */
.text-input--error,
.text-input--error.text-input--focus {
  border-color: transparent;
  box-shadow: 0 0 0 2px #ffcdd2;
}

.password-wrap {
  position: relative;
}

.password-wrap__input {
  padding-right: 40px;
}

/* 明文切换眼睛图标按钮（DESIGN.md §5.8 图标按钮紧凑尺寸）。 */
.password-wrap__toggle {
  position: absolute;
  top: 50%;
  right: 8px;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #4b5563;
  cursor: pointer;
}

.password-wrap__toggle:hover {
  background: #f3f4f6;
  color: #1f2937;
}

/* 主按钮「登录」：40px 大号、宽 100%、Primary 500 底白字、间距上 16px；禁用 Neutral 200 底（PRD login / §5.1）。 */
.login-submit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 40px;
  margin-top: 16px;
  padding: 0 20px;
  border: none;
  border-radius: 6px;
  background: #1a6fff;
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.login-submit:hover:not(:disabled) {
  background: #0d5be6;
}

.login-submit:active:not(:disabled) {
  background: #0a47b8;
}

.login-submit:disabled {
  background: #e5e7eb;
  color: #9ca3af;
  cursor: not-allowed;
}

/* 错误文案：semantic-error 500，字号 12px 字重 500，输入框下方间距 4px（DESIGN.md §5.2）。 */
.form-error {
  margin: -8px 0 16px;
  font-size: 12px;
  font-weight: 500;
  color: #e53935;
}

/* 按钮内白 spinner：24px、2.5px 描边（DESIGN.md §5 Loading 按钮内规格）。 */
.login-submit__spinner {
  width: 24px;
  height: 24px;
  border: 2.5px solid #ffffff;
  border-top-color: transparent;
  border-radius: 50%;
  animation: login-spin 1s linear infinite;
}

@keyframes login-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
