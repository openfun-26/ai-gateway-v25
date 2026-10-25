<script setup>
// radix-vue 1.x SwitchRoot 的受控 prop 是 checked（非 modelValue）、
// 事件是 update:checked（非 update:modelValue）。此处做适配：
// 对外仍暴露 modelValue / update:modelValue 契约，内部加乐观翻转，
// 点击即时响应，外部数据回流后自动校正。
import { ref, watch } from 'vue'
import { SwitchRoot, SwitchThumb } from 'radix-vue'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue'])

const local = ref(props.modelValue)
watch(() => props.modelValue, v => { local.value = v })

function onToggle(v) {
  local.value = v
  emit('update:modelValue', v)
}
</script>

<template>
  <SwitchRoot :checked="local" @update:checked="onToggle"
              class="relative h-5 w-9 shrink-0 rounded-full transition-colors outline-none
                     data-[state=unchecked]:bg-[var(--border)] data-[state=checked]:bg-[var(--accent)] cursor-pointer">
    <SwitchThumb class="block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow transition-transform
                        data-[state=checked]:translate-x-[18px]" />
  </SwitchRoot>
</template>
