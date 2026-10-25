<script setup>
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogClose } from 'radix-vue'
import { X } from 'lucide-vue-next'

defineProps({
  open: Boolean,
  title: { type: String, default: '' },
  width: { type: String, default: '520px' }
})
defineEmits(['update:open'])
</script>

<template>
  <DialogRoot :open="open" @update:open="$emit('update:open', $event)">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-50 bg-black/45 backdrop-blur-[1px]" />
      <DialogContent :style="{ width, maxWidth: '94vw' }"
                     class="fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2 max-h-[88vh] overflow-y-auto
                            rounded-xl bg-card hairline shadow-subtle focus:outline-none">
        <div class="flex items-center justify-between px-5 pt-4 pb-3 border-b border-[var(--border)] sticky top-0 bg-card z-10">
          <DialogTitle class="text-[15px] font-semibold">{{ title }}</DialogTitle>
          <DialogClose class="p-1 rounded-md hover:bg-[var(--hover)] text-muted cursor-pointer">
            <X :size="16" />
          </DialogClose>
        </div>
        <div class="p-5">
          <slot />
        </div>
        <div v-if="$slots.footer" class="flex justify-end gap-2 px-5 pb-5">
          <slot name="footer" />
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
