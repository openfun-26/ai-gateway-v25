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
import StatusDot from '../components/ui/StatusDot.vue'
import Textarea from '../components/ui/Textarea.vue'
import Dialog from '../components/ui/Dialog.vue'
import ConfirmDialog from '../components/ui/ConfirmDialog.vue'
import { Plus, Pencil, Trash2, Save, Download, Upload, Database, Play, Square, Terminal, ShieldX } from 'lucide-vue-next'

const ui = useUiStore()
const s = ref({})
const loading = ref(false)
const confirmState = ref({ open: false, title: '', message: '', action: null })

async function load() {
  loading.value = true
  try { s.value = (await api.get('/admin/api/settings', { silent: true })).settings }
  finally { loading.value = false }
}

async function save() {
  const payload = { ...s.value }
  delete payload.frp_config
  const r = await api.put('/admin/api/settings', payload)
  toast.success(r.message || '设置已保存')
  if (r.port_changed) toast.warning('监听端口已修改：重启进程后生效')
  load()
}

// ---------- 反代规则 ----------
const proxyRules = ref([])
const proxyDlg = ref({ open: false, isEdit: false, form: {} })
async function loadProxy() { proxyRules.value = (await api.get('/admin/api/proxy-rules', { silent: true })).rows }
function openProxyCreate() { proxyDlg.value = { open: true, isEdit: false, form: { name: '', path_prefix: '', target_url: '', api_key: '', vendor_tag: '', enabled: true } } }
function openProxyEdit(r) { proxyDlg.value = { open: true, isEdit: true, form: { ...r, enabled: !!r.enabled } } }
async function saveProxy() {
  const f = proxyDlg.value.form
  if (!f.name || !f.path_prefix || !f.target_url) return toast.warning('名称/路径前缀/目标地址必填')
  if (!f.path_prefix.startsWith('/')) f.path_prefix = '/' + f.path_prefix
  if (proxyDlg.value.isEdit) await api.put(`/admin/api/proxy-rules/${f.id}`, f)
  else await api.post('/admin/api/proxy-rules', f)
  toast.success('反代规则已保存（透传强制写日志）')
  proxyDlg.value.open = false
  loadProxy()
}
function askDeleteProxy(r) {
  confirmState.value = { open: true, title: '删除反代规则', message: `确认删除「${r.name}」？`,
    action: async () => { await api.del(`/admin/api/proxy-rules/${r.id}`); loadProxy() } }
}

// ---------- 模型黑名单 ----------
const blacklist = ref([])
const blInput = ref('')
async function loadBlacklist() { blacklist.value = (await api.get('/admin/api/blacklist', { silent: true })).rows }
async function addBlacklist() {
  if (!blInput.value.trim()) return
  await api.post('/admin/api/blacklist', { model: blInput.value.trim() })
  blInput.value = ''
  toast.success('已加入全局黑名单')
  loadBlacklist()
}
async function delBlacklist(r) { await api.del(`/admin/api/blacklist/${r.id}`); loadBlacklist() }

// ---------- 配置导入导出 ----------
async function exportConfig() {
  const data = await api.get('/admin/api/settings/export', { silent: true })
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'gateway_config.json'
  a.click()
  URL.revokeObjectURL(a.href)
  toast.success('配置已导出')
}
const importText = ref('')
const importDlg = ref({ open: false, mode: 'overwrite' })
async function runImport() {
  try {
    const data = JSON.parse(importText.value)
    await api.post('/admin/api/settings/import', { ...data, mode: importDlg.value.mode })
    toast.success('配置已导入')
    importDlg.value.open = false
    importText.value = ''
    load(); loadProxy(); loadBlacklist()
  } catch (e) { toast.error(`导入失败: ${e.message}`) }
}
async function vacuum() {
  toast.info('正在 VACUUM…')
  await api.post('/admin/api/settings/vacuum')
  toast.success('数据库已压缩')
}

