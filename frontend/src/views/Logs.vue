<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { api, downloadFile, qs } from '../api/client'
import { useUiStore } from '../stores/ui'
import { toast } from '../components/ui/toast'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import Input from '../components/ui/Input.vue'
import Select from '../components/ui/Select.vue'
import Badge from '../components/ui/Badge.vue'
import RefreshButton from '../components/ui/RefreshButton.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import Pagination from '../components/ui/Pagination.vue'
import Dialog from '../components/ui/Dialog.vue'
import ConfirmDialog from '../components/ui/ConfirmDialog.vue'
import JsonPreview from '../components/ui/JsonPreview.vue'
import { Eye, Trash2, Download } from 'lucide-vue-next'

const ui = useUiStore()
const rows = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const selected = ref([])
const confirmState = ref({ open: false, title: '', message: '', action: null })
const filters = ref({ start: '', end: '', key_name: '', model: '', vendor: '', channel: '', request_type: 'all', status: 'all', q: '' })

async function load() {
  loading.value = true
  try {
    const r = await api.get(`/admin/api/logs${qs({ ...filters.value, page: page.value, size: 50 })}`, { silent: true })
    rows.value = r.rows
    total.value = r.total
  } finally { loading.value = false }
}
function doSearch() { page.value = 1; load() }

const statusVariant = s => ({ success: 'success', failure: 'error', timeout: 'warning', rate_limited: 'warning',
  circuit_open: 'warning', blacklisted: 'error', auth_failed: 'error', ip_blocked: 'error' }[s] || 'default')
const statusText = s => ({ success: '成功', failure: '失败', timeout: '超时', rate_limited: '限流', circuit_open: '熔断',
  blacklisted: '黑名单', auth_failed: '鉴权失败', ip_blocked: 'IP限制' }[s] || s)

// payload 预览
const previewDlg = ref({ open: false, log: null })
async function openPreview(row) {
  const r = await api.get(`/admin/api/logs/${row.id}`)
  previewDlg.value = { open: true, log: r.log }
}

async function deleteOne(row) {
  await api.del(`/admin/api/logs/${row.id}`)
  toast.success('已删除')
  load()
}
function askClearAll() {
  confirmState.value = { open: true, title: '清空全部日志', message: '将删除全部调用日志（含反代日志），确认？',
    action: async () => { await api.del('/admin/api/logs'); toast.success('已清空'); load() } }
}
async function batchDelete() {
  if (!selected.value.length) return toast.warning('请先勾选日志行')
  await api.post('/admin/api/logs/batch-delete', { ids: selected.value })
  toast.success(`已删除 ${selected.value.length} 条`)
  selected.value = []
  load()
}
function exportCsv() {
  downloadFile(`/admin/api/logs/export-csv${qs({ ...filters.value })}`, `logs_${Date.now()}.csv`)
}

let timer = null
function setupTimer() {
  clearInterval(timer)
  if (ui.autoRefresh) timer = setInterval(load, ui.autoRefreshInterval * 1000)
}
onMounted(() => { load(); setupTimer(); window.addEventListener('gw-autorefresh-changed', setupTimer) })
onBeforeUnmount(() => { clearInterval(timer); window.removeEventListener('gw-autorefresh-changed', setupTimer) })
</script>

