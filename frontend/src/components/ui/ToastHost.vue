<script setup>
import { toastState } from './toast'
import { CheckCircle2, XCircle, Info, AlertTriangle } from 'lucide-vue-next'

const icons = { success: CheckCircle2, error: XCircle, info: Info, warning: AlertTriangle }
const colors = {
  success: 'text-emerald-500',
  error: 'text-red-500',
  info: 'text-blue-500',
  warning: 'text-amber-500'
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-[100] flex flex-col gap-2 w-80 max-w-[90vw]">
      <TransitionGroup name="toast">
        <div v-for="t in toastState.list" :key="t.id"
             class="flex items-start gap-2.5 rounded-card border-[var(--border)] bg-card p-3 shadow-subtle hairline">
          <component :is="icons[t.type]" :size="17" :class="colors[t.type]" class="mt-0.5 shrink-0" />
          <div class="text-[13px] leading-snug break-all">{{ t.message }}</div>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active { transition: all .25s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(16px); }
</style>