// ---------- FRP ----------
const frpStatus = ref({})
const frpCfg = ref({ config: '', autostart: false, validation: { warnings: [] } })
const frpLogs = ref([])
const frpLogDlg = ref(false)
let frpTimer = null
async function loadFrp() {
  const cfg = await api.get('/admin/api/frp/config', { silent: true })
  frpCfg.value = { ...cfg, autostart: !!cfg.autostart, validation: cfg.validation || { warnings: [] } }
  frpStatus.value = await api.get('/admin/api/frp/status', { silent: true })
}
async function saveFrp() {
  const r = await api.put('/admin/api/frp/config', { config: frpCfg.value.config, autostart: frpCfg.value.autostart })
  frpCfg.value.validation = r.validation || { warnings: [] }
  toast.success('FRP 配置已保存')
}
async function frpStart() {
  const r = await api.post('/admin/api/frp/start')
  r.ok ? toast.success(r.message) : toast.error(r.message)
  loadFrp()
}
async function frpStop() {
  const r = await api.post('/admin/api/frp/stop')
  r.ok ? toast.success(r.message) : toast.error(r.message)
  loadFrp()
}
async function openFrpLogs() {
  frpLogDlg.value = true
  await refreshFrpLogs()
  clearInterval(frpTimer)
  frpTimer = setInterval(refreshFrpLogs, 1500)
}
async function refreshFrpLogs() {
  frpLogs.value = (await api.get('/admin/api/frp/logs', { silent: true })).logs
  await Promise.resolve()
  const el = document.getElementById('frp-log-box')
  if (el) el.scrollTop = el.scrollHeight
}
async function clearFrpLogs() { await api.post('/admin/api/frp/logs/clear'); frpLogs.value = [] }

const dotStatus = () => frpStatus.value.running ? 'online' : (frpStatus.value.state === 'error' ? 'offline' : 'stopped')

onMounted(() => { load(); loadProxy(); loadBlacklist(); loadFrp() })
onBeforeUnmount(() => clearInterval(frpTimer))
</script>

