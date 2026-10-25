<script setup>
defineProps({
  modelValue: [String, Number],
  options: { type: Array, default: () => [] } // [{value,label}] 或字符串数组
})
defineEmits(['update:modelValue'])
</script>

<template>
  <select :value="modelValue" @change="$emit('update:modelValue', $event.target.value)"
          class="h-9 w-full rounded-[0.55rem] bg-card px-2.5 text-[13px] hairline outline-none
                 focus:ring-2 focus:ring-[var(--accent)] cursor-pointer">
    <option v-for="opt in options" :key="typeof opt === 'string' ? opt : opt.value"
            :value="typeof opt === 'string' ? opt : opt.value">
      {{ typeof opt === 'string' ? opt : opt.label }}
    </option>
  </select>
</template>
