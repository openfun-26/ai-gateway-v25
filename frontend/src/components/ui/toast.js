// 轻量 toast 总线
import { reactive } from 'vue'

export const toastState = reactive({ list: [] })
let _id = 0

function push(type, message, duration = 3200) {
  const id = ++_id
  toastState.list.push({ id, type, message })
  setTimeout(() => {
    const i = toastState.list.findIndex(t => t.id === id)
    if (i > -1) toastState.list.splice(i, 1)
  }, duration)
}

export const toast = {
  success: (m) => push('success', m),
  error: (m) => push('error', m, 5000),
  info: (m) => push('info', m),
  warning: (m) => push('warning', m, 4200)
}
