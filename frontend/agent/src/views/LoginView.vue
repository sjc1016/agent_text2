<script setup lang="ts">
/** 坐席登录页（壳层变体 login：完全脱离 app-shell 全屏独立页）。
 * 登录表单与交互由后续 login 切片 issue 实现，本页仅承载壳层变体。 */
</script>

<template>
  <div data-testid="login-page" class="login-page">
    <div class="login-card">
      <div class="login-card__brand">
        <span class="login-card__logo" aria-hidden="true" />
        <h2 class="login-card__title">客服工作台</h2>
      </div>
      <p class="login-card__hint">请登录坐席工作台</p>
    </div>
  </div>
</template>

<style scoped>
/* 脱离壳层全屏独立页：surface-base 背景 + 垂直水平居中 Modal 弹层卡片（DESIGN.md §5.3）。 */
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f9fafb;
}

.login-card {
  width: 400px;
  padding: 24px;
  border-radius: 12px;
  box-shadow:
    0 10px 15px rgba(0, 0, 0, 0.1),
    0 4px 6px rgba(0, 0, 0, 0.05);
  background: #ffffff;
}

.login-card__brand {
  display: flex;
  align-items: center;
  gap: 8px;
}

.login-card__logo {
  width: 24px;
  height: 24px;
  border-radius: 5px;
  background: #1a6fff;
}

.login-card__title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.login-card__hint {
  margin: 24px 0 0;
  font-size: 14px;
  color: #6b7280;
}
</style>
