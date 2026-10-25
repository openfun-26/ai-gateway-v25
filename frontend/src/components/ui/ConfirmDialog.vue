<script setup>
import Dialog from './Dialog.vue'
import Button from './Button.vue'

const props = defineProps({
  open: Boolean,
  title: { type: String, default: '确认操作' },
  message: { type: String, default: '确定执行此操作吗？' },
  danger: Boolean
})
const emit = defineEmits(['update:open', 'confirm'])

function onConfirm() {
  emit('confirm')
  emit('update:open', false)
}
</script>

<template>
  <Dialog :open="open" :title="title" width="400px" @update:open="$emit('update:open', $event)">
    <p class="text-[13px] text-muted leading-relaxed">{{ message }}</p>
    <template #footer>
      <Button variant="outline" @click="$emit('update:open', false)">取消</Button>
      <Button :variant="danger ? 'destructive' : 'default'" @click="onConfirm">确认</Button>
    </template>
  </Dialog>
</template>
