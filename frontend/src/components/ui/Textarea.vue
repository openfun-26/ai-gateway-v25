<script setup>
defineProps({
  modelValue: [String, Number],
  placeholder: { type: String, default: '' },
  rows: { type: Number, default: 4 },
  mono: Boolean
})
defineEmits(['update:modelValue'])
</script>

<template>
  <textarea :value="modelValue" :placeholder="placeholder" :rows="rows"
            @input="$emit('update:modelValue', $event.target.value)"
            class="w-full rounded-[0.55rem] bg-transparent px-3 py-2 text-[13px] hairline outline-none
                   focus:ring-2 focus:ring-[var(--accent)] placeholder:text-muted/60 transition resize-y"
            :class="mono ? 'font-mono text-xs leading-relaxed' : ''" />
</template>
