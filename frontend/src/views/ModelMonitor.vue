<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRoute } from 'vue-router'
import { api, downloadFile } from '../api/client'
import { useUiStore } from '../stores/ui'
import { toast } from '../components/ui/toast'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import Input from '../components/ui/Input.vue'
import Select from '../components/ui/Select.vue'
import Badge from '../components/ui/Badge.vue'
import StatusDot from '../components/ui/StatusDot.vue'
import Switch from '../components/ui/Switch.vue'
import RefreshButton from '../components/ui/RefreshButton.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import Dialog from '../components/ui/Dialog.vue'
import ConfirmDialog from '../components/ui/ConfirmDialog.vue'
import Textarea from '../components/ui/Textarea.vue'
import { fmtMs } from '../components/ui/helpers'
import { FlaskConical, Activity, Download, Pencil, Trash2, ArrowUp, ArrowDown, Plus } from 'lucide-vue-next'

const route = useRoute()
const ui = useUiStore()

const rows = ref([])
const loading = ref(false)
const filters = ref({ search: '', status: 'all', vendor: 'all', group: 'all', channel: 'all' })
const selected = ref([])

async function load() {
  loading.value = true
  try {
    const r = await api.get('/admin/api/models', { silent: true })
    rows.value = r.rows
    if (route.query.model) filters.value.search = route.query.model
  } finally { loading.value = false }
}

const vendorOpts = computed(() => [...new Set(rows.value.map(r => r.vendor_tag).filter(Boolean))])
const groupOpts = computed(() => [...new Set(rows.value.map(r => r.channel_group).filter(Boolean))])
const channelOpts = computed(() => [...new Map(rows.value.map(r => [r.channel_name, r.channel_name])).entries()].map(([k]) => k))

const filtered = computed(() => rows.value.filter(r => {
  const f = filters.value
  if (f.search && !(r.upstream_model.includes(f.search) || (r.alias || '').includes(f.search))) return false
  if (f.status !== 'all' && r.status !== f.status) return false
  if (f.vendor !== 'all' && r.vendor_tag !== f.vendor) return false
  if (f.group !== 'all' && r.channel_group !== f.group) return false
  if (f.channel !== 'all' && r.channel_name !== f.channel) return false
  return true
}))

const statusVariant = s => ({ online: 'success', limited: 'warning', offline: 'error', missing: 'default', unknown: 'default' }[s] || 'default')
const statusText = s => ({ online: '在线', limited: '限速/超时', offline: '离线', missing: '不存在', unknown: '未知' }[s] || s)

// 批量
const confirmState = ref({ open: false, title: '', message: '', action: null })
function askConfirm(title, message, action) {
  confirmState.value = { open: true, title, message, action }
}
async function batch(action, value) {
  if (!selected.value.length) return toast.warning('请先勾选模型')
  if (action === 'delete') {
    return askConfirm('批量删除模型', `将永久删除选中的 ${selected.value.length} 个模型映射，确认？`,
      async () => {
        await api.post('/admin/api/models/batch', { action, ids: selected.value })
        toast.success(`已删除 ${selected.value.length} 个模型`)
        selected.value = []
        load()
      })
  }
  await api.post('/admin/api/models/batch', { action, ids: selected.value, value })
  toast.success('批量操作完成')
  selected.value = []
  load()
}
async function deleteOne(r) {
  askConfirm('删除模型', `将永久删除「${r.alias || r.upstream_model}」的模型映射，确认？`,
    async () => {
      await api.del(`/admin/api/models/${r.id}`)
      toast.success('已删除')
      load()
    })
}
async function toggleModel(r, v) {
  await api.put(`/admin/api/models/${r.id}`, { enabled: v ? 1 : 0 })
  r.enabled = v ? 1 : 0
}

// 批量改名弹窗（替代原生 prompt）
const promptDlg = ref({ open: false, action: '', label: '', value: '' })
function openPrompt(action, label) {
  if (!selected.value.length) return toast.warning('请先勾选模型')
  promptDlg.value = { open: true, action, label, value: '' }
}
async function runPrompt() {
  await batch(promptDlg.value.action, promptDlg.value.value)
  promptDlg.value.open = false
}

// 单模型测试
const testDlg = ref({ open: false, model: '', channel_id: null, prompt: 'Hello，请回复 pong' })
const testResult = ref(null)
const testing = ref(false)
function openTest(row) {
  testDlg.value = { open: true, model: row.alias || row.upstream_model, channel_id: row.channel_id, prompt: 'Hello，请回复 pong' }
  testResult.value = null
}
async function runTest() {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await api.post('/admin/api/models/test', testDlg.value)
  } catch (e) {
    testResult.value = { ok: false, error: e.message }
  } finally { testing.value = false }
}