<template>
  <div class="space-y-4 pb-8">
    <Card title="调用日志" subtitle="分流 + 反代全量请求，点击行预览原始 payload">
      <template #header>
        <div class="flex flex-wrap items-center gap-2">
          <label class="flex items-center gap-1.5 text-[12px] text-muted cursor-pointer">
            自动刷新 <input type="checkbox" class="accent-[var(--accent)]" :checked="ui.autoRefresh"
              @change="ui.setAutoRefresh($event.target.checked)" />
          </label>
          <RefreshButton :loading="loading" @refresh="load" />
        </div>
      </template>

      <!-- 筛选 -->
      <div class="flex flex-wrap items-end gap-2 mb-3 text-[13px]">
        <div><label class="text-[11px] text-muted">开始日期</label><Input v-model="filters.start" type="date" class="!w-36" /></div>
        <div><label class="text-[11px] text-muted">结束日期</label><Input v-model="filters.end" type="date" class="!w-36" /></div>
        <div><label class="text-[11px] text-muted">Key 备注</label><Input v-model="filters.key_name" class="!w-28" placeholder="精确匹配" /></div>
        <div><label class="text-[11px] text-muted">模型</label><Input v-model="filters.model" class="!w-32" /></div>
        <div><label class="text-[11px] text-muted">厂商</label><Input v-model="filters.vendor" class="!w-24" /></div>
        <div><label class="text-[11px] text-muted">渠道</label><Input v-model="filters.channel" class="!w-28" /></div>
        <div><label class="text-[11px] text-muted">类型</label>
          <Select v-model="filters.request_type" class="!w-24" :options="[{ value: 'all', label: '全部' }, { value: 'forward', label: '分流' }, { value: 'proxy', label: '反代' }]" /></div>
        <div><label class="text-[11px] text-muted">状态</label>
          <Select v-model="filters.status" class="!w-28" :options="[
            { value: 'all', label: '全部' }, { value: 'success', label: '成功' }, { value: 'failure', label: '失败' },
            { value: 'timeout', label: '超时' }, { value: 'rate_limited', label: '限流' }, { value: 'blacklisted', label: '黑名单' },
            { value: 'auth_failed', label: '鉴权失败' }]" /></div>
        <div><label class="text-[11px] text-muted">关键字</label><Input v-model="filters.q" class="!w-40" placeholder="错误/payload…" /></div>
        <Button size="sm" @click="doSearch">筛选</Button>
      </div>

      <div v-if="selected.length" class="flex items-center gap-2 mb-2">
        <Badge variant="accent">已选 {{ selected.length }}</Badge>
        <Button size="sm" variant="destructive" @click="batchDelete"><Trash2 :size="13" /> 批量删除选中</Button>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-[12px] whitespace-nowrap">
          <thead>
            <tr class="text-left text-muted border-b border-[var(--border)]">
              <th class="py-2 w-8"><input type="checkbox" class="accent-[var(--accent)] cursor-pointer"
                  @change="selected = $event.target.checked ? rows.map(r => r.id) : []" /></th>
              <th class="py-2 px-1.5">时间</th><th class="py-2 px-1.5">类型</th><th class="py-2 px-1.5">协议</th>
              <th class="py-2 px-1.5">Key</th><th class="py-2 px-1.5">模型</th><th class="py-2 px-1.5">厂商</th>
              <th class="py-2 px-1.5">源IP</th><th class="py-2 px-1.5">渠道</th>
              <th class="py-2 px-1.5 text-right">耗时</th><th class="py-2 px-1.5 text-right">P-Tok</th>
              <th class="py-2 px-1.5 text-right">C-Tok</th><th class="py-2 px-1.5">HTTP</th>
              <th class="py-2 px-1.5">状态</th><th class="py-2 px-1.5">错误</th><th class="py-2 px-1.5">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.id" class="border-b border-[var(--border)]/50 hover:bg-[var(--hover)] cursor-pointer"
                :class="r.status !== 'success' ? 'row-failed' : ''" @click="openPreview(r)">
              <td class="py-1.5" @click.stop><input type="checkbox" class="accent-[var(--accent)] cursor-pointer"
                  :checked="selected.includes(r.id)"
                  @change="$event.target.checked ? selected.push(r.id) : (selected = selected.filter(i => i !== r.id))" /></td>
              <td class="px-1.5 text-muted">{{ r.ts }}</td>
              <td class="px-1.5"><Badge size="sm" :variant="r.request_type === 'proxy' ? 'info' : 'accent'">{{ r.request_type === 'proxy' ? '反代' : '分流' }}</Badge></td>
              <td class="px-1.5">{{ r.protocol }}</td>
              <td class="px-1.5">{{ r.key_name || '-' }}</td>
              <td class="px-1.5 font-medium">{{ r.model || '-' }}</td>
              <td class="px-1.5">{{ r.vendor_tag || '-' }}</td>
              <td class="px-1.5 text-muted">{{ r.source_ip }}</td>
              <td class="px-1.5">{{ r.channel || '-' }}</td>
              <td class="px-1.5 text-right">{{ r.latency_ms }}ms</td>
              <td class="px-1.5 text-right">{{ r.prompt_tokens }}</td>
              <td class="px-1.5 text-right">{{ r.completion_tokens }}</td>
              <td class="px-1.5">{{ r.http_status || '-' }}</td>
              <td class="px-1.5"><Badge size="sm" :variant="statusVariant(r.status)">{{ statusText(r.status) }}</Badge></td>
              <td class="px-1.5 max-w-[160px] truncate text-red-500" :title="r.error">{{ r.error || '' }}</td>
              <td class="px-1.5" @click.stop>
                <div class="flex gap-0.5">
                  <Button size="icon" variant="ghost" title="预览" @click="openPreview(r)"><Eye :size="13" /></Button>
                  <Button size="icon" variant="ghost" class="text-red-500" title="删除" @click="deleteOne(r)"><Trash2 :size="13" /></Button>
                </div>
              </td>
            </tr>
            <tr v-if="!rows.length"><td colspan="16"><EmptyState message="暂无日志" /></td></tr>
          </tbody>
        </table>
      </div>
      <Pagination :page="page" :total="total" :size="50" @change="p => { page = p; load() }" />

      <div class="flex gap-2 mt-3">
        <Button variant="outline" @click="exportCsv"><Download :size="14" /> 导出筛选结果 CSV</Button>
        <Button variant="destructive" @click="askClearAll"><Trash2 :size="14" /> 清空全部</Button>
      </div>
    </Card>

    <Dialog v-model:open="previewDlg.open" title="请求详情" width="680px">
      <div class="space-y-3 text-[12.5px]" v-if="previewDlg.log">
        <div class="grid grid-cols-2 gap-2 text-muted">
          <div>时间：<b class="text-content">{{ previewDlg.log.ts }}</b></div>
          <div>状态：<Badge size="sm" :variant="statusVariant(previewDlg.log.status)">{{ previewDlg.log.status }}</Badge></div>
          <div>渠道：{{ previewDlg.log.channel || '-' }}</div>
          <div>HTTP：{{ previewDlg.log.http_status || '-' }} · 耗时 {{ previewDlg.log.latency_ms }}ms</div>
        </div>
        <div v-if="previewDlg.log.error" class="rounded-card bg-red-500/8 border border-red-500/25 p-2.5 text-red-600 dark:text-red-300 break-all">
          {{ previewDlg.log.error }}</div>
        <div>
          <div class="text-xs text-muted mb-1">原始请求 Payload</div>
          <JsonPreview :data="previewDlg.log.request_payload" />
        </div>
        <div>
          <div class="text-xs text-muted mb-1">响应 Payload</div>
          <JsonPreview :data="previewDlg.log.response_payload" />
        </div>
      </div>
    </Dialog>

    <ConfirmDialog v-model:open="confirmState.open" :title="confirmState.title" :message="confirmState.message" danger @confirm="confirmState.action && confirmState.action()" />
  </div>
</template>
