<script setup>
import { RefreshCw } from 'lucide-vue-next'

defineProps({ loading: Boolean, label: { type: String, default: '刷新' } })
defineEmits(['refresh'])
</script>

<template>
  <button @click="$emit('refresh')" :disabled="loading"
          class="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-[0.55rem] hairline bg-card text-[12px] text-muted
                 hover:bg-[var(--hover)] hover:text-content transition disabled:opacity-60 cursor-pointer">
    <RefreshCw :size="13" :class="loading ? 'animate-spin' : ''" />
    <span>{{ label }}</span>
  </button>
</template>
