import { defineStore } from 'pinia'

export const ACCENTS = {
  teal:   { label: '青绿',   color: '#14b8a6', softLight: 'rgba(20,184,166,.12)',  softDark: 'rgba(20,184,166,.20)' },
  blue:   { label: '蓝',     color: '#3b82f6', softLight: 'rgba(59,130,246,.12)',  softDark: 'rgba(59,130,246,.20)' },
  purple: { label: '紫',     color: '#8b5cf6', softLight: 'rgba(139,92,246,.12)',  softDark: 'rgba(139,92,246,.20)' },
  amber:  { label: '琥珀',   color: '#f59e0b', softLight: 'rgba(245,158,11,.14)',  softDark: 'rgba(245,158,11,.22)' },
  rose:   { label: '玫红',   color: '#f43f5e', softLight: 'rgba(244,63,94,.12)',   softDark: 'rgba(244,63,94,.20)' },
  slate:  { label: '石板灰蓝', color: '#64748b', softLight: 'rgba(100,116,139,.14)', softDark: 'rgba(100,116,139,.22)' }
}

function applyAccent(key) {
  const a = ACCENTS[key] || ACCENTS.teal
  const root = document.documentElement
  root.style.setProperty('--accent', a.color)
  root.style.setProperty('--accent-soft', document.documentElement.classList.contains('dark') ? a.softDark : a.softLight)
}

export const useUiStore = defineStore('ui', {
  state: () => ({
    theme: localStorage.getItem('gw_theme') || 'light',
    accent: localStorage.getItem('gw_accent') || 'teal',
    // 自动刷新全局总开关（默认关）+ 间隔
    autoRefresh: localStorage.getItem('gw_auto') === '1',
    autoRefreshInterval: parseInt(localStorage.getItem('gw_auto_interval') || '10', 10),
    sidebarCollapsed: false
  }),
  actions: {
    init() {
      this.applyTheme(this.theme)
      applyAccent(this.accent)
    },
    applyTheme(t) {
      this.theme = t
      document.documentElement.classList.toggle('dark', t === 'dark')
      localStorage.setItem('gw_theme', t)
      applyAccent(this.accent)
      window.dispatchEvent(new CustomEvent('gw-theme-changed'))
    },
    toggleTheme() {
      this.applyTheme(this.theme === 'dark' ? 'light' : 'dark')
    },
    setAccent(key) {
      this.accent = key
      localStorage.setItem('gw_accent', key)
      applyAccent(key)
      window.dispatchEvent(new CustomEvent('gw-accent-changed'))
    },
    setAutoRefresh(on, interval) {
      this.autoRefresh = on
      if (interval) this.autoRefreshInterval = interval
      localStorage.setItem('gw_auto', on ? '1' : '0')
      localStorage.setItem('gw_auto_interval', String(this.autoRefreshInterval))
      window.dispatchEvent(new CustomEvent('gw-autorefresh-changed'))
    }
  }
})
