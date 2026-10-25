<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'unknown' }, // online/offline/limited/missing/unknown/running/stopped/error/running-yellow
  tooltip: { type: String, default: '' },
  size: { type: Number, default: 8 }
})

const colorMap = {
  online: '#10b981', running: '#10b981',
  offline: '#ef4444', error: '#ef4444',
  limited: '#f59e0b', timeout: '#f59e0b', pending: '#f59e0b',
  missing: '#9ca3af', stopped: '#eab308',
  unknown: '#9ca3af'
}

const color = computed(() => colorMap[props.status] || '#9ca3af')
</script>

<template>
  <span class="inline-flex items-center gap-1.5 align-middle" :title="tooltip || status">
    <span class="relative inline-flex shrink-0" :style="{ width: size + 4 + 'px', height: size + 4 + 'px' }">
      <span class="absolute inset-0 rounded-full opacity-25 animate-pulse" :style="{ background: color }"
            v-if="['online', 'running'].includes(status)" />
      <span class="absolute rounded-full" :style="{ background: color, width: size + 'px', height: size + 'px', inset: '2px' }" />
    </span>
    <slot />
  </span>
</template>