// 编辑
const editDlg = ref({ open: false, row: null })
function openEdit(row) { editDlg.value = { open: true, row: { ...row } } }
async function saveEdit() {
  const r = editDlg.value.row
  await api.put(`/admin/api/models/${r.id}`, {
    alias: r.alias, vendor_tag: r.vendor_tag, emoji: r.emoji, grp: r.grp,
    remark: r.remark, enabled: r.enabled ? 1 : 0, skip_health: r.skip_health ? 1 : 0, prefer_group: r.prefer_group
  })
  toast.success('已保存')
  editDlg.value.open = false
  load()
}

async function refreshChannel(cid) {
  toast.info('正在后台检测该渠道模型，状态稍后自动更新…')
  const r = await api.post(`/admin/api/models/health-check-channel/${cid}`)
  toast.success(`已提交检测（${r.checked} 个模型），请稍候刷新查看`)
  load()
}
async function healthAll() {
  const r = await api.post('/admin/api/models/health-check-all')
  if (r.started === false) return toast.warning(r.message || '检测任务已在进行中')
  toast.success('后台检测已启动，状态将陆续更新（无需等待）')
}
function exportCsv() { downloadFile('/admin/api/models/export-csv', 'models.csv') }

let timer = null
function setupTimer() {
  clearInterval(timer)
  if (ui.autoRefresh) timer = setInterval(load, ui.autoRefreshInterval * 1000)
}
// ---------- auto 智能路由 ----------
const autoOn = ref(false)
const autoExPaid = ref(true)
async function loadAuto() {
  try {
    const s = (await api.get('/admin/api/settings', { silent: true })).settings
    autoOn.value = String(s.auto_enabled ?? '1') === '1'
    autoExPaid.value = String(s.auto_exclude_paid ?? '1') === '1'
  } catch (e) { /* 静默 */ }
}
async function saveAuto(v) {
  try {
    await api.put('/admin/api/settings', { auto_enabled: v ? 1 : 0 })
    toast.success(v ? 'auto 智能路由已开启' : 'auto 智能路由已关闭')
  } catch (e) { autoOn.value = !v }
}
async function saveExPaid(v) {
  try {
    await api.put('/admin/api/settings', { auto_exclude_paid: v ? 1 : 0 })
    toast.success(v ? 'auto 将跳过付费渠道' : 'auto 允许使用付费渠道')
  } catch (e) { autoExPaid.value = !v }
}
// ---------- auto 规则路由（按问题内容选模型） ----------
const autoRules = ref([])
const ruleDlg = ref({ open: false, keyword: '', model_name: '', priority: 0 })
async function loadRules() {
  try { autoRules.value = (await api.get('/admin/api/models/auto-rules', { silent: true })).rows } catch (e) { /* 静默 */ }
}
async function addRule() {
  if (!ruleDlg.value.keyword.trim() || !ruleDlg.value.model_name.trim()) return toast.warning('关键词与目标模型不能为空')
  await api.post('/admin/api/models/auto-rules', ruleDlg.value)
  toast.success('规则已添加')
  ruleDlg.value.open = false
  loadRules()
}
async function toggleRule(r) {
  await api.put(`/admin/api/models/auto-rules/${r.id}`, { enabled: r.enabled ? 0 : 1 })
  r.enabled = r.enabled ? 0 : 1
}
async function delRule(r) {
  await api.del(`/admin/api/models/auto-rules/${r.id}`)
  toast.success('规则已删除')
  loadRules()
}
// ---------- 模型排序（降级顺序） ----------
async function moveModel(r, direction) {
  const res = await api.post('/admin/api/models/reorder', { id: r.id, direction })
  if (res.ok && res.moved) load()
}
onMounted(() => { load(); loadAuto(); loadRules(); setupTimer(); window.addEventListener('gw-autorefresh-changed', setupTimer) })
onBeforeUnmount(() => { clearInterval(timer); window.removeEventListener('gw-autorefresh-changed', setupTimer) })
</script>

