<script setup>
defineProps({
  variant: { type: String, default: 'default' }, // default | accent | success | warning | error | info
  size: { type: String, default: 'default' }
})
const styles = {
  default: 'bg-[var(--hover)] text-muted',
  accent: 'bg-[var(--accent-soft)] text-[var(--accent)]',
  success: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  warning: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  error: 'bg-red-500/10 text-red-600 dark:text-red-400',
  info: 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
}
</script>

<template>
  <span class="inline-flex items-center gap-1 rounded-full font-medium"
        :class="[styles[variant], size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-0.5 text-xs']">
    <slot />
  </span>
</template>
