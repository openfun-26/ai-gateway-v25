<script setup>
defineProps({ title: String, subtitle: String })
</script>

<template>
  <div class="rounded-card bg-card shadow-subtle hairline">
    <div v-if="title || $slots.header || subtitle" class="px-4 py-3 flex items-center justify-between gap-3"
         :class="$slots.header ? '' : 'border-b border-[var(--border)]'">
      <div>
        <h3 class="text-[14px] font-semibold leading-tight">{{ title }}</h3>
        <p v-if="subtitle" class="text-xs text-muted mt-0.5">{{ subtitle }}</p>
      </div>
      <div class="flex items-center gap-2">
        <slot name="header" />
      </div>
    </div>
    <div class="p-4">
      <slot />
    </div>
  </div>
</template>
