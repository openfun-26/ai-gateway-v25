<script setup>
defineProps({
  variant: { type: String, default: 'default' }, // default | secondary | outline | ghost | destructive | accent-soft
  size: { type: String, default: 'default' }     // default | sm | icon
})
</script>

<template>
  <button
    class="inline-flex items-center justify-center gap-1.5 rounded-[0.55rem] text-[13px] font-medium transition-colors
           focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap"
    :class="{
      'bg-[var(--accent)] text-[var(--accent-fg)] hover:opacity-90': variant === 'default',
      'bg-[var(--hover)] text-content hover:opacity-80': variant === 'secondary',
      'hairline bg-card hover:bg-[var(--hover)]': variant === 'outline',
      'hover:bg-[var(--hover)]': variant === 'ghost',
      'bg-red-500/90 text-white hover:bg-red-500': variant === 'destructive',
      'bg-[var(--accent-soft)] text-[var(--accent)] hover:opacity-80': variant === 'accent-soft'
    }"
    :style="size === 'sm' ? 'height:28px;padding:0 10px;font-size:12px'
            : size === 'icon' ? 'height:30px;width:30px'
            : 'height:34px;padding:0 14px'">
    <slot />
  </button>
</template>