<template>
  <div class="space-y-4 pb-8">
    <Card title="🎯 auto 智能路由" subtitle="请求模型名 auto 时由网关挑最优渠道；其他模型失败时按下方列表顺序自动降级备选，auto 兜底">
      <template #header>
        <Badge variant="accent">v20 增强</Badge>
      </template>
      <div class="space-y-3 text-[13px]">
        <div class="flex items-center justify-between gap-4">
          <span class="text-muted">开启后客户端可直接请求 auto；关闭后请求 auto 将提示模型不存在。备选降级顺序 = 下方模型列表从上到下（可用 ↑↓ 按钮调整）。</span>
          <div class="shrink-0"><Switch v-model="autoOn" @update:modelValue="saveAuto" /></div>
        </div>
        <div class="flex items-center justify-between gap-4 border-t border-[var(--border)]/60 pt-3">
          <span class="text-muted">💸 排除付费渠道：auto 挑选与兜底时跳过标记为「付费」的渠道（防止误触付费模型产生费用）。标记入口：上游渠道页编辑。</span>
          <div class="shrink-0"><Switch v-model="autoExPaid" @update:modelValue="saveExPaid" /></div>
        </div>
        <!-- auto 规则路由 -->
        <div class="border-t border-[var(--border)]/60 pt-3">
          <div class="flex items-center justify-between mb-2">
            <span class="font-medium">📋 规则路由（按问题内容自动选模型）</span>
            <Button size="sm" variant="accent-soft" @click="ruleDlg = { open: true, keyword: '', model_name: '', priority: 0 }">
              <Plus :size="13" /> 新增规则
            </Button>
          </div>
          <p class="text-muted text-[12px] mb-2">用户消息命中关键词时，auto 优先使用指定模型（该模型不可用时自动按健康度兜底）。数字越小优先级越高。</p>
          <div v-if="autoRules.length" class="overflow-x-auto">
            <table class="w-full text-[12.5px] whitespace-nowrap">
              <thead><tr class="text-left text-muted border-b border-[var(--border)]">
                <th class="py-1.5 font-medium">启用</th><th class="py-1.5 px-2 font-medium">关键词</th>
                <th class="py-1.5 px-2 font-medium">目标模型</th><th class="py-1.5 px-2 font-medium">优先级</th>
                <th class="py-1.5 font-medium">操作</th></tr></thead>
              <tbody>
                <tr v-for="r in autoRules" :key="r.id" class="border-b border-[var(--border)]/50" :class="r.enabled ? '' : 'opacity-45'">
                  <td class="py-1.5"><Switch :model-value="!!r.enabled" @update:model-value="() => toggleRule(r)" /></td>
                  <td class="px-2"><Badge variant="accent">{{ r.keyword }}</Badge></td>
                  <td class="px-2 font-medium">{{ r.model_name }}</td>
                  <td class="px-2">{{ r.priority }}</td>
                  <td class="py-1.5"><Button size="icon" variant="ghost" class="text-red-500" @click="delRule(r)" title="删除"><Trash2 :size="14" /></Button></td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="text-muted text-[12px]">暂无规则。示例：关键词「画图」→ 模型「glm-5v-turbo」；关键词「代码」→ 模型「deepseek-v4-pro」。</p>
        </div>
      </div>
    </Card>
    <Card title="模型监控" subtitle="别名映射 / 分组 / 健康检测状态 / 默认路由组">
      <template #header>
        <div class="flex flex-wrap items-center gap-2">
          <Input v-model="filters.search" placeholder="搜索模型ID / 别名" class="!w-44" />
          <Select v-model="filters.status" class="!w-28" :options="[
            { value: 'all', label: '全部状态' }, { value: 'online', label: '在线' },
            { value: 'limited', label: '限速' }, { value: 'offline', label: '离线' }, { value: 'missing', label: '不存在' }]" />
          <Select v-model="filters.vendor" class="!w-28" :options="[{ value: 'all', label: '全部厂商' }, ...vendorOpts.map(v => ({ value: v, label: v }))]" />
          <Select v-model="filters.group" class="!w-28" :options="[{ value: 'all', label: '全部分组' }, ...groupOpts.map(v => ({ value: v, label: v }))]" />
          <Select v-model="filters.channel" class="!w-32" :options="[{ value: 'all', label: '全部渠道' }, ...channelOpts.map(v => ({ value: v, label: v }))]" />
          <RefreshButton :loading="loading" @refresh="load" />
        </div>
      </template>

      <!-- 批量操作条 -->
      <div class="flex flex-wrap items-center gap-2 mb-3" v-if="selected.length">
        <Badge variant="accent">已选 {{ selected.length }} 项</Badge>
        <Button size="sm" variant="outline" @click="batch('enable')">批量启用</Button>
        <Button size="sm" variant="outline" @click="batch('disable')">批量禁用</Button>
        <Button size="sm" variant="outline" @click="openPrompt('set_vendor', '新的厂商标签')">批量改厂商</Button>
        <Button size="sm" variant="outline" @click="openPrompt('set_remark', '新的备注标签')">批量改备注</Button>
        <Button size="sm" variant="destructive" @click="batch('delete')"><Trash2 :size="13" /> 批量删除</Button>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-[12.5px] whitespace-nowrap">
          <thead>
            <tr class="text-left text-muted border-b border-[var(--border)]">
              <th class="py-2 w-8"><input type="checkbox" class="accent-[var(--accent)] cursor-pointer"
                  :checked="selected.length && selected.length === filtered.length"
                  @change="selected = $event.target.checked ? filtered.map(r => r.id) : []" /></th>
              <th class="py-2 px-1.5 font-medium">启用</th>
              <th class="py-2 px-1.5 font-medium">分组</th><th class="py-2 px-1.5 font-medium">渠道</th>
              <th class="py-2 px-1.5 font-medium">模型ID</th><th class="py-2 px-1.5 font-medium">状态</th>
              <th class="py-2 px-1.5 font-medium">厂商</th><th class="py-2 px-1.5 font-medium">HTTP</th>
              <th class="py-2 px-1.5 font-medium">耗时</th><th class="py-2 px-1.5 font-medium">上次检测</th>
              <th class="py-2 px-1.5 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in filtered" :key="r.id" class="border-b border-[var(--border)]/50 hover:bg-[var(--hover)]"
                :class="r.enabled ? '' : 'opacity-45'">
              <td class="py-2"><input type="checkbox" class="accent-[var(--accent)] cursor-pointer"
                  :checked="selected.includes(r.id)" @change="$event.target.checked ? selected.push(r.id) : (selected = selected.filter(i => i !== r.id))" /></td>
              <td class="px-1.5"><Switch :model-value="!!r.enabled" @update:model-value="v => toggleModel(r, v)" /></td>
              <td class="px-1.5">{{ r.channel_group || '-' }}</td>
              <td class="px-1.5">{{ r.channel_name || '-' }}</td>
              <td class="px-1.5 font-medium">{{ r.emoji }} {{ r.alias || r.upstream_model }}
                <span v-if="r.alias" class="text-muted text-[11px]">（{{ r.upstream_model }}）</span></td>
              <td class="px-1.5"><span class="inline-flex items-center gap-1.5"><StatusDot :status="r.status" />
                <Badge size="sm" :variant="statusVariant(r.status)">{{ statusText(r.status) }}</Badge></span></td>
              <td class="px-1.5">{{ r.vendor_tag || '-' }}</td>
              <td class="px-1.5 text-muted">{{ r.last_http_status ?? '-' }}</td>
              <td class="px-1.5">{{ fmtMs(r.latency_ms) }}</td>
              <td class="px-1.5 text-muted">{{ r.last_check_time || '从未检测' }}</td>
              <td class="px-1.5">
                <div class="flex gap-1">
                  <Button size="icon" variant="ghost" @click="moveModel(r, 'up')" title="上移（降级顺序提前）"><ArrowUp :size="14" /></Button>
                  <Button size="icon" variant="ghost" @click="moveModel(r, 'down')" title="下移（降级顺序靠后）"><ArrowDown :size="14" /></Button>
                  <Button size="icon" variant="ghost" @click="openTest(r)" title="测试"><FlaskConical :size="14" /></Button>
                  <Button size="icon" variant="ghost" @click="refreshChannel(r.channel_id)" title="检测此渠道全部模型"><Activity :size="14" /></Button>
                  <Button size="icon" variant="ghost" @click="openEdit(r)" title="编辑"><Pencil :size="14" /></Button>
                  <Button size="icon" variant="ghost" class="text-red-500" @click="deleteOne(r)" title="删除"><Trash2 :size="14" /></Button>
                </div>
              </td>
            </tr>
            <tr v-if="!filtered.length"><td colspan="11"><EmptyState message="没有匹配的模型" /></td></tr>
          </tbody>
        </table>
      </div>

      <div class="flex gap-2 mt-4">
        <Button variant="accent-soft" @click="healthAll"><Activity :size="14" /> 一键全部模型健康检测</Button>
        <Button variant="outline" @click="exportCsv"><Download :size="14" /> 导出全部模型 CSV</Button>
      </div>
    </Card>

    <!-- 测试弹窗 -->
    <Dialog v-model:open="testDlg.open" title="模型测试" width="560px">
      <div class="space-y-3">
        <div><label class="text-xs text-muted">模型</label>
          <Input v-model="testDlg.model" class="mt-1" /></div>
        <div><label class="text-xs text-muted">测试 Prompt</label>
          <Textarea v-model="testDlg.prompt" :rows="3" class="mt-1" /></div>
        <Button :disabled="testing" @click="runTest">
          <FlaskConical :size="14" /> {{ testing ? '测试中…' : '发送测试' }}
        </Button>
        <div v-if="testResult" class="rounded-card hairline p-3 space-y-2 text-[12.5px]">
          <div v-if="testResult.ok">
            <Badge variant="success">成功</Badge>
            <span class="ml-2 text-muted">耗时 {{ testResult.latency_ms }}ms · P {{ testResult.prompt_tokens }} / C {{ testResult.completion_tokens }} tok · HTTP {{ testResult.http_status }}</span>
            <div class="mt-2 p-2 rounded-md bg-[var(--hover)] whitespace-pre-wrap break-all">{{ testResult.content }}</div>
          </div>
          <div v-else><Badge variant="error">失败</Badge><span class="ml-2 text-red-500 break-all">{{ testResult.error }}</span></div>
        </div>
      </div>
    </Dialog>

    <!-- 编辑弹窗 -->
    <Dialog v-model:open="editDlg.open" title="编辑模型" width="480px">
      <div class="grid grid-cols-2 gap-3 text-[13px]" v-if="editDlg.row">
        <div><label class="text-xs text-muted">对外别名（alias）</label><Input v-model="editDlg.row.alias" class="mt-1" /></div>
        <div><label class="text-xs text-muted">厂商标签</label><Input v-model="editDlg.row.vendor_tag" class="mt-1" /></div>
        <div><label class="text-xs text-muted">emoji 图标</label><Input v-model="editDlg.row.emoji" class="mt-1" /></div>
        <div><label class="text-xs text-muted">所属分组</label><Input v-model="editDlg.row.grp" class="mt-1" /></div>
        <div><label class="text-xs text-muted">默认优先路由渠道组</label><Input v-model="editDlg.row.prefer_group" class="mt-1" /></div>
        <div><label class="text-xs text-muted">备注标签</label><Input v-model="editDlg.row.remark" class="mt-1" /></div>
        <label class="flex items-center gap-2"><input type="checkbox" v-model="editDlg.row.enabled" class="accent-[var(--accent)]" /> 启用</label>
        <label class="flex items-center gap-2"><input type="checkbox" v-model="editDlg.row.skip_health" class="accent-[var(--accent)]" /> 跳过健康检测</label>
      </div>
      <template #footer>
        <Button variant="outline" @click="editDlg.open = false">取消</Button>
        <Button @click="saveEdit">保存</Button>
      </template>
    </Dialog>

    <!-- 批量改名弹窗 -->
    <Dialog v-model:open="promptDlg.open" :title="promptDlg.label" width="380px">
      <Input v-model="promptDlg.value" :placeholder="promptDlg.label" />
      <template #footer>
        <Button variant="outline" @click="promptDlg.open = false">取消</Button>
        <Button @click="runPrompt">应用到已选 {{ selected.length }} 项</Button>
      </template>
    </Dialog>

    <!-- auto 规则弹窗 -->
    <Dialog v-model:open="ruleDlg.open" title="新增 auto 路由规则" width="440px">
      <div class="space-y-3 text-[13px]">
        <div><label class="text-xs text-muted">关键词（用户消息包含即命中，不区分大小写）</label>
          <Input v-model="ruleDlg.keyword" class="mt-1" placeholder="例如：画图 / 翻译 / 写代码" /></div>
        <div><label class="text-xs text-muted">目标模型（别名或模型ID）</label>
          <Input v-model="ruleDlg.model_name" class="mt-1" placeholder="例如：glm-5v-turbo" /></div>
        <div><label class="text-xs text-muted">优先级（数字越小越先匹配）</label>
          <Input v-model="ruleDlg.priority" type="number" class="mt-1" /></div>
      </div>
      <template #footer>
        <Button variant="outline" @click="ruleDlg.open = false">取消</Button>
        <Button @click="addRule">保存</Button>
      </template>
    </Dialog>

    <ConfirmDialog v-model:open="confirmState.open" :title="confirmState.title" :message="confirmState.message"
                   danger @confirm="confirmState.action && confirmState.action()" />
  </div>
</template>
