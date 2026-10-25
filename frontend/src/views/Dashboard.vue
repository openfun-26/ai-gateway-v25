<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRouter } from 'vue-router'
import { api, downloadFile } from '../api/client'
import { useUiStore } from '../stores/ui'
import { toast } from '../components/ui/toast'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import RefreshButton from '../components/ui/RefreshButton.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import AlertBar from '../components/ui/AlertBar.vue'
import StatusDot from '../components/ui/StatusDot.vue'
import Badge from '../components/ui/Badge.vue'
import Select from '../components/ui/Select.vue'
import ConfirmDialog from '../components/ui/ConfirmDialog.vue'
import EChart from '../components/charts/EChart.vue'
import { fmtNum, fmtMs } from '../components/ui/helpers'
import {
  Activity, CalendarClock, XCircle, Coins, Zap, ArrowDownToLine, ArrowUpFromLine,
  Server, ServerOff, KeyRound, Gauge, Grid2x2, List, Trash2, ShieldAlert, Download, RotateCcw,
  Plus, Rocket, Copy
} from 'lucide-vue-next'

const router = useRouter()
const ui = useUiStore()

// ---------- 统计卡 ----------
const summary = ref({})
const sumLoading = ref(false)
async function loadSummary() {
  sumLoading.value = true
  try { summary.value = await api.get('/admin/api/dashboard/summary', { silent: true }) }
  finally { sumLoading.value = false }
}
const statCards = computed(() => {
  const s = summary.value
  return [
    { label: '总请求', value: fmtNum(s.total_requests), icon: Activity, color: '#3b82f6' },
    { label: '今日请求', value: fmtNum(s.today_requests), icon: CalendarClock, color: '#0ea5e9' },
    { label: '失败请求', value: fmtNum(s.failure_requests), icon: XCircle, color: '#ef4444' },
    { label: '总 Token', value: fmtNum(s.total_tokens), icon: Coins, color: '#8b5cf6' },
    { label: '今日 Token', value: fmtNum(s.today_tokens), icon: Coins, color: '#a855f7' },
    { label: '输入 Token', value: fmtNum(s.input_tokens), icon: ArrowDownToLine, color: '#14b8a6' },
    { label: '输出 Token', value: fmtNum(s.output_tokens), icon: ArrowUpFromLine, color: '#f59e0b' },
    { label: '在线渠道', value: fmtNum(s.online_channels), icon: Server, color: '#10b981' },
    { label: '离线渠道', value: fmtNum(s.offline_channels), icon: ServerOff, color: '#9ca3af' },
    { label: '有效密钥', value: fmtNum(s.valid_keys), icon: KeyRound, color: '#ec4899' },
    { label: '实时 QPS', value: fmtNum(s.qps_60s), icon: Gauge, color: '#06b6d4' },
    { label: '缓存命中率', value: fmtNum(s.cache_hit_rate) + '%', icon: Zap, color: '#14b8a6' }
  ]
})

// ---------- 告警 ----------
const alerts = ref([])
const alertLoading = ref(false)
async function loadAlerts() {
  alertLoading.value = true
  try { alerts.value = (await api.get('/admin/api/dashboard/alerts', { silent: true })).alerts }
  finally { alertLoading.value = false }
}
async function clearAlerts() {
  await api.post('/admin/api/dashboard/alerts/clear')
  toast.success('告警已清除')
  loadAlerts()
}

// ---------- 快速开始引导 ----------
const showGuide = computed(() => modelCards.value.length === 0)
const curlExample = computed(() =>
`curl http://${location.host}/v1/chat/completions \\
  -H "Authorization: Bearer sk-gw-你的密钥" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"你的模型别名","messages":[{"role":"user","content":"你好"}]}'`)
function fallbackCopy(text) {
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.cssText = 'position:fixed;opacity:0'
  document.body.appendChild(ta)
  ta.select()
  try { document.execCommand('copy'); toast.success('调用示例已复制到剪贴板') }
  catch { toast.warning('复制失败，请手动复制') }
  ta.remove()
}
async function copyExample() {
  if (navigator.clipboard && window.isSecureContext) {
    try { await navigator.clipboard.writeText(curlExample.value); return toast.success('调用示例已复制到剪贴板') } catch {}
  }
  fallbackCopy(curlExample.value)
}

