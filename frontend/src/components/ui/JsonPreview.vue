<script setup>
import { computed } from 'vue'
import { highlightJson } from './helpers'

const props = defineProps({ data: [Object, String], empty: { type: String, default: '（空）' } })
const html = computed(() => {
  const s = typeof props.data === 'string' ? props.data : (props.data ? JSON.stringify(props.data) : '')
  if (!s || s === 'null') return props.empty
  return highlightJson(s)
})
</script>

<template>
  <pre class="json-view rounded-card hairline p-3 bg-[var(--hover)] max-h-72 overflow-auto" v-html="html" />
</template>
