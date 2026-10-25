<script setup>
defineProps({ icon: { type: [Object, Function], default: null }, message: { type: String, default: '暂无数据' } })
</script>

<template>
  <div class="flex flex-col items-center justify-center py-10 text-muted gap-2">
    <component :is="icon" v-if="icon" :size="28" class="opacity-40" />
    <p class="text-[13px]">{{ message }}</p>
    <slot />
  </div>
</template>