// ---------- 快捷操作 ----------
const confirmState = ref({ open: false, title: '', message: '', action: null, danger: true })
function askConfirm(title, message, action) {
  confirmState.value = { open: true, title, message, action, danger: true }
}
async function runConfirm() {
  if (confirmState.value.action) await confirmState.value.action()
}
async function healthAll() {
  const r = await api.post('/admin/api/dashboard/health-check-all')
  if (r.started === false) return toast.warning(r.message || '检测任务已在进行中')
  toast.success('后台检测已启动，状态将陆续更新（无需等待）')
  loadModelCards()
}
async function resetStats() {
  await api.post('/admin/api/dashboard/reset-stats')
  toast.success('全部统计已重置')
  refreshAll()
}
async function clearLogs() {
  await api.post('/admin/api/dashboard/clear-logs')
  toast.success('普通日志已清空')
  loadMonitor()
}
async function resetCircuits() {
  await api.post('/admin/api/dashboard/reset-circuits')
  toast.success('熔断器冻结状态已全部重置')
}
function exportToday() {
  downloadFile('/admin/api/dashboard/export-today-csv', `today_logs_${new Date().toISOString().slice(0, 10)}.csv`)
}

// ---------- 模型状态网格 ----------
const modelCards = ref([])
const cardsLoading = ref(false)
const viewMode = ref('grid')
const sortBy = ref('status')
const vendorFilter = ref('all')
async function loadModelCards() {
  cardsLoading.value = true
  try { modelCards.value = await api.get('/admin/api/dashboard/model-cards', { silent: true }) }
  finally { cardsLoading.value = false }
}
const vendors = computed(() => [...new Set(modelCards.value.map(m => m.vendor_tag).filter(Boolean))])
const sortedCards = computed(() => {
  let arr = modelCards.value.filter(m => vendorFilter.value === 'all' || m.vendor_tag === vendorFilter.value)
  const rank = { online: 0, limited: 1, offline: 2, missing: 3, unknown: 4 }
  const key = sortBy.value
  arr = [...arr].sort((a, b) =>
    key === 'status' ? (rank[a.status] ?? 9) - (rank[b.status] ?? 9) || b.total_uses - a.total_uses
    : key === 'today' ? b.today_uses - a.today_uses
    : key === 'tokens' ? b.total_tokens - a.total_tokens
    : b.qps - a.qps)
  return arr
})
function goModel(model) {
  router.push({ path: '/models', query: { model } })
}

// ---------- 图表 ----------
const chartRange = ref('1h')
const charts = ref({})
const chartsLoading = ref(false)
async function loadCharts() {
  chartsLoading.value = true
  try { charts.value = await api.get(`/admin/api/dashboard/charts?range=${chartRange.value}`, { silent: true }) }
  finally { chartsLoading.value = false }
}

