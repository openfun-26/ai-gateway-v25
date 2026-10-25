<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { api } from '../api/client'
import { useUiStore } from '../stores/ui'
import { toast } from '../components/ui/toast'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import Input from '../components/ui/Input.vue'
import Select from '../components/ui/Select.vue'
import Switch from '../components/ui/Switch.vue'
import Badge from '../components/ui/Badge.vue'
import AlertBar from '../components/ui/AlertBar.vue'
import StatusDot from '../components/ui/StatusDot.vue'
import RefreshButton from '../components/ui/RefreshButton.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import Dialog from '../components/ui/Dialog.vue'
import ConfirmDialog from '../components/ui/ConfirmDialog.vue'
import Textarea from '../components/ui/Textarea.vue'
import { fmtMs } from '../components/ui/helpers'
import { Plus, Pencil, Copy, Trash2, FlaskConical, Upload, Power, PowerOff, Zap, ListPlus } from 'lucide-vue-next'

// 常见厂商快速模板：点击自动填充名称 / 端点 / 协议
const VENDOR_PRESETS = [
  { label: 'OpenAI',     name: 'openai',     vendor: 'OpenAI',     base_url: 'https://api.openai.com',                              protocol: 'openai' },
  { label: 'Anthropic',  name: 'anthropic',  vendor: 'Anthropic',  base_url: 'https://api.anthropic.com',                           protocol: 'anthropic' },
  { label: 'DeepSeek',   name: 'deepseek',   vendor: 'DeepSeek',   base_url: 'https://api.deepseek.com',                            protocol: 'openai' },
  { label: 'Kimi',       name: 'kimi',       vendor: 'Moonshot',   base_url: 'https://api.moonshot.cn',                             protocol: 'openai' },
  { label: '通义千问',    name: 'qwen',       vendor: '阿里云',      base_url: 'https://dashscope.aliyuncs.com/compatible-mode',      protocol: 'openai' },
  { label: '智谱 GLM',   name: 'glm',        vendor: '智谱',        base_url: 'https://open.bigmodel.cn/api/paas/v4',                protocol: 'openai' },
  { label: 'Gemini',     name: 'gemini',     vendor: 'Google',     base_url: 'https://generativelanguage.googleapis.com/v1beta/openai', protocol: 'openai' },
  { label: 'xAI',        name: 'xai',        vendor: 'xAI',        base_url: 'https://api.x.ai',                                    protocol: 'openai' },
  { label: 'OpenRouter', name: 'openrouter', vendor: 'OpenRouter', base_url: 'https://openrouter.ai/api',                           protocol: 'openai' },
  { label: '本地 Ollama', name: 'ollama',     vendor: 'Ollama',     base_url: 'http://127.0.0.1:11434',                              protocol: 'openai' }
]
function applyPreset(p) {
  Object.assign(formDlg.value.form, { name: p.name, vendor: p.vendor, base_url: p.base_url, protocol: p.protocol })
}

const ui = useUiStore()
const rows = ref([])
const loading = ref(false)
const selected = ref([])
const confirmState = ref({ open: false, title: '', message: '', action: null })

const emptyForm = () => ({
  name: '', grp: 'default', vendor: '', base_url: '', api_key: '', protocol: 'openai',
  enabled: true, timeout_ms: 60000, weight: 1, max_concurrency: 5, max_retries: 1,
  cooldown_sec: 60, http_proxy: '', extra_headers: '{}', retry_status_codes: [429, 500, 502, 503, 504],
  silent_degrade: false, model_whitelist: '', model_blacklist: '',
  cb_error_threshold: 50, cb_window_sec: 60, cb_freeze_sec: 300, paid: false
})
const formDlg = ref({ open: false, isEdit: false, form: emptyForm() })
const importDlg = ref({ open: false, text: '' })
const testDlg = ref({ open: false, channel: null, model: '', prompt: 'Hello，请回复 pong' })
const testResult = ref(null)
const testing = ref(false)
const fetchDlg = ref({ open: false, channel: null, loading: false, error: '', remote: [], existing: [], selected: [], manual: '' })

