<script setup>
defineProps({
  modelValue: [String, Number],
  type: { type: String, default: 'text' },
  placeholder: { type: String, default: '' }
})
defineEmits(['update:modelValue'])
</script>

<template>
  <input :type="type" :value="modelValue" :placeholder="placeholder"
         @input="$emit('update:modelValue', $event.target.value)"
         class="h-9 w-full rounded-[0.55rem] bg-transparent px-3 text-[13px] hairline outline-none
                focus:ring-2 focus:ring-[var(--accent)] placeholder:text-muted/60 transition" />
</template>