const reqOption = computed(() => {
  const d = charts.value.request_series || []
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['成功', '失败'], bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8 },
    grid: { left: 44, right: 16, top: 14, bottom: 40 },
    xAxis: { type: 'category', data: d.map(x => formatSlot(x.t)) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '成功', type: 'line', data: d.map(x => x.success), smooth: true, showSymbol: false,
        lineStyle: { width: 2 }, areaStyle: { opacity: 0.08 }, color: '#10b981' },
      { name: '失败', type: 'line', data: d.map(x => x.failure), smooth: true, showSymbol: false,
        lineStyle: { width: 2 }, color: '#ef4444' }
    ]
  }
})
const tokOption = computed(() => {
  const d = charts.value.token_series || []
  return {
    tooltip: { trigger: 'axis', valueFormatter: v => fmtNum(v) },
    legend: { data: ['输入', '输出'], bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8 },
    grid: { left: 52, right: 16, top: 14, bottom: 40 },
    xAxis: { type: 'category', data: d.map(x => formatSlot(x.t)) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '输入', type: 'line', data: d.map(x => x.input), smooth: true, showSymbol: false,
        areaStyle: { opacity: 0.08 }, color: '#14b8a6' },
      { name: '输出', type: 'line', data: d.map(x => x.output), smooth: true, showSymbol: false, color: '#f59e0b' }
    ]
  }
})
const hourOption = computed(() => {
  const d = charts.value.hour_dist || []
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 14, bottom: 26 },
    xAxis: { type: 'category', data: d.map(x => `${x.hour}时`) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{ type: 'bar', data: d.map(x => x.count), barMaxWidth: 18, itemStyle: { borderRadius: [4, 4, 0, 0] } }]
  }
})
function pieOption(data) {
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { type: 'scroll', orient: 'vertical', right: 0, top: 'middle', textStyle: { fontSize: 11 } },
    center: ['38%', '50%'],
    series: [{
      type: 'pie', radius: ['44%', '70%'], center: ['38%', '50%'],
      data: (data || []).map(x => ({ name: x.name, value: x.value })),
      label: { show: false }, emphasis: { label: { show: false } },
      itemStyle: { borderRadius: 4, borderWidth: 2, borderColor: 'var(--card)' }
    }]
  }
}
function formatSlot(t) {
  const d = new Date(t * 1000)
  const p = n => String(n).padStart(2, '0')
  const h = `${p(d.getHours())}:${p(d.getMinutes())}`
  return d.getHours() === 0 && d.getMinutes() === 0 ? `${p(d.getMonth() + 1)}/${p(d.getDate())} 0时` : h
}

// ---------- 实时监视器 ----------
const monitorRows = ref([])
const monitorLoading = ref(false)
async function loadMonitor() {
  monitorLoading.value = true
  try { monitorRows.value = (await api.get('/admin/api/dashboard/monitor?limit=50', { silent: true })).rows }
  finally { monitorLoading.value = false }
}
const statusBadge = s => ({
  success: 'success', failure: 'error', timeout: 'warning', rate_limited: 'warning',
  circuit_open: 'warning', blacklisted: 'error', auth_failed: 'error', ip_blocked: 'error',
  quota_exhausted: 'warning'
}[s] || 'default')
const statusLabel = s => ({
  success: '成功', failure: '失败', timeout: '超时', rate_limited: '限流', circuit_open: '熔断',
  blacklisted: '黑名单', auth_failed: '鉴权失败', ip_blocked: 'IP限制', quota_exhausted: '额度耗尽'
}[s] || s)

// ---------- 自动刷新 ----------
let timer = null
function setupTimer() {
  clearInterval(timer)
  if (ui.autoRefresh) {
    timer = setInterval(() => {
      loadSummary(); loadCharts(); loadMonitor(); loadModelCards(); loadAlerts()
    }, ui.autoRefreshInterval * 1000)
  }
}
function refreshAll() {
  loadSummary(); loadAlerts(); loadModelCards(); loadCharts(); loadMonitor()
}
onMounted(() => {
  refreshAll()
  setupTimer()
  window.addEventListener('gw-autorefresh-changed', setupTimer)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  window.removeEventListener('gw-autorefresh-changed', setupTimer)
})
</script>