// ---------- 拉取上游模型 ----------
async function openFetch(r) {
  fetchDlg.value = { open: true, channel: r, loading: true, error: '', remote: [], existing: [], selected: [], manual: '' }
  try {
    const [f, ex] = await Promise.all([
      api.post(`/admin/api/channels/${r.id}/fetch-models`),
      api.get(`/admin/api/models?channel_id=${r.id}`, { silent: true })
    ])
    if (!f.ok) { fetchDlg.value.error = f.error || '拉取失败'; fetchDlg.value.loading = false; return }
    const existing = (ex.rows || []).map(x => x.upstream_model)
    fetchDlg.value.remote = f.models || []
    fetchDlg.value.existing = existing
    fetchDlg.value.selected = (f.models || []).filter(m => !existing.includes(m))
  } catch (e) {
    fetchDlg.value.error = e.message || '网络错误'
  } finally { fetchDlg.value.loading = false }
}
function toggleAllFetch() {
  const d = fetchDlg.value
  const selectable = d.remote.filter(m => !d.existing.includes(m))
  d.selected = d.selected.length >= selectable.length ? [] : selectable
}
async function confirmImport() {
  const d = fetchDlg.value
  const manual = d.manual.split(/[\n,，;；\s]+/).map(s => s.trim()).filter(Boolean)
  const models = [...d.selected, ...manual]
  if (!models.length) return toast.warning('请勾选或手动输入至少一个模型')
  const r = await api.post(`/admin/api/channels/${d.channel.id}/import-models`, { models })
  if (!r.ok) return toast.error(r.error || '导入失败')
  toast.success(`已添加 ${r.added} 个模型${r.skipped ? `，跳过重复 ${r.skipped} 个` : ''}`)
  d.open = false
  load()
}

async function load() {
  loading.value = true
  try { rows.value = (await api.get('/admin/api/channels', { silent: true })).rows }
  finally { loading.value = false }
}

function openCreate() { formDlg.value = { open: true, isEdit: false, form: emptyForm() } }
function openEdit(r) {
  formDlg.value = { open: true, isEdit: true, form: {
    ...r, enabled: !!r.enabled, silent_degrade: !!r.silent_degrade, paid: !!r.paid,
    retry_status_codes: JSON.parse(r.retry_status_codes || '[]'),
    extra_headers: r.extra_headers || '{}'
  } }
}
async function saveForm() {
  const f = formDlg.value.form
  if (!f.name || !f.base_url) return toast.warning('名称与 API 端点必填')
  const payload = { ...f }
  // OpenAI 协议自动补版本段；已含 /v1、/v4、/v1beta 等版本路径的不补，避免破坏特殊端点
  if (payload.protocol === 'openai' && payload.base_url && !/\/v\d+[a-z]*(\/|$)/.test(payload.base_url)) {
    payload.base_url = payload.base_url.replace(/\/+$/, '') + '/v1'
  }
  try { JSON.parse(payload.extra_headers || '{}') } catch { return toast.warning('附加请求头必须是合法 JSON') }
  if (formDlg.value.isEdit) await api.put(`/admin/api/channels/${payload.id}`, payload)
  else await api.post('/admin/api/channels', payload)
  toast.success(formDlg.value.isEdit ? '渠道已更新' : '渠道已创建')
  formDlg.value.open = false
  load()
}
async function duplicate(r) {
  const res = await api.post(`/admin/api/channels/${r.id}/duplicate`)
  toast.success(`已复制为新渠道 #${res.id}（含模型）`)
  load()
}
function askDelete(r) {
  confirmState.value = { open: true, title: '删除渠道', message: `确认删除渠道「${r.name}」？其下模型映射将一并删除。`,
    action: async () => { await api.del(`/admin/api/channels/${r.id}`); toast.success('已删除'); load() } }
}
async function batch(action) {
  if (!selected.value.length) return toast.warning('请先勾选渠道')
  await api.post('/admin/api/channels/batch', { action, ids: selected.value })
  toast.success('批量操作完成')
  selected.value = []
  load()
}
async function runImport() {
  const r = await api.post('/admin/api/channels/import', { text: importDlg.value.text })
  toast.success(`成功导入 ${r.added} 个渠道`)
  if (r.errors?.length) toast.error(r.errors.slice(0, 3).join('；'))
  importDlg.value.open = false
  importDlg.value.text = ''
  load()
}

