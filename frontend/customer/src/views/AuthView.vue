<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Hide, View } from '@element-plus/icons-vue'

import { AuthError, login } from '../api/auth'
import { useSessionStore } from '../stores/session'

/**
 * 服务密码认证页（UI-C-2 / issue #8）。
 *
 * PRD auth 条目：脱离 app-shell 全屏独立任务页（无顶栏无底栏），垂直水平居中
 * Modal 弹层卡片（品牌 + 辅助文案 + 手机号 + 服务密码 + 认证主按钮 + 暂不认证文字按钮）。
 * 四态：default（聚焦 `shadow-focus` 环）/ error（`semantic-error 100` 环 + 文案）/
 *       disabled（手机号未满 11 位主按钮禁用）/ loading（提交中禁用 + 白 spinner + 「认证中…」）。
 */
const router = useRouter()
const session = useSessionStore()

const phone = ref('')
const servicePassword = ref('')
const showPassword = ref(false)
const focusedField = ref<'phone' | 'password' | ''>('')
const submitting = ref(false)
const loginError = ref('')

/** 手机号 11 位数字校验（PRD 禁用变体：未满 11 位主按钮禁用）。 */
const phoneValid = computed(() => /^\d{11}$/.test(phone.value))

async function handleSubmit() {
  if (!phoneValid.value || submitting.value) return
  submitting.value = true
  loginError.value = ''
  try {
    const tokens = await login(phone.value, servicePassword.value)
    session.setAuthenticated(
      { accessToken: tokens.access_token, refreshToken: tokens.refresh_token },
      phone.value,
    )
    await router.push('/chat')
  } catch (err) {
    loginError.value = err instanceof AuthError ? err.message : '手机号或服务密码错误'
  } finally {
    submitting.value = false
  }
}

/** 「暂不认证，先咨询」：返回会话页，保持访客身份（US-2 第二路径）。 */
function handleSkip() {
  void router.push('/chat')
}
</script>

<template>
  <div data-testid="auth-view" class="auth-page">
    <!-- Modal 弹层卡片：圆角 12px / shadow-lg / 内边距 24px / 宽 400px（DESIGN.md §5.3） -->
    <div data-testid="auth-card" class="auth-card">
      <div class="auth-card__brand">
        <span class="auth-card__logo" aria-hidden="true" />
        <h2 class="auth-card__title">电信客服</h2>
      </div>
      <p class="auth-card__hint">请输入服务密码以查询和办理业务</p>

      <form data-testid="auth-form" novalidate @submit.prevent="handleSubmit">
        <div class="form-field">
          <label class="form-field__label" for="auth-phone">
            手机号<span class="form-field__required" aria-hidden="true">*</span>
          </label>
          <input
            id="auth-phone"
            v-model="phone"
            data-testid="phone-input"
            class="text-input"
            :class="{
              'text-input--focus': focusedField === 'phone',
              'text-input--error': loginError !== '',
            }"
            type="tel"
            maxlength="11"
            autocomplete="tel"
            placeholder="请输入 11 位手机号"
            @focus="focusedField = 'phone'"
            @blur="focusedField = ''"
          />
        </div>

        <div class="form-field">
          <label class="form-field__label" for="auth-password">
            服务密码<span class="form-field__required" aria-hidden="true">*</span>
          </label>
          <div class="password-wrap">
            <input
              id="auth-password"
              v-model="servicePassword"
              data-testid="password-input"
              class="text-input password-wrap__input"
              :class="{
                'text-input--focus': focusedField === 'password',
                'text-input--error': loginError !== '',
              }"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              placeholder="请输入服务密码"
              @focus="focusedField = 'password'"
              @blur="focusedField = ''"
            />
            <button
              type="button"
              data-testid="password-toggle"
              class="password-wrap__toggle"
              :aria-label="showPassword ? '隐藏服务密码' : '显示服务密码'"
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
        <p v-if="loginError" data-testid="auth-error" class="form-error">{{ loginError }}</p>

        <!-- 主按钮：40px 大号 Primary，loading 禁用 + 白 spinner（24px）+ 「认证中…」 -->
        <button
          type="submit"
          data-testid="auth-submit"
          class="auth-submit"
          :disabled="!phoneValid || submitting"
        >
          <span v-if="submitting" data-testid="auth-submit-spinner" class="auth-submit__spinner" />
          <span>{{ submitting ? '认证中…' : '认证' }}</span>
        </button>

        <!-- 文字按钮（DESIGN.md §5.1 Text） -->
        <button type="button" data-testid="auth-skip" class="auth-skip" @click="handleSkip">
          暂不认证，先咨询
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
/* 脱离壳层全屏独立任务页：surface-base（Neutral 50）+ 垂直水平居中（PRD auth / 壳层变体）。 */
.auth-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f9fafb;
}

/* Modal 弹层卡片：圆角 12px / shadow-lg / 内边距 24px / 宽 400px（DESIGN.md §5.3）。 */
.auth-card {
  width: 400px;
  padding: 24px;
  border-radius: 12px;
  background: #ffffff;
  box-shadow:
    0 10px 15px rgba(0, 0, 0, 0.1),
    0 4px 6px rgba(0, 0, 0, 0.05);
}

.auth-card__brand {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

/* 品牌 Logo：电信蓝（Primary 500）圆角块，契合顶栏品牌标识。 */
.auth-card__logo {
  width: 24px;
  height: 24px;
  border-radius: 5px;
  background: #1a6fff;
}

/* 品牌标题：H2 18px Neutral 800 600 字重（PRD auth）。 */
.auth-card__title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

/* 辅助文案：Body-sm 13px Neutral 500，间距下 24px（PRD auth）。 */
.auth-card__hint {
  margin: 0 0 24px;
  font-size: 13px;
  color: #6b7280;
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

/* 错误文案：semantic-error 500，字号 12px 字重 500，输入框下方间距 4px（DESIGN.md §5.2）。 */
.form-error {
  margin: -8px 0 16px;
  font-size: 12px;
  font-weight: 500;
  color: #e53935;
}

/* 主按钮「认证」：40px 大号、宽 100%、Primary 500 底白字、间距上 16px；禁用 Neutral 200 底（PRD auth / §5.1）。 */
.auth-submit {
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

.auth-submit:hover:not(:disabled) {
  background: #0d5be6;
}

.auth-submit:active:not(:disabled) {
  background: #0a47b8;
}

.auth-submit:disabled {
  background: #e5e7eb;
  color: #9ca3af;
  cursor: not-allowed;
}

/* 按钮内白 spinner：24px、2.5px 描边（DESIGN.md §5 Loading 按钮内规格）。 */
.auth-submit__spinner {
  width: 24px;
  height: 24px;
  border: 2.5px solid #ffffff;
  border-top-color: transparent;
  border-radius: 50%;
  animation: auth-spin 1s linear infinite;
}

/* 文字按钮「暂不认证，先咨询」：居中 Primary 500 文字，间距上 12px（PRD auth / §5.1 Text）。 */
.auth-skip {
  display: block;
  margin: 12px auto 0;
  padding: 4px 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #1a6fff;
  font-size: 14px;
  cursor: pointer;
}

.auth-skip:hover {
  background: #f4f8ff;
  color: #0d5be6;
}

.auth-skip:active {
  background: #e0ebff;
  color: #0a47b8;
}

@keyframes auth-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