<template>
  <div class="space-y-4 pb-8">
    <!-- 告警区 -->
    <div v-if="alerts.length" class="space-y-2">
      <div class="flex items-center justify-between">
        <h2 class="text-[13px] font-semibold text-muted flex items-center gap-1.5">
          <ShieldAlert :size="14" class="text-amber-500" /> 顶部告警（熔断 / 额度）
        </h2>
        <Button variant="ghost" size="sm" @click="clearAlerts">清除全部</Button>
      </div>
      <AlertBar v-for="(a, i) in alerts.slice(0, 20)" :key="i" :variant="a.type === 'circuit' ? 'error' : 'warning'">
        <span class="opacity-70 mr-2">{{ a.ts }}</span>{{ a.message }}
      </AlertBar>
    </div>

    <!-- 快速开始（无启用模型时显示） -->
    <Card v-if="showGuide">
      <template #header>
        <div class="flex items-center gap-2 text-[13px] font-semibold">
          <Rocket :size="15" class="text-[var(--accent)]" /> 快速开始 · 三步接入
        </div>
      </template>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div class="rounded-card hairline p-3.5">
          <div class="text-[11px] text-muted">第 1 步</div>
          <div class="text-[13.5px] font-semibold mt-0.5">添加上游渠道</div>
          <p class="text-[12px] text-muted mt-1 leading-relaxed">填写厂商 API 端点与密钥，内置常见厂商模板一键填充，创建后自动拉取模型。</p>
          <Button size="sm" class="mt-2.5" @click="router.push('/channels')"><Plus :size="13" /> 去添加渠道</Button>
        </div>
        <div class="rounded-card hairline p-3.5">
          <div class="text-[11px] text-muted">第 2 步</div>
          <div class="text-[13.5px] font-semibold mt-0.5">创建客户端密钥</div>
          <p class="text-[12px] text-muted mt-1 leading-relaxed">生成 sk-gw- 开头的密钥供客户端使用，可设置额度、有效期与模型权限。</p>
          <Button size="sm" variant="outline" class="mt-2.5" @click="router.push('/keys')"><KeyRound :size="13" /> 去创建密钥</Button>
        </div>
        <div class="rounded-card hairline p-3.5">
          <div class="text-[11px] text-muted">第 3 步</div>
          <div class="text-[13.5px] font-semibold mt-0.5">OpenAI 兼容调用</div>
          <p class="text-[12px] text-muted mt-1 leading-relaxed">任何 OpenAI / Claude SDK 把 Base URL 指向本网关即可开始使用。</p>
          <Button size="sm" variant="outline" class="mt-2.5" @click="copyExample"><Copy :size="13" /> 复制调用示例</Button>
        </div>
      </div>
    </Card>

    <!-- 统计卡 -->
    <div class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
      <Card v-for="c in statCards" :key="c.label" class="!p-0">
        <div class="flex items-center gap-3 px-4 py-3.5">
          <div class="h-9 w-9 rounded-lg flex items-center justify-center shrink-0"
               :style="{ background: c.color + '18', color: c.color }">
            <component :is="c.icon" :size="17" />
          </div>
          <div class="min-w-0">
            <div class="text-[11.5px] text-muted">{{ c.label }}</div>
            <div class="text-[17px] font-bold leading-tight truncate">{{ c.value }}</div>
          </div>
        </div>
      </Card>
    </div>

    <!-- 快捷按钮 -->
    <Card title="快捷操作">
      <template #header>
        <Badge variant="outline">网关版本 v20</Badge>
      </template>
      <div class="flex flex-wrap gap-2">
        <Button variant="accent-soft" @click="router.push('/channels')"><Plus :size="14" /> 添加渠道</Button>
        <Button variant="accent-soft" @click="router.push('/keys')"><KeyRound :size="14" /> 新建密钥</Button>
        <Button variant="accent-soft" @click="healthAll"><Activity :size="14" /> 一键全部渠道健康探测</Button>
        <Button variant="outline" @click="askConfirm('重置全部统计', '将清空所有统计与日志计数，且不可恢复。确认？', resetStats)"><RotateCcw :size="14" /> 重置全部统计</Button>
        <Button variant="outline" @click="askConfirm('清空普通日志', '将删除全部调用日志记录，确认？', clearLogs)"><Trash2 :size="14" /> 清空普通日志</Button>
        <Button variant="outline" @click="resetCircuits"><ShieldAlert :size="14" /> 重置所有熔断器</Button>
        <Button variant="outline" @click="exportToday"><Download :size="14" /> 导出今日日志 CSV</Button>
      </div>
    </Card>

    <!-- 模型状态概览 -->
    <Card>
      <template #header>
        <div class="flex flex-wrap items-center gap-2">
          <Select v-model="vendorFilter" :options="[{ value: 'all', label: '全部厂商' }, ...vendors.map(v => ({ value: v, label: v }))]" class="!w-32" />
          <Select v-model="sortBy" :options="[
            { value: 'status', label: '按状态排序' }, { value: 'qps', label: '按 QPS' },
            { value: 'today', label: '按今日调用' }, { value: 'tokens', label: '按 Token 总量' }]" class="!w-36" />
          <div class="flex rounded-[0.55rem] hairline overflow-hidden">
            <button class="px-2 h-8 flex items-center" :class="viewMode === 'grid' ? 'bg-[var(--accent-soft)] text-[var(--accent)]' : 'bg-card text-muted'"
                    @click="viewMode = 'grid'"><Grid2x2 :size="14" /></button>
            <button class="px-2 h-8 flex items-center border-l border-[var(--border)]" :class="viewMode === 'list' ? 'bg-[var(--accent-soft)] text-[var(--accent)]' : 'bg-card text-muted'"
                    @click="viewMode = 'list'"><List :size="14" /></button>
          </div>
          <RefreshButton :loading="cardsLoading" @refresh="loadModelCards" label="刷新" />
        </div>
      </template>
      <EmptyState v-if="!sortedCards.length" message="暂无启用中的模型，请先在渠道页添加并启用" />
      <!-- 网格模式 -->
      <div v-else-if="viewMode === 'grid'" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-3">
        <div v-for="m in sortedCards" :key="m.id" @click="goModel(m.display)"
             class="rounded-card hairline p-3.5 cursor-pointer transition hover:bg-[var(--hover)] group">
          <div class="flex items-center gap-2">
            <StatusDot :status="m.status" size="9"
                       :tooltip="`HTTP ${m.last_http_status ?? '-'} · ${fmtMs(m.latency_ms)} · 来源渠道: ${m.channel_name}`" />
            <span class="text-lg leading-none">{{ m.emoji || '🤖' }}</span>
            <span class="text-[13px] font-semibold truncate group-hover:text-[var(--accent)]">{{ m.display }}</span>
            <Badge size="sm" v-if="m.vendor_tag" class="ml-auto shrink-0">{{ m.vendor_tag }}</Badge>
          </div>
          <div class="grid grid-cols-4 gap-1 mt-3 text-center">
            <div><div class="text-[11px] text-muted">QPS</div><div class="text-[12.5px] font-semibold">{{ m.qps }}</div></div>
            <div><div class="text-[11px] text-muted">Token</div><div class="text-[12.5px] font-semibold">{{ fmtNum(m.total_tokens) }}</div></div>
            <div><div class="text-[11px] text-muted">命中</div><div class="text-[12.5px] font-semibold">{{ m.cache_hit_rate }}%</div></div>
            <div><div class="text-[11px] text-muted">今日</div><div class="text-[12.5px] font-semibold">{{ m.today_uses }}</div></div>
          </div>
        </div>
      </div>
      <!-- 列表模式 -->
      <div v-else class="overflow-x-auto">
        <table class="w-full text-[12.5px]">
          <thead>
            <tr class="text-left text-muted border-b border-[var(--border)]">
              <th class="py-2 font-medium">状态</th><th class="py-2 font-medium">模型</th>
              <th class="py-2 font-medium">厂商</th><th class="py-2 font-medium text-right">QPS</th>
              <th class="py-2 font-medium text-right">Token</th><th class="py-2 font-medium text-right">命中</th>
              <th class="py-2 font-medium text-right">总使用</th><th class="py-2 font-medium text-right">今日</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in sortedCards" :key="m.id" class="border-b border-[var(--border)]/60 hover:bg-[var(--hover)] cursor-pointer" @click="goModel(m.display)">
              <td class="py-2"><StatusDot :status="m.status" /></td>
              <td class="py-2 font-medium">{{ m.emoji }} {{ m.display }}</td>
              <td class="py-2">{{ m.vendor_tag || '-' }}</td>
              <td class="py-2 text-right">{{ m.qps }}</td>
              <td class="py-2 text-right">{{ fmtNum(m.total_tokens) }}</td>
              <td class="py-2 text-right">{{ m.cache_hit_rate }}%</td>
              <td class="py-2 text-right">{{ m.total_uses }}</td>
              <td class="py-2 text-right">{{ m.today_uses }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <!-- 五张图 -->
    <Card>
      <template #header>
        <div class="flex items-center gap-2">
          <Select v-model="chartRange" :options="['30m', '1h', '6h', '24h', '3d', '7d'].map(v => ({ value: v, label: v }))"
                  class="!w-24" @update:model-value="loadCharts" />
          <RefreshButton :loading="chartsLoading" @refresh="loadCharts" />
        </div>
      </template>
      <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div class="rounded-card hairline p-2">
          <div class="text-[12.5px] font-medium px-2 pt-1 pb-0.5">请求时序（成功 / 失败）</div>
          <EChart :option="reqOption" height="240px" />
        </div>
        <div class="rounded-card hairline p-2">
          <div class="text-[12.5px] font-medium px-2 pt-1 pb-0.5">Token 时序（输入 / 输出）</div>
          <EChart :option="tokOption" height="240px" />
        </div>
        <div class="rounded-card hairline p-2">
          <div class="text-[12.5px] font-medium px-2 pt-1 pb-0.5">每小时请求分布</div>
          <EChart :option="hourOption" height="240px" />
        </div>
        <div class="grid grid-cols-1 gap-4">
          <div class="rounded-card hairline p-2">
            <div class="text-[12.5px] font-medium px-2 pt-1 pb-0.5">渠道请求占比</div>
            <EChart v-if="(charts.channel_dist || []).length" :option="pieOption(charts.channel_dist)" height="220px" />
            <EmptyState v-else message="暂无渠道调用数据" />
          </div>
          <div class="rounded-card hairline p-2">
            <div class="text-[12.5px] font-medium px-2 pt-1 pb-0.5">模型调用占比</div>
            <EChart v-if="(charts.model_dist || []).length" :option="pieOption(charts.model_dist)" height="220px" />
            <EmptyState v-else message="暂无模型调用数据" />
          </div>
        </div>
      </div>
    </Card>

    <!-- 实时监视器 -->
    <Card title="实时请求监视器" subtitle="最近 50 条调用（含分流与反代）">
      <template #header>
        <RefreshButton :loading="monitorLoading" @refresh="loadMonitor" />
      </template>
      <div class="overflow-x-auto">
        <table class="w-full text-[12px] whitespace-nowrap">
          <thead>
            <tr class="text-left text-muted border-b border-[var(--border)]">
              <th v-for="h in ['类型', '协议', '时间', 'Key', '模型', '厂商', '耗时', 'P-Tok', 'C-Tok', '源IP', '状态', '渠道', '错误']"
                  :key="h" class="py-2 px-1.5 font-medium">{{ h }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in monitorRows" :key="r.id" class="border-b border-[var(--border)]/50 hover:bg-[var(--hover)]"
                :class="r.status !== 'success' ? 'row-failed' : ''">
              <td class="py-1.5 px-1.5"><Badge size="sm" :variant="r.request_type === 'proxy' ? 'info' : 'accent'">{{ r.request_type === 'proxy' ? '反代' : '分流' }}</Badge></td>
              <td class="px-1.5">{{ r.protocol }}</td>
              <td class="px-1.5 text-muted">{{ r.ts }}</td>
              <td class="px-1.5">{{ r.key_name || '-' }}</td>
              <td class="px-1.5 font-medium">{{ r.model || '-' }}</td>
              <td class="px-1.5">{{ r.vendor_tag || '-' }}</td>
              <td class="px-1.5">{{ fmtMs(r.latency_ms) }}</td>
              <td class="px-1.5">{{ r.prompt_tokens }}</td>
              <td class="px-1.5">{{ r.completion_tokens }}</td>
              <td class="px-1.5 text-muted">{{ r.source_ip }}</td>
              <td class="px-1.5"><Badge size="sm" :variant="statusBadge(r.status)">{{ statusLabel(r.status) }}</Badge></td>
              <td class="px-1.5">{{ r.channel || '-' }}</td>
              <td class="px-1.5 max-w-[180px] truncate text-red-500" :title="r.error">{{ r.error || '' }}</td>
            </tr>
            <tr v-if="!monitorRows.length"><td colspan="13"><EmptyState message="暂无调用记录" /></td></tr>
          </tbody>
        </table>
      </div>
    </Card>

    <ConfirmDialog v-model:open="confirmState.open" :title="confirmState.title" :message="confirmState.message"
                   @confirm="runConfirm" />
  </div>
</template>
