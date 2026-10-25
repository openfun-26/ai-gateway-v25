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
import JsonPreview from '../components/ui/JsonPreview.vue'
import { Eye } from 'lucide-vue-next'

const ui = useUiStore()
const rows = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const filters = ref({ start: '', end: '', model: '', channel: '', request_type: 'all', q: '' })
const previewDlg = ref({ open: false, log: null })

async function load() {
  loading.value = true
  try {
    const r = await api.get(`/admin/api/logs/errors${qs({ ...filters.value, page: page.value, size: 50 })}`, { silent: true })
    rows.value = r.rows
    total.value = r.total
  } finally { loading.value = false }
}
function doSearch() { page.value = 1; load() }

const statusText = s => ({ failure: '失败', timeout: '超时', rate_limited: '限流', circuit_open: '熔断',
  blacklisted: '黑名单', auth_failed: '鉴权失败', ip_blocked: 'IP限制', quota_exhausted: '额度耗尽' }[s] || s)

async function openPreview(row) {
  const r = await api.get(`/admin/api/logs/${row.id}`)
  previewDlg.value = { open: true, log: r.log }
}
function exportCsv() {
  downloadFile(`/admin/api/logs/export-csv${qs({ ...filters.value, errors_only: '1' })}`, `error_logs_${Date.now()}.csv`)
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
    <Card title="错误日志" subtitle="全部失败/超时/限流/熔断/黑名单/鉴权失败记录（含反代产生的错误）">
      <template #header><RefreshButton :loading="loading" @refresh="load" /></template>

      <div class="flex flex-wrap items-end gap-2 mb-3 text-[13px]">
        <div><label class="text-[11px] text-muted">开始日期</label><Input v-model="filters.start" type="date" class="!w-36" /></div>
        <div><label class="text-[11px] text-muted">结束日期</label><Input v-model="filters.end" type="date" class="!w-36" /></div>
        <div><label class="text-[11px] text-muted">模型</label><Input v-model="filters.model" class="!w-32" /></div>
        <div><label class="text-[11px] text-muted">渠道</label><Input v-model="filters.channel" class="!w-28" /></div>
        <div><label class="text-[11px] text-muted">类型</label>
          <Select v-model="filters.request_type" class="!w-24" :options="[{ value: 'all', label: '全部' }, { value: 'forward', label: '分流' }, { value: 'proxy', label: '反代' }]" /></div>
        <div><label class="text-[11px] text-muted">关键字</label><Input v-model="filters.q" class="!w-40" /></div>
        <Button size="sm" @click="doSearch">筛选</Button>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-[12px] whitespace-nowrap">
          <thead>
            <tr class="text-left text-muted border-b border-[var(--border)]">
              <th class="py-2 px-1.5">时间</th><th class="py-2 px-1.5">类型</th><th class="py-2 px-1.5">协议</th>
              <th class="py-2 px-1.5">Key</th><th class="py-2 px-1.5">模型</th><th class="py-2 px-1.5">源IP</th>
              <th class="py-2 px-1.5">渠道</th><th class="py-2 px-1.5 text-right">耗时</th><th class="py-2 px-1.5">HTTP</th>
              <th class="py-2 px-1.5">状态</th><th class="py-2 px-1.5">错误消息</th><th class="py-2 px-1.5">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.id" class="border-b border-[var(--border)]/50 hover:bg-[var(--hover)] cursor-pointer row-failed" @click="openPreview(r)">
              <td class="px-1.5 py-1.5 text-muted">{{ r.ts }}</td>
              <td class="px-1.5"><Badge size="sm" :variant="r.request_type === 'proxy' ? 'info' : 'accent'">{{ r.request_type === 'proxy' ? '反代' : '分流' }}</Badge></td>
              <td class="px-1.5">{{ r.protocol }}</td>
              <td class="px-1.5">{{ r.key_name || '-' }}</td>
              <td class="px-1.5 font-medium">{{ r.model || '-' }}</td>
              <td class="px-1.5 text-muted">{{ r.source_ip }}</td>
              <td class="px-1.5">{{ r.channel || '-' }}</td>
              <td class="px-1.5 text-right">{{ r.latency_ms }}ms</td>
              <td class="px-1.5">{{ r.http_status || '-' }}</td>
              <td class="px-1.5"><Badge size="sm" variant="error">{{ statusText(r.status) }}</Badge></td>
              <td class="px-1.5 max-w-[260px] truncate text-red-500" :title="r.error">{{ r.error || '' }}</td>
              <td class="px-1.5"><Button size="icon" variant="ghost" @click.stop="openPreview(r)"><Eye :size="13" /></Button></td>
            </tr>
            <tr v-if="!rows.length"><td colspan="12"><EmptyState message="没有错误记录 🎉" /></td></tr>
          </tbody>
        </table>
      </div>
      <Pagination :page="page" :total="total" :size="50" @change="p => { page = p; load() }" />

      <div class="mt-3">
        <Button variant="outline" @click="exportCsv">导出筛选结果 CSV</Button>
      </div>
    </Card>

    <Dialog v-model:open="previewDlg.open" title="错误详情" width="680px">
      <div class="space-y-3 text-[12.5px]" v-if="previewDlg.log">
        <div class="grid grid-cols-2 gap-2 text-muted">
          <div>时间：<b class="text-content">{{ previewDlg.log.ts }}</b></div>
          <div>状态：{{ previewDlg.log.status }} · HTTP {{ previewDlg.log.http_status || '-' }}</div>
        </div>
        <div class="rounded-card bg-red-500/8 border border-red-500/25 p-2.5 text-red-600 dark:text-red-300 break-all">
          {{ previewDlg.log.error }}</div>
        <div><div class="text-xs text-muted mb-1">请求 Payload</div><JsonPreview :data="previewDlg.log.request_payload" /></div>
      </div>
    </Dialog>
  </div>
</template>