<template>
  <div class="space-y-4 pb-8">
    <!-- 基础设置 -->
    <Card title="基础设置">
      <template #header>
        <div class="flex items-center gap-2">
          <Button size="sm" :disabled="loading" @click="save"><Save :size="14" /> 保存全部设置</Button>
          <RefreshButton :loading="loading" @refresh="load" />
        </div>
      </template>
      <div class="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-3 text-[13px]">
        <div><label class="text-xs text-muted">网关监听端口</label>
          <Input v-model="s.port" type="number" class="mt-1" />
          <p class="text-[11px] text-amber-500 mt-1">⚠ 修改后需重启进程生效</p></div>
        <div><label class="text-xs text-muted">管理台端口（仅内网）</label>
          <Input v-model="s.admin_port" type="number" class="mt-1" />
          <p class="text-[11px] text-amber-500 mt-1">⚠ 管理台独立端口，不随 API 穿透外网；修改后需重启</p></div>
        <div><label class="text-xs text-muted">CORS 允许来源（逗号分隔）</label>
          <Input v-model="s.cors_origins" class="mt-1" placeholder="*" /></div>
        <div><label class="text-xs text-muted">全局 RPS 限流（0 不限）</label>
          <Input v-model="s.global_rps" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">全局健康检测超时 (秒)</label>
          <Input v-model="s.health_timeout_sec" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">定时检测间隔 (秒，0 关闭)</label>
          <Input v-model="s.health_interval_sec" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">日志保留天数</label>
          <Input v-model="s.log_retention_days" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">日志保留条数上限</label>
          <Input v-model="s.log_max_rows" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">默认主题（新设备初始值）</label>
          <Select v-model="s.theme_default" class="mt-1" :options="[{ value: 'light', label: '浅色' }, { value: 'dark', label: '深色' }]" /></div>
        <div><label class="text-xs text-muted">默认强调色</label>
          <Select v-model="s.accent_default" class="mt-1" :options="[
            { value: 'teal', label: '青绿' }, { value: 'blue', label: '蓝' }, { value: 'purple', label: '紫' },
            { value: 'amber', label: '琥珀' }, { value: 'rose', label: '玫红' }, { value: 'slate', label: '石板灰蓝' }]" /></div>
      </div>
      <div class="flex flex-wrap gap-2 mt-4 pt-3 border-t border-[var(--border)]">
        <Button variant="outline" @click="vacuum"><Database :size="14" /> 数据库 VACUUM</Button>
        <Button variant="outline" @click="exportConfig"><Download :size="14" /> 导出配置</Button>
        <Button variant="outline" @click="importDlg.open = true"><Upload :size="14" /> 导入配置</Button>
        <Button variant="destructive" @click="confirmState = { open: true, title: '重置全部统计',
          message: '将清空日志与全部统计数据（渠道/密钥计数归零），确认？',
          action: async () => { await api.post('/admin/api/dashboard/reset-stats'); toast.success('已重置') } }">
          <ShieldX :size="14" /> 重置全部统计</Button>
      </div>
    </Card>

    <!-- 反代规则 -->
    <Card title="反代 OpenAI 透传规则" subtitle="命中路径前缀的请求原样透传到目标地址（网关保留端点除外），强制写日志并纳入全局统计">
      <template #header>
        <div class="flex items-center gap-2">
          <Button size="sm" @click="openProxyCreate"><Plus :size="14" /> 新增规则</Button>
          <RefreshButton :loading="false" @refresh="loadProxy" />
        </div>
      </template>
      <div class="overflow-x-auto" v-if="proxyRules.length">
        <table class="w-full text-[12.5px] whitespace-nowrap">
          <thead>
            <tr class="text-left text-muted border-b border-[var(--border)]">
              <th class="py-2 px-1.5">启用</th><th class="py-2 px-1.5">名称</th><th class="py-2 px-1.5">路径前缀</th>
              <th class="py-2 px-1.5">目标 Base URL</th><th class="py-2 px-1.5">上游 Key</th>
              <th class="py-2 px-1.5">厂商标签</th><th class="py-2 px-1.5">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in proxyRules" :key="r.id" class="border-b border-[var(--border)]/50 hover:bg-[var(--hover)]"
                :class="r.enabled ? '' : 'opacity-45'">
              <td class="px-1.5 py-2"><Badge size="sm" :variant="r.enabled ? 'success' : 'default'">{{ r.enabled ? '启用' : '停用' }}</Badge></td>
              <td class="px-1.5 font-semibold">{{ r.name }}</td>
              <td class="px-1.5 font-mono text-[12px]">{{ r.path_prefix }}</td>
              <td class="px-1.5 max-w-[220px] truncate text-muted" :title="r.target_url">{{ r.target_url }}</td>
              <td class="px-1.5 font-mono text-[11px] text-muted">{{ r.api_key_masked || '透传客户端' }}</td>
              <td class="px-1.5">{{ r.vendor_tag || '-' }}</td>
              <td class="px-1.5">
                <div class="flex gap-0.5">
                  <Button size="icon" variant="ghost" @click="openProxyEdit(r)"><Pencil :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" class="text-red-500" @click="askDeleteProxy(r)"><Trash2 :size="13.5" /></Button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="text-[13px] text-muted py-3">暂无反代规则。示例：前缀 <code>/openai</code> → 目标 <code>https://api.openai.com/v1</code>，则 POST /openai/chat/completions 会被原样透传。</p>
    </Card>

    <!-- 模型黑名单 -->
    <Card title="全局模型黑名单" subtitle="命中黑名单的模型请求将被 403 拦截并落日志">
      <div class="flex gap-2 mb-3 max-w-md">
        <Input v-model="blInput" placeholder="输入模型名，如 gpt-4o" @keyup.enter="addBlacklist" />
        <Button @click="addBlacklist"><Plus :size="14" /> 添加</Button>
      </div>
      <div class="flex flex-wrap gap-1.5">
        <Badge v-for="b in blacklist" :key="b.id" variant="error" class="!text-[12px] !px-3 !py-1 cursor-pointer"
               :title="b.reason || '点击移除'" @click="delBlacklist(b)">
          {{ b.model }} ✕
        </Badge>
        <span v-if="!blacklist.length" class="text-[13px] text-muted">黑名单为空</span>
      </div>
    </Card>

    <!-- FRP 管理 -->
    <Card title="FRP 内网穿透管理"
          subtitle="本程序不内置 frpc 二进制：请自行下载对应平台（Termux 为 aarch64）版本放入项目根目录并 chmod +x frpc。FRP 用于把本地 9010 端口暴露到公网；外网访问仍走网关全部鉴权/限流/日志管线。">
      <template #header>
        <span class="inline-flex items-center gap-2 text-[12.5px]">
          <StatusDot :status="dotStatus()" size="9" />
          {{ frpStatus.running ? '🟢 运行中' + (frpStatus.pid ? ` (PID ${frpStatus.pid})` : '') : (frpStatus.state === 'error' ? '🔴 错误' : '🟡 未运行') }}
        </span>
      </template>
      <div class="space-y-3">
        <Textarea v-model="frpCfg.config" :rows="9" mono
                  placeholder="[common]
server_addr = your.server.com
server_port = 7000
token = your_token

