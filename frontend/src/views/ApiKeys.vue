<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { api, downloadFile } from '../api/client'
import { useUiStore } from '../stores/ui'
import { toast } from '../components/ui/toast'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import Input from '../components/ui/Input.vue'
import Select from '../components/ui/Select.vue'
import Switch from '../components/ui/Switch.vue'
import Badge from '../components/ui/Badge.vue'
import RefreshButton from '../components/ui/RefreshButton.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import Dialog from '../components/ui/Dialog.vue'
import ConfirmDialog from '../components/ui/ConfirmDialog.vue'
import { Plus, Pencil, Copy, Trash2, RotateCcw, Download, Ban } from 'lucide-vue-next'

const ui = useUiStore()
const rows = ref([])
const loading = ref(false)
const confirmState = ref({ open: false, title: '', message: '', action: null })

const emptyForm = () => ({
  name: '', tag: '', enabled: true, expires_at: '',
  quota_requests: 0, quota_total_tokens: 0, quota_input_tokens: 0, quota_output_tokens: 0,
  period: 'none', rps: 0, model_whitelist: '', model_blacklist: '', ip_whitelist: '', alert_threshold: 80
})
const formDlg = ref({ open: false, isEdit: false, form: emptyForm() })
const createdKey = ref('')
const keyDlg = ref({ open: false, key: '' })

async function load() {
  loading.value = true
  try { rows.value = (await api.get('/admin/api/keys', { silent: true })).rows }
  finally { loading.value = false }
}

function openCreate() { formDlg.value = { open: true, isEdit: false, form: emptyForm() } }
function openEdit(r) {
  formDlg.value = { open: true, isEdit: true, form: { ...r, enabled: !!r.enabled } }
}
async function saveForm() {
  const f = formDlg.value.form
  if (!f.name) return toast.warning('备注必填')
  if (formDlg.value.isEdit) {
    await api.put(`/admin/api/keys/${f.id}`, f)
    toast.success('密钥已更新')
  } else {
    const res = await api.post('/admin/api/keys', f)
    createdKey.value = res.key.key
    keyDlg.value = { open: true, key: res.key.key }
  }
  formDlg.value.open = false
  load()
}
async function copyKey(k) {
  await navigator.clipboard.writeText(k).catch(() => {})
  toast.success('Key 已复制到剪贴板')
}
function askDelete(r) {
  confirmState.value = { open: true, title: '删除密钥', message: `确认删除「${r.name}」？使用该 Key 的客户端将立即 401。`,
    action: async () => { await api.del(`/admin/api/keys/${r.id}`); toast.success('已删除'); load() } }
}
async function resetQuota(r) {
  await api.post(`/admin/api/keys/${r.id}/reset-quota`)
  toast.success('额度已重置')
  load()
}
async function toggle(r) {
  await api.put(`/admin/api/keys/${r.id}`, { enabled: r.enabled ? 0 : 1 })
  load()
}
function exportCsv() { downloadFile('/admin/api/keys/export-csv', 'api_keys.csv') }

