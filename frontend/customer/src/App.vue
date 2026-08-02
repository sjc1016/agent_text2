<script setup lang="ts">
import { RouterView } from 'vue-router'
import { useUiStore } from './stores/ui'

const ui = useUiStore()
</script>

<template>
  <RouterView />

  <div
    v-if="ui.routeLoading"
    data-testid="route-loading-overlay"
    class="route-loading-overlay"
  >
    <div data-testid="route-loading-spinner" class="route-loading-spinner" />
  </div>
</template>

<style scoped>
/* 全屏加载遮罩：neutral-overlay（DESIGN.md §4，Neutral 900 @ 50%）+ 32px Primary spinner（§5 Loading）。 */
.route-loading-overlay {
  position: fixed;
  inset: 0;
  background: rgba(17, 24, 39, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.route-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #1a6fff;
  border-top-color: transparent;
  border-radius: 50%;
  animation: route-loading-spin 1s linear infinite;
}

@keyframes route-loading-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
