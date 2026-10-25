// 通用格式化工具
export function fmtNum(n) {
  if (n === null || n === undefined) return '0'
  n = Number(n)
  if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(2) + 'B'
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + 'M'
  if (Math.abs(n) >= 1e4) return (n / 1e3).toFixed(1) + 'k'
  return n.toLocaleString('zh-CN')
}

export function fmtMs(ms) {
  if (ms === null || ms === undefined) return '-'
  return `${Number(ms).toLocaleString('zh-CN')} ms`
}

export function fmtPct(v, digits = 1) {
  if (v === null || v === undefined || isNaN(v)) return '-'
  return `${Number(v).toFixed(digits)}%`
}

export function fmtTs(ts) {
  return ts || '-'
}

export function shortTs(ts) {
  if (!ts) return '-'
  return ts.length > 16 ? ts.slice(5, 16) : ts
}

export function copyText(text) {
  navigator.clipboard?.writeText(text)
}

// 简易 JSON 语法高亮（HTML 字符串）
export function highlightJson(obj) {
  let json
  try {
    json = typeof obj === 'string' ? JSON.stringify(JSON.parse(obj), null, 2) : JSON.stringify(obj, null, 2)
  } catch {
    return String(obj).replace(/</g, '&lt;')
  }
  return json
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"([^"\\]*(?:\\.[^"\\]*)*)"(\s*:)?/g, (m, s, colon) =>
      colon ? `<span class="json-key">"${s}"</span>${colon}` : `<span class="json-str">"${s}"</span>`)
    .replace(/\b(true|false)\b/g, '<span class="json-bool">$1</span>')
    .replace(/\bnull\b/g, '<span class="json-null">null</span>')
    .replace(/: ?(-?\d+\.?\d*(e[+-]?\d+)?)/gi, ': <span class="json-num">$1</span>')
}
