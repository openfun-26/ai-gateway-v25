<script setup>
import { ref, onMounted, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { useUiStore, ACCENTS } from './stores/ui'
import ToastHost from './components/ui/ToastHost.vue'
import {
  LayoutDashboard, Boxes, Server, KeyRound, Split, ScrollText,
  Bug, Settings, Sun, Moon, Palette, Zap, Menu, X
} from 'lucide-vue-next'

const ui = useUiStore()
const route = useRoute()
const paletteOpen = ref(false)
const sidebarOpen = ref(false)

const navs = [
  { to: '/', label: '仪表盘总览', icon: LayoutDashboard },
  { to: '/models', label: '模型监控', icon: Boxes },
  { to: '/channels', label: '上游渠道', icon: Server },
  { to: '/keys', label: '客户端密钥', icon: KeyRound },
  { to: '/routing', label: '路由&分流', icon: Split },
  { to: '/logs', label: '调用日志', icon: ScrollText },
  { to: '/errors', label: '错误日志', icon: Bug },
  { to: '/settings', label: '系统设置', icon: Settings }
]

onMounted(() => ui.init())

// 移动端抽屉：路由切换后自动收起
watch(() => route.path, () => { sidebarOpen.value = false })
</script>

<template>
  <div class="flex h-full min-h-screen">
    <!-- 侧边栏 -->
    <aside class="w-52 shrink-0 border-r border-[var(--border)] bg-card flex flex-col max-lg:hidden">
      <div class="h-14 flex items-center gap-2.5 px-4 border-b border-[var(--border)]">
        <div class="h-7 w-7 rounded-lg bg-[var(--accent)] flex items-center justify-center text-[var(--accent-fg)]">
          <Zap :size="15" />
        </div>
        <div>
          <div class="text-[13.5px] font-bold leading-none">AI 聚合网关</div>
          <div class="text-[10px] text-muted mt-1">Multi-Protocol Gateway</div>
        </div>
      </div>
      <nav class="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        <RouterLink v-for="n in navs" :key="n.to" :to="n.to"
                    class="flex items-center gap-2.5 px-3 h-9 rounded-[0.55rem] text-[13px] transition-colors"
                    :class="route.path === n.to
                      ? 'bg-[var(--accent-soft)] text-[var(--accent)] font-semibold'
                      : 'text-muted hover:bg-[var(--hover)] hover:text-content'">
          <component :is="n.icon" :size="15.5" />
          {{ n.label }}
        </RouterLink>
      </nav>
      <div class="px-4 py-3 border-t border-[var(--border)] text-[10.5px] text-muted leading-relaxed">
        单进程 · 双协议 · SQLite WAL<br />FastAPI + Vue 3
      </div>
    </aside>

    <!-- 主区域 -->
    <div class="flex-1 flex flex-col min-w-0">
      <header class="h-14 shrink-0 border-b border-[var(--border)] bg-card/80 backdrop-blur flex items-center justify-between px-4 sm:px-5 sticky top-0 z-40">
        <div class="flex items-center gap-2 min-w-0">
          <!-- 移动端：汉堡菜单（桌面端隐藏，不影响原有布局） -->
          <button @click="sidebarOpen = true"
                  class="lg:hidden h-8 w-8 shrink-0 rounded-[0.55rem] hairline bg-card hover:bg-[var(--hover)] flex items-center justify-center text-muted cursor-pointer"
                  title="打开导航菜单">
            <Menu :size="17" />
          </button>
          <h1 class="text-[15px] font-semibold truncate">{{ route.meta.title }}</h1>
        </div>
        <div class="flex items-center gap-1.5">
          <!-- 自动刷新全局开关 -->
          <button @click="ui.setAutoRefresh(!ui.autoRefresh)"
                  class="h-8 px-2.5 rounded-[0.55rem] text-[12px] hairline flex items-center gap-1.5 transition cursor-pointer"
                  :class="ui.autoRefresh
                    ? 'bg-[var(--accent-soft)] text-[var(--accent)] border-transparent'
                    : 'bg-card text-muted hover:bg-[var(--hover)]'"
                  :title="ui.autoRefresh ? `自动刷新已开启（${ui.autoRefreshInterval}s）` : '自动刷新已关闭'">
            <Zap :size="13" />
            {{ ui.autoRefresh ? `自动 ${ui.autoRefreshInterval}s` : '自动刷新关' }}
          </button>
          <select v-if="ui.autoRefresh" :value="ui.autoRefreshInterval"
                  @change="ui.setAutoRefresh(true, parseInt($event.target.value))"
                  class="h-8 rounded-[0.55rem] bg-card hairline text-[12px] px-1.5 cursor-pointer">
            <option v-for="n in [5, 10, 15, 30, 60]" :key="n" :value="n">{{ n }}s</option>
          </select>
          <!-- 强调色 -->
          <div class="relative">
            <button @click="paletteOpen = !paletteOpen"
                    class="h-8 w-8 rounded-[0.55rem] hairline bg-card hover:bg-[var(--hover)] flex items-center justify-center text-muted cursor-pointer">
              <Palette :size="15" :style="{ color: `var(--accent)` }" />
            </button>
            <div v-if="paletteOpen" class="absolute right-0 top-9 z-50 rounded-xl bg-card hairline shadow-subtle p-2 grid grid-cols-3 gap-1.5 w-max">
              <button v-for="(a, key) in ACCENTS" :key="key" @click="ui.setAccent(key); paletteOpen = false"
                      class="flex flex-col items-center gap-1 px-2 py-1.5 rounded-lg hover:bg-[var(--hover)] cursor-pointer">
                <span class="h-5 w-5 rounded-full border border-black/10"
                      :style="{ background: a.color, outline: ui.accent === key ? `2px solid ${a.color}` : 'none', outlineOffset: '2px' }" />
                <span class="text-[10px] text-muted">{{ a.label }}</span>
              </button>
            </div>
          </div>
          <!-- 明暗切换 -->
          <button @click="ui.toggleTheme()"
                  class="h-8 w-8 rounded-[0.55rem] hairline bg-card hover:bg-[var(--hover)] flex items-center justify-center text-muted cursor-pointer">
            <Sun v-if="ui.theme === 'dark'" :size="15" />
            <Moon v-else :size="15" />
          </button>
        </div>
      </header>
      <main class="flex-1 px-4 py-4 sm:p-5 overflow-y-auto">
        <RouterView />
      </main>
    </div>

    <!-- 移动端抽屉导航（仅 <lg 显示，桌面端零影响） -->
    <Teleport to="body">
      <Transition name="gw-fade">
        <div v-if="sidebarOpen" class="fixed inset-0 bg-black/55 z-[60] lg:hidden" @click="sidebarOpen = false" />
      </Transition>
      <Transition name="gw-slide">
        <aside v-if="sidebarOpen"
               class="fixed top-0 left-0 bottom-0 w-64 max-w-[82vw] z-[61] bg-card border-r border-[var(--border)] flex flex-col lg:hidden">
          <div class="h-14 flex items-center gap-2.5 px-4 border-b border-[var(--border)]">
            <div class="h-7 w-7 rounded-lg bg-[var(--accent)] flex items-center justify-center text-[var(--accent-fg)]">
              <Zap :size="15" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-[13.5px] font-bold leading-none">AI 聚合网关</div>
              <div class="text-[10px] text-muted mt-1">Multi-Protocol Gateway</div>
            </div>
            <button @click="sidebarOpen = false"
                    class="h-8 w-8 rounded-[0.55rem] hover:bg-[var(--hover)] flex items-center justify-center text-muted cursor-pointer">
              <X :size="16" />
            </button>
          </div>
          <nav class="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
            <RouterLink v-for="n in navs" :key="n.to" :to="n.to"
                        class="flex items-center gap-2.5 px-3 h-11 rounded-[0.55rem] text-[14px] transition-colors"
                        :class="route.path === n.to
                          ? 'bg-[var(--accent-soft)] text-[var(--accent)] font-semibold'
                          : 'text-muted hover:bg-[var(--hover)] hover:text-content'">
              <component :is="n.icon" :size="17" />
              {{ n.label }}
            </RouterLink>
          </nav>
          <div class="px-4 py-3 border-t border-[var(--border)] text-[10.5px] text-muted leading-relaxed">
            单进程 · 双协议 · SQLite WAL<br />FastAPI + Vue 3
          </div>
        </aside>
      </Transition>
    </Teleport>
    <ToastHost />
  </div>
</template>