async function runTest() {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await api.post(`/admin/api/channels/${testDlg.value.channel.id}/test`,
      { model: testDlg.value.model, prompt: testDlg.value.prompt })
  } catch (e) { testResult.value = { ok: false, error: e.message } }
  finally { testing.value = false }
}
function openTest(r) {
  testDlg.value.channel = r
  testDlg.value.model = ''
  testResult.value = null
  testDlg.value.open = true
}

const retryCodeOpts = [400, 401, 403, 404, 408, 429, 500, 502, 503, 504]
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
          <Button size="sm" @click="openCreate"><Plus :size="14" /> 新建渠道</Button>
          <Button size="sm" variant="outline" @click="importDlg.open = true"><Upload :size="14" /> 批量导入</Button>
          <template v-if="selected.length">
            <Badge variant="accent">已选 {{ selected.length }}</Badge>
            <Button size="sm" variant="outline" @click="batch('enable')"><Power :size="13" /> 启用</Button>
            <Button size="sm" variant="outline" @click="batch('disable')"><PowerOff :size="13" /> 禁用</Button>
            <Button size="sm" variant="destructive" @click="batch('delete')"><Trash2 :size="13" /> 批量删除</Button>
          </template>
          <RefreshButton :loading="loading" @refresh="load" />
        </div>
      </template>

      <div class="overflow-x-auto">
        <table class="w-full text-[12.5px] whitespace-nowrap">
          <thead>
            <tr class="text-left text-muted border-b border-[var(--border)]">
              <th class="py-2 w-8"><input type="checkbox" class="accent-[var(--accent)] cursor-pointer"
                  :checked="selected.length === rows.length && rows.length > 0"
                  @change="selected = $event.target.checked ? rows.map(r => r.id) : []" /></th>
              <th class="py-2 px-1.5">启用</th><th class="py-2 px-1.5">名称</th><th class="py-2 px-1.5">分组</th>
              <th class="py-2 px-1.5">协议</th><th class="py-2 px-1.5">Base URL</th>
              <th class="py-2 px-1.5">Key</th><th class="py-2 px-1.5">模型数</th>
              <th class="py-2 px-1.5 text-right">并发</th><th class="py-2 px-1.5 text-right">今日请求</th>
              <th class="py-2 px-1.5 text-right">今日失败</th><th class="py-2 px-1.5 text-right">成功率</th>
              <th class="py-2 px-1.5 text-right">平均耗时</th><th class="py-2 px-1.5">熔断</th>
              <th class="py-2 px-1.5">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.id" class="border-b border-[var(--border)]/50 hover:bg-[var(--hover)]"
                :class="r.enabled ? '' : 'opacity-45'">
              <td class="py-2"><input type="checkbox" class="accent-[var(--accent)] cursor-pointer"
                  :checked="selected.includes(r.id)"
                  @change="$event.target.checked ? selected.push(r.id) : (selected = selected.filter(i => i !== r.id))" /></td>
              <td class="px-1.5"><Switch :model-value="!!r.enabled" @update:model-value="api.put(`/admin/api/channels/${r.id}`, { enabled: $event ? 1 : 0 }).then(load)" /></td>
              <td class="px-1.5 font-semibold">{{ r.name }} <Badge v-if="r.vendor" size="sm">{{ r.vendor }}</Badge></td>
              <td class="px-1.5">{{ r.grp }}</td>
              <td class="px-1.5"><Badge size="sm" :variant="r.protocol === 'anthropic' ? 'info' : 'accent'">{{ r.protocol }}</Badge></td>
              <td class="px-1.5 max-w-[200px] truncate text-muted" :title="r.base_url">{{ r.base_url }}</td>
              <td class="px-1.5 font-mono text-[11px] text-muted">{{ r.api_key_masked }}</td>
              <td class="px-1.5">
                <button class="underline decoration-dotted underline-offset-2 cursor-pointer hover:text-[var(--accent)]"
                        :class="r.model_count ? '' : 'text-amber-500'"
                        :title="r.model_count ? '查看/管理该渠道模型' : '该渠道还没有模型，点击拉取或手动添加'"
                        @click="openFetch(r)">{{ r.model_count }}</button>
              </td>
              <td class="px-1.5 text-right">{{ r.current_concurrency }}/{{ r.max_concurrency }}</td>
              <td class="px-1.5 text-right">{{ r.today_requests }}</td>
              <td class="px-1.5 text-right" :class="r.today_failures ? 'text-red-500' : ''">{{ r.today_failures }}</td>
              <td class="px-1.5 text-right">{{ r.success_rate ?? 100 }}%</td>
              <td class="px-1.5 text-right">{{ fmtMs(r.avg_latency_ms) }}</td>
              <td class="px-1.5"><StatusDot :status="r.circuit_state === 'open' ? 'offline' : 'online'"
                  :tooltip="r.circuit_state === 'open' ? '熔断中' : '正常'" /></td>
              <td class="px-1.5">
                <div class="flex gap-0.5">
                  <Button size="icon" variant="ghost" @click="openEdit(r)" title="编辑"><Pencil :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" @click="duplicate(r)" title="复制新建"><Copy :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" @click="openFetch(r)" title="拉取模型（从上游获取可用模型并挂到该渠道）"><ListPlus :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" @click="openTest(r)" title="连通性测试"><FlaskConical :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" class="text-red-500" @click="askDelete(r)" title="删除"><Trash2 :size="13.5" /></Button>
                </div>
              </td>
            </tr>
            <tr v-if="!rows.length"><td colspan="15"><EmptyState message="暂无渠道，点击右上角新建或批量导入" /></td></tr>
          </tbody>
        </table>
      </div>
    </Card>

    <!-- 新建/编辑弹窗 -->
    <Dialog v-model:open="formDlg.open" :title="formDlg.isEdit ? '编辑渠道' : '新建渠道'" width="640px">
      <div class="grid grid-cols-2 gap-x-4 gap-y-3 text-[13px]">
        <div class="col-span-2">
          <div class="flex items-center gap-1 text-xs text-muted"><Zap :size="12" class="text-[var(--accent)]" /> 厂商快速模板（点击自动填充名称 / 端点 / 协议）</div>
          <div class="flex flex-wrap gap-1.5 mt-1.5">
            <button v-for="p in VENDOR_PRESETS" :key="p.label" type="button" @click="applyPreset(p)"
                    class="h-7 px-2.5 rounded-full hairline bg-card text-[12px] hover:bg-[var(--accent-soft)] hover:text-[var(--accent)] hover:border-transparent transition cursor-pointer">
              {{ p.label }}
            </button>
          </div>
        </div>
        <div><label class="text-xs text-muted">名称 *</label><Input v-model="formDlg.form.name" class="mt-1" placeholder="如 openai-main" /></div>
        <div><label class="text-xs text-muted">分组</label><Input v-model="formDlg.form.grp" class="mt-1" placeholder="default" /></div>
        <div><label class="text-xs text-muted">厂商备注</label><Input v-model="formDlg.form.vendor" class="mt-1" placeholder="openai / azure / 智谱 …" /></div>
        <div><label class="text-xs text-muted">协议类型</label>
          <Select v-model="formDlg.form.protocol" class="mt-1" :options="[{ value: 'openai', label: 'OpenAI' }, { value: 'anthropic', label: 'Anthropic (Claude)' }]" /></div>
        <div class="col-span-2"><label class="text-xs text-muted">API 端点 *（OpenAI 协议自动补末尾 /v1）</label>
          <Input v-model="formDlg.form.base_url" class="mt-1" placeholder="https://api.openai.com" /></div>
        <div class="col-span-2"><label class="text-xs text-muted">上游 API Key</label>
          <Input v-model="formDlg.form.api_key" class="mt-1" type="password" placeholder="sk-..." /></div>
        <div><label class="text-xs text-muted">超时 (ms)</label><Input v-model="formDlg.form.timeout_ms" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">权重</label><Input v-model="formDlg.form.weight" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">最大并发</label><Input v-model="formDlg.form.max_concurrency" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">重试次数</label><Input v-model="formDlg.form.max_retries" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">失败冷却 (秒)</label><Input v-model="formDlg.form.cooldown_sec" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">HTTP 代理</label><Input v-model="formDlg.form.http_proxy" class="mt-1" placeholder="http://127.0.0.1:7890" /></div>
        <div class="col-span-2"><label class="text-xs text-muted">附加请求头（JSON）</label>
          <Textarea v-model="formDlg.form.extra_headers" :rows="2" mono class="mt-1" placeholder='{"CF-Worker": "xxx"}' /></div>
        <div><label class="text-xs text-muted">模型白名单（逗号分隔）</label><Input v-model="formDlg.form.model_whitelist" class="mt-1" /></div>
        <div><label class="text-xs text-muted">模型黑名单（逗号分隔）</label><Input v-model="formDlg.form.model_blacklist" class="mt-1" /></div>
        <div class="col-span-2">
          <label class="text-xs text-muted">允许重试的 HTTP 状态码</label>
          <div class="flex flex-wrap gap-2 mt-1.5">
            <label v-for="c in retryCodeOpts" :key="c" class="flex items-center gap-1 text-[12px] cursor-pointer">
              <input type="checkbox" class="accent-[var(--accent)]" :value="c" v-model="formDlg.form.retry_status_codes" /> {{ c }}
            </label>
          </div>
        </div>
        <div class="col-span-2 border-t border-[var(--border)] pt-3">
          <div class="text-xs text-muted mb-2">每渠道独立熔断器</div>
          <div class="grid grid-cols-3 gap-3">
            <div><label class="text-[11px] text-muted">错误率阈值 %</label><Input v-model="formDlg.form.cb_error_threshold" type="number" class="mt-1" /></div>
            <div><label class="text-[11px] text-muted">统计窗口 (秒)</label><Input v-model="formDlg.form.cb_window_sec" type="number" class="mt-1" /></div>
            <div><label class="text-[11px] text-muted">熔断持续 (秒)</label><Input v-model="formDlg.form.cb_freeze_sec" type="number" class="mt-1" /></div>
          </div>
        </div>
        <label class="flex items-center gap-2">启用 <Switch v-model="formDlg.form.enabled" /></label>
        <label class="flex items-center gap-2">静默降级（失败跳下一渠道） <Switch v-model="formDlg.form.silent_degrade" /></label>
        <label class="flex items-center gap-2" title="auto 智能路由默认跳过付费渠道，防止误触付费模型产生费用">💸 付费渠道（auto 默认排除） <Switch v-model="formDlg.form.paid" /></label>
      </div>
      <template #footer>
        <Button variant="outline" @click="formDlg.open = false">取消</Button>
        <Button @click="saveForm">{{ formDlg.isEdit ? '保存' : '创建' }}</Button>
      </template>
    </Dialog>

    <!-- 批量导入 -->
    <Dialog v-model:open="importDlg.open" title="批量导入渠道" width="620px">
      <div class="space-y-2">
        <div class="text-[12.5px] text-muted leading-relaxed rounded-card bg-[var(--hover)] p-3">
          每行一个渠道，两种格式均支持：<br />
          ① JSON：<code class="text-[11px]">{"name":"x","grp":"default","base_url":"https://api.x.com/v1","api_key":"sk-..","protocol":"openai"}</code><br />
          ② 管道分隔：<code class="text-[11px]">名称|分组|base_url|key|协议</code>
        </div>
        <Textarea v-model="importDlg.text" :rows="10" mono
                  placeholder="openai主渠道|default|https://api.openai.com/v1|sk-xxx|openai" />
        <Button @click="runImport"><Upload :size="14" /> 开始导入</Button>
      </div>
    </Dialog>

    <!-- 连通性测试 -->
    <Dialog v-model:open="testDlg.open" title="渠道连通性测试" width="560px">
      <div class="space-y-3" v-if="testDlg.channel">
        <div class="text-[12.5px] text-muted">渠道：<b class="text-content">{{ testDlg.channel.name }}</b>（{{ testDlg.channel.protocol }}）</div>
        <div><label class="text-xs text-muted">模型</label><Input v-model="testDlg.model" class="mt-1" placeholder="留空则用 gpt-4o-mini / claude-3-haiku" /></div>
        <div><label class="text-xs text-muted">Prompt</label><Textarea v-model="testDlg.prompt" :rows="2" class="mt-1" /></div>
        <Button :disabled="testing" @click="runTest"><FlaskConical :size="14" /> {{ testing ? '测试中…' : '发送测试' }}</Button>
        <div v-if="testResult" class="rounded-card hairline p-3 text-[12.5px] space-y-2">
          <div v-if="testResult.ok">
            <Badge variant="success">成功</Badge>
            <span class="ml-2 text-muted">耗时 {{ testResult.latency_ms }}ms · P {{ testResult.prompt_tokens }} / C {{ testResult.completion_tokens }} tok</span>
            <div class="mt-2 p-2 rounded-md bg-[var(--hover)] whitespace-pre-wrap break-all">{{ testResult.content }}</div>
          </div>
          <div v-else><Badge variant="error">失败</Badge><span class="ml-2 text-red-500 break-all">{{ testResult.error }}</span></div>
        </div>
      </div>
    </Dialog>

    <!-- 拉取模型 -->
    <Dialog v-model:open="fetchDlg.open" :title="`拉取模型 · ${fetchDlg.channel?.name || ''}`" width="580px">
      <div class="space-y-3">
        <div v-if="fetchDlg.loading" class="py-10 text-center text-[13px] text-muted">正在从上游拉取模型列表…</div>
        <template v-else>
          <AlertBar v-if="fetchDlg.error" variant="warning">
            {{ fetchDlg.error }}（可在下方手动输入模型名）
          </AlertBar>
          <div v-if="fetchDlg.remote.length">
            <div class="flex items-center justify-between text-xs text-muted mb-1.5">
              <span>上游共 {{ fetchDlg.remote.length }} 个模型，已选 {{ fetchDlg.selected.length }} 个</span>
              <button class="text-[var(--accent)] cursor-pointer hover:underline" @click="toggleAllFetch">全选 / 全不选</button>
            </div>
            <div class="max-h-60 overflow-y-auto rounded-card hairline p-2 grid grid-cols-1 sm:grid-cols-2 gap-x-2">
              <label v-for="m in fetchDlg.remote" :key="m"
                     class="flex items-center gap-2 text-[12.5px] px-1.5 py-1 rounded hover:bg-[var(--hover)] cursor-pointer"
                     :class="fetchDlg.existing.includes(m) ? 'opacity-45' : ''">
                <input type="checkbox" class="accent-[var(--accent)] shrink-0" :disabled="fetchDlg.existing.includes(m)"
                       :checked="fetchDlg.selected.includes(m)"
                       @change="$event.target.checked ? fetchDlg.selected.push(m) : (fetchDlg.selected = fetchDlg.selected.filter(x => x !== m))" />
                <span class="truncate font-mono text-[11.5px]" :title="m">{{ m }}</span>
                <Badge v-if="fetchDlg.existing.includes(m)" size="sm" class="ml-auto shrink-0">已添加</Badge>
              </label>
            </div>
          </div>
          <div v-else-if="!fetchDlg.error">
            <EmptyState message="上游未返回模型列表" />
          </div>
          <div>
            <label class="text-xs text-muted">手动补充模型（逗号 / 换行分隔，自动跳过重复）</label>
            <Textarea v-model="fetchDlg.manual" :rows="3" mono class="mt-1" placeholder="gpt-4o, gpt-4o-mini, claude-sonnet-4-20250514" />
          </div>
          <Button @click="confirmImport"><ListPlus :size="14" /> 导入选中与手动输入的模型</Button>
        </template>
      </div>
    </Dialog>

    <ConfirmDialog v-model:open="confirmState.open" :title="confirmState.title" :message="confirmState.message" danger @confirm="confirmState.action && confirmState.action()" />
  </div>
</template>