[web]
type = http
local_port = 9010
custom_domains = gw.example.com" />
        <AlertBar v-for="(w, i) in frpCfg.validation.warnings || []" :key="i" variant="warning">{{ w }}</AlertBar>
        <div class="flex flex-wrap items-center gap-2">
          <Button variant="accent-soft" @click="saveFrp"><Save :size="14" /> 保存配置</Button>
          <Button @click="frpStart" :disabled="frpStatus.running"><Play :size="14" /> 启动 FRP</Button>
          <Button variant="outline" @click="frpStop" :disabled="!frpStatus.running"><Square :size="14" /> 停止 FRP</Button>
          <Button variant="outline" @click="openFrpLogs"><Terminal :size="14" /> 查看实时日志</Button>
          <label class="flex items-center gap-2 text-[13px] ml-1">
            <Switch v-model="frpCfg.autostart" @update:model-value="api.put('/admin/api/frp/config', { config: frpCfg.config, autostart: $event })" />
            网关启动时自动启动 FRP
          </label>
          <Badge v-if="!frpStatus.binary_exists" variant="warning">未检测到 frpc 二进制</Badge>
        </div>
        <p class="text-[11.5px] text-muted">提示：ini 中 <code>local_port</code> 必须为 9010 才能穿透到网关（不一致会黄条警告但不阻断启动）。</p>
      </div>
    </Card>

    <!-- 反代规则弹窗 -->
    <Dialog v-model:open="proxyDlg.open" :title="proxyDlg.isEdit ? '编辑反代规则' : '新增反代规则'" width="540px">
      <div class="grid grid-cols-2 gap-3 text-[13px]">
        <div><label class="text-xs text-muted">名称 *</label><Input v-model="proxyDlg.form.name" class="mt-1" /></div>
        <div><label class="text-xs text-muted">厂商标签</label><Input v-model="proxyDlg.form.vendor_tag" class="mt-1" /></div>
        <div><label class="text-xs text-muted">匹配路径前缀 *</label><Input v-model="proxyDlg.form.path_prefix" class="mt-1" placeholder="/openai" /></div>
        <div><label class="text-xs text-muted">目标 Base URL *</label><Input v-model="proxyDlg.form.target_url" class="mt-1" placeholder="https://api.openai.com/v1" /></div>
        <div class="col-span-2"><label class="text-xs text-muted">上游 Key（留空则透传客户端 Authorization）</label>
          <Input v-model="proxyDlg.form.api_key" type="password" class="mt-1" /></div>
        <label class="flex items-center gap-2">启用 <Switch v-model="proxyDlg.form.enabled" /></label>
      </div>
      <template #footer>
        <Button variant="outline" @click="proxyDlg.open = false">取消</Button>
        <Button @click="saveProxy">保存</Button>
      </template>
    </Dialog>

    <!-- 配置导入弹窗 -->
    <Dialog v-model:open="importDlg.open" title="导入配置" width="600px">
      <div class="space-y-3">
        <Select v-model="importDlg.mode" :options="[{ value: 'overwrite', label: '覆盖（清空现有后导入）' }, { value: 'merge', label: '增量（保留现有，追加导入）' }]" />
        <Textarea v-model="importText" :rows="10" mono placeholder="粘贴导出的 gateway_config.json 内容" />
        <Button @click="runImport"><Upload :size="14" /> 执行导入</Button>
      </div>
    </Dialog>

    <!-- FRP 日志弹窗 -->
    <Dialog v-model:open="frpLogDlg" title="FRP 实时日志" width="720px" @update:open="v => { if (!v) clearInterval(frpTimer) }">
      <div class="space-y-2">
        <div class="flex justify-end gap-2">
          <Button size="sm" variant="outline" @click="clearFrpLogs">清空</Button>
        </div>
        <div id="frp-log-box" class="h-72 overflow-y-auto rounded-card hairline bg-[var(--hover)] p-3 font-mono text-[11.5px] leading-relaxed">
          <div v-if="!frpLogs.length" class="text-muted">暂无日志（内存环形缓冲，网关重启即清空）</div>
          <div v-for="(l, i) in frpLogs" :key="i" class="whitespace-pre-wrap break-all">{{ l }}</div>
        </div>
      </div>
    </Dialog>

    <ConfirmDialog v-model:open="confirmState.open" :title="confirmState.title" :message="confirmState.message" danger @confirm="confirmState.action && confirmState.action()" />
  </div>
</template>
