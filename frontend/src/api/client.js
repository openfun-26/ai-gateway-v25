// 统一 API 客户端：失败自动 toast
import { toast } from '../components/ui/toast'

async function request(method, url, body, opts = {}) {
  const cfg = {
    method,
    headers: { 'Content-Type': 'application/json' }
  }
  if (body !== undefined) cfg.body = JSON.stringify(body)
  let res
  try {
    res = await fetch(url, cfg)
  } catch (e) {
    if (!opts.silent) toast.error(`网络错误: ${e.message}`)
    throw e
  }
  const ct = res.headers.get('content-type') || ''
  const isJson = ct.includes('json')
  const data = isJson ? await res.json().catch(() => ({})) : await res.blob()
  if (!res.ok) {
    const msg = (isJson && (data?.error?.message || data?.detail || data?.error)) || `HTTP ${res.status}`
    if (!opts.silent) toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

export const api = {
  get: (url, opts) => request('GET', url, undefined, opts),
  post: (url, body, opts) => request('POST', url, body, opts),
  put: (url, body, opts) => request('PUT', url, body, opts),
  del: (url, body, opts) => request('DELETE', url, body, opts)
}

// 文件下载（CSV）
export async function downloadFile(url, filename) {
  try {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename
    a.click()
    URL.revokeObjectURL(a.href)
    toast.success(`已导出 ${filename}`)
  } catch (e) {
    toast.error(`下载失败: ${e.message}`)
  }
}

export function qs(params) {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== '' && v !== 'all') u.set(k, v)
  }
  const s = u.toString()
  return s ? `?${s}` : ''
}