function remainText(r) {
  const parts = []
  if (r.quota_requests) parts.push(`次数 ${r.remaining_requests}`)
  if (r.quota_total_tokens) parts.push(`Token ${r.remaining_total_tokens}`)
  return parts.length ? parts.join(' / ') : '不限'
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
    <Card>
      <template #header>
        <div class="flex flex-wrap items-center gap-2">
          <Button size="sm" @click="openCreate"><Plus :size="14" /> 新建密钥</Button>
          <Button size="sm" variant="outline" @click="exportCsv"><Download :size="14" /> 导出 CSV</Button>
          <RefreshButton :loading="loading" @refresh="load" />
        </div>
      </template>

      <div class="overflow-x-auto">
        <table class="w-full text-[12.5px] whitespace-nowrap">
          <thead>
            <tr class="text-left text-muted border-b border-[var(--border)]">
              <th class="py-2 px-1.5">启用</th><th class="py-2 px-1.5">备注</th><th class="py-2 px-1.5">标签</th>
              <th class="py-2 px-1.5">Key</th><th class="py-2 px-1.5 text-right">已用请求</th>
              <th class="py-2 px-1.5 text-right">已用 Token (入/出)</th><th class="py-2 px-1.5">剩余额度</th>
              <th class="py-2 px-1.5">周期</th><th class="py-2 px-1.5">过期时间</th>
              <th class="py-2 px-1.5">最后调用</th><th class="py-2 px-1.5">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.id" class="border-b border-[var(--border)]/50 hover:bg-[var(--hover)]"
                :class="r.enabled && !r.expired ? '' : 'opacity-45'">
              <td class="px-1.5 py-2"><Switch :model-value="!!r.enabled" @update:model-value="toggle(r)" /></td>
              <td class="px-1.5 font-semibold">{{ r.name }}
                <Badge v-if="r.expired" size="sm" variant="error">已过期</Badge></td>
              <td class="px-1.5">{{ r.tag || '-' }}</td>
              <td class="px-1.5 font-mono text-[11.5px]">
                <span class="cursor-pointer hover:text-[var(--accent)]" title="点击复制" @click="copyKey(r.key)">
                  {{ r.key.slice(0, 12) }}…{{ r.key.slice(-4) }} <Copy :size="11" class="inline opacity-50" /></span></td>
              <td class="px-1.5 text-right">{{ r.used_requests?.toLocaleString() }}<span v-if="r.quota_requests" class="text-muted"> / {{ r.quota_requests.toLocaleString() }}</span></td>
              <td class="px-1.5 text-right text-muted">{{ r.used_input_tokens?.toLocaleString() }} / {{ r.used_output_tokens?.toLocaleString() }}</td>
              <td class="px-1.5">{{ remainText(r) }}</td>
              <td class="px-1.5"><Badge size="sm" :variant="r.period === 'daily' ? 'info' : r.period === 'monthly' ? 'warning' : 'default'">
                {{ { none: '不限', daily: '每日', monthly: '每月' }[r.period] }}</Badge></td>
              <td class="px-1.5 text-muted">{{ r.expires_at || '永久' }}</td>
              <td class="px-1.5 text-muted">{{ r.last_used_at || '从未' }}</td>
              <td class="px-1.5">
                <div class="flex gap-0.5">
                  <Button size="icon" variant="ghost" @click="openEdit(r)" title="编辑"><Pencil :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" @click="copyKey(r.key)" title="复制 Key"><Copy :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" @click="resetQuota(r)" title="重置额度"><RotateCcw :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" @click="toggle(r)" title="禁用/启用"><Ban :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" class="text-red-500" @click="askDelete(r)" title="删除"><Trash2 :size="13.5" /></Button>
                </div>
              </td>
            </tr>
            <tr v-if="!rows.length"><td colspan="11"><EmptyState message="暂无密钥，创建一个并分发给客户端" /></td></tr>
          </tbody>
        </table>
      </div>
    </Card>

    <!-- 新建/编辑 -->
    <Dialog v-model:open="formDlg.open" :title="formDlg.isEdit ? '编辑密钥' : '新建密钥'" width="600px">
      <div class="grid grid-cols-2 gap-x-4 gap-y-3 text-[13px]">
        <div><label class="text-xs text-muted">备注 *</label><Input v-model="formDlg.form.name" class="mt-1" placeholder="如 mobile-app" /></div>
        <div><label class="text-xs text-muted">标签分组</label><Input v-model="formDlg.form.tag" class="mt-1" /></div>
        <div><label class="text-xs text-muted">过期时间（留空永久）</label><Input v-model="formDlg.form.expires_at" type="date" class="mt-1" /></div>
        <div><label class="text-xs text-muted">额度周期</label>
          <Select v-model="formDlg.form.period" class="mt-1" :options="[
            { value: 'none', label: '不限' }, { value: 'daily', label: '每日重置' }, { value: 'monthly', label: '每月重置' }]" /></div>
        <div><label class="text-xs text-muted">总次数上限（0 不限）</label><Input v-model="formDlg.form.quota_requests" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">总 Token 上限</label><Input v-model="formDlg.form.quota_total_tokens" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">输入 Token 上限</label><Input v-model="formDlg.form.quota_input_tokens" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">输出 Token 上限</label><Input v-model="formDlg.form.quota_output_tokens" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">RPS 限流（0 不限）</label><Input v-model="formDlg.form.rps" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">告警阈值 %</label><Input v-model="formDlg.form.alert_threshold" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">模型白名单（逗号分隔）</label><Input v-model="formDlg.form.model_whitelist" class="mt-1" placeholder="gpt-4o,claude-*" /></div>
        <div><label class="text-xs text-muted">模型黑名单</label><Input v-model="formDlg.form.model_blacklist" class="mt-1" /></div>
        <div class="col-span-2"><label class="text-xs text-muted">IP 白名单（逗号分隔，支持 CIDR，留空不限）</label>
          <Input v-model="formDlg.form.ip_whitelist" class="mt-1" placeholder="192.168.1.0/24,10.0.0.5" /></div>
        <label class="flex items-center gap-2">启用 <Switch v-model="formDlg.form.enabled" /></label>
      </div>
      <template #footer>
        <Button variant="outline" @click="formDlg.open = false">取消</Button>
        <Button @click="saveForm">{{ formDlg.isEdit ? '保存' : '生成密钥' }}</Button>
      </template>
    </Dialog>

    <!-- 新建成功展示 key -->
    <Dialog v-model:open="keyDlg.open" title="密钥已生成" width="520px">
      <div class="space-y-3">
        <p class="text-[13px] text-muted">请立即复制保存，该 Key 支持 OpenAI 与 Claude 双协议调用：</p>
        <div class="flex gap-2">
          <Input :model-value="keyDlg.key" readonly class="font-mono text-[12px]" />
          <Button variant="outline" @click="copyKey(keyDlg.key)"><Copy :size="14" /> 复制</Button>
        </div>
        <div class="text-[12px] text-muted rounded-card bg-[var(--hover)] p-3 leading-relaxed">
          OpenAI 端点：<code>POST http://&lt;host&gt;:9010/v1/chat/completions</code><br />
          Claude 端点：<code>POST http://&lt;host&gt;:9010/anthropic/v1/messages</code>
        </div>
      </div>
    </Dialog>

    <ConfirmDialog v-model:open="confirmState.open" :title="confirmState.title" :message="confirmState.message" danger @confirm="confirmState.action && confirmState.action()" />
  </div>
</template>
