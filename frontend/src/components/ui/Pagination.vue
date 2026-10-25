<script setup>
import { computed } from 'vue'

const props = defineProps({
  page: { type: Number, default: 1 },
  total: { type: Number, default: 0 },
  size: { type: Number, default: 50 }
})
const emit = defineEmits(['change'])
const pages = computed(() => Math.max(1, Math.ceil(props.total / props.size)))
</script>

<template>
  <div class="flex items-center justify-between pt-3 text-[12px] text-muted">
    <span>共 {{ total.toLocaleString('zh-CN') }} 条 · 第 {{ page }}/{{ pages }} 页</span>
    <div class="flex items-center gap-1.5">
      <button class="px-2 h-7 rounded-md hairline bg-card hover:bg-[var(--hover)] disabled:opacity-40 cursor-pointer"
              :disabled="page <= 1" @click="emit('change', page - 1)">上一页</button>
      <button class="px-2 h-7 rounded-md hairline bg-card hover:bg-[var(--hover)] disabled:opacity-40 cursor-pointer"
              :disabled="page >= pages" @click="emit('change', page + 1)">下一页</button>
    </div>
  </div>
</template>
