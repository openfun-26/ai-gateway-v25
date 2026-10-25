<script setup>
defineProps({
  variant: { type: String, default: 'warning' }, // info | warning | error | success
  title: { type: String, default: '' }
})
defineEmits(['dismiss'])
const styles = {
  info: 'bg-blue-500/8 border-blue-500/25 text-blue-700 dark:text-blue-300',
  warning: 'bg-amber-500/8 border-amber-500/30 text-amber-700 dark:text-amber-300',
  error: 'bg-red-500/8 border-red-500/30 text-red-700 dark:text-red-300',
  success: 'bg-emerald-500/8 border-emerald-500/25 text-emerald-700 dark:text-emerald-300'
}
</script>

<template>
  <div class="flex items-start gap-2 rounded-card px-3.5 py-2.5 text-[13px] border" :class="styles[variant]">
    <div class="flex-1 leading-relaxed">
      <span v-if="title" class="font-semibold mr-1.5">{{ title }}</span>
      <slot />
    </div>
    <button v-if="$slots.actions || variant === 'warning'" @click="$emit('dismiss')"
            class="opacity-50 hover:opacity-100 shrink-0 cursor-pointer text-xs">✕</button>
    <div v-if="$slots.actions"><slot name="actions" /></div>
  </div>
</template>
