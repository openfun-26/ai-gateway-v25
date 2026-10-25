<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api/client'
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
import { Plus, Pencil, Trash2, ArrowUp, ArrowDown, Save } from 'lucide-vue-next'

const data = ref(null)
const loading = ref(false)
const saving = ref(false)
const confirmState = ref({ open: false, title: '', message: '', action: null })

const ruleDlg = ref({ open: false, isEdit: false, form: { match_type: 'model', match_value: '', target_group: '', priority: 0, enabled: true } })

const strategyOpts = [
  { value: 'round_robin', label: '轮询' },
  { value: 'weighted_round_robin', label: '权重轮询' },
  { value: 'least_concurrency', label: '最少并发优先' },
  { value: 'least_latency', label: '最小平均延迟优先' },
  { value: 'failover', label: '故障降级' }
]

async function load() {
  loading.value = true
  try { data.value = await api.get('/admin/api/routing', { silent: true }) }
  finally { loading.value = false }
}

async function saveGlobal() {
  saving.value = true
  try {
    await api.put('/admin/api/routing/global', data.value)
    toast.success('全局策略已保存')
  } finally { saving.value = false }
}

function openCreate() {
  ruleDlg.value = { open: true, isEdit: false, form: { match_type: 'model', match_value: '', target_group: '', priority: (data.value.rules.at(-1)?.priority ?? 0) + 1, enabled: true } }
}
function openEdit(r) { ruleDlg.value = { open: true, isEdit: true, form: { ...r, enabled: !!r.enabled } } }
async function saveRule() {
  const f = ruleDlg.value.form
  if (!f.match_value || !f.target_group) return toast.warning('匹配条件与目标渠道组必填')
  if (ruleDlg.value.isEdit) await api.put(`/admin/api/routing/rules/${f.id}`, f)
  else await api.post('/admin/api/routing/rules', f)
  toast.success('规则已保存')
  ruleDlg.value.open = false
  load()
}
function askDelete(r) {
  confirmState.value = { open: true, title: '删除规则', message: `确认删除该路由规则？`,
    action: async () => { await api.del(`/admin/api/routing/rules/${r.id}`); toast.success('已删除'); load() } }
}
async function move(r, direction) {
  await api.post(`/admin/api/routing/rules/${r.id}/move`, { direction })
  load()
}
async function toggle(r) {
  await api.put(`/admin/api/routing/rules/${r.id}`, { enabled: r.enabled ? 0 : 1 })
  load()
}

onMounted(load)
</script>

<template>
  <div class="space-y-4 pb-8" v-if="data">
    <Card title="全局路由策略">
      <template #header><RefreshButton :loading="loading" @refresh="load" /></template>
      <div class="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-3 text-[13px]">
        <div><label class="text-xs text-muted">策略五选一</label>
          <Select v-model="data.strategy" class="mt-1" :options="strategyOpts" /></div>
        <div><label class="text-xs text-muted">全局最大重试次数</label>
          <Input v-model="data.global_max_retries" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">上游报错自动冻结时长 (秒)</label>
          <Input v-model="data.upstream_freeze_sec" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">熔断错误率阈值 %</label>
          <Input v-model="data.circuit_error_threshold" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">熔断统计窗口 (秒)</label>
          <Input v-model="data.circuit_window_sec" type="number" class="mt-1" /></div>
        <div><label class="text-xs text-muted">熔断持续 (秒)</label>
          <Input v-model="data.circuit_freeze_sec" type="number" class="mt-1" /></div>
        <label class="flex items-center gap-2 col-span-2 md:col-span-3">
          动态自适应权重（按渠道实时成功率自动修正权重）
          <Switch v-model="data.auto_adaptive_weight" /></label>
      </div>
      <div class="mt-4"><Button :disabled="saving" @click="saveGlobal"><Save :size="14" /> {{ saving ? '保存中…' : '保存全局策略' }}</Button></div>
    </Card>

    <Card title="条件路由规则" subtitle="按优先级从上到下匹配：先命中先生效（模型级专属规则优先于本表，见模型监控页编辑）">
      <template #header>
        <div class="flex items-center gap-2">
          <Button size="sm" @click="openCreate"><Plus :size="14" /> 新增规则</Button>
          <RefreshButton :loading="loading" @refresh="load" />
        </div>
      </template>
      <EmptyState v-if="!data.rules.length" message="暂无自定义规则，全部流量走全局策略" />
      <div v-else class="overflow-x-auto">
        <table class="w-full text-[12.5px] whitespace-nowrap">
          <thead>
            <tr class="text-left text-muted border-b border-[var(--border)]">
              <th class="py-2 px-1.5">优先级</th><th class="py-2 px-1.5">匹配类型</th>
              <th class="py-2 px-1.5">匹配条件</th><th class="py-2 px-1.5">目标渠道组</th>
              <th class="py-2 px-1.5">启用</th><th class="py-2 px-1.5">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in data.rules" :key="r.id" class="border-b border-[var(--border)]/50 hover:bg-[var(--hover)]"
                :class="r.enabled ? '' : 'opacity-45'">
              <td class="px-1.5 py-2"><Badge size="sm">{{ r.priority }}</Badge></td>
              <td class="px-1.5">{{ { model: '按模型', group: '按分组' }[r.match_type] }}</td>
              <td class="px-1.5 font-mono text-[12px]">{{ r.match_value }}</td>
              <td class="px-1.5"><Badge size="sm" variant="accent">{{ r.target_group }}</Badge></td>
              <td class="px-1.5"><Switch :model-value="!!r.enabled" @update:model-value="toggle(r)" /></td>
              <td class="px-1.5">
                <div class="flex gap-0.5">
                  <Button size="icon" variant="ghost" @click="move(r, 'up')" title="上移"><ArrowUp :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" @click="move(r, 'down')" title="下移"><ArrowDown :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" @click="openEdit(r)" title="编辑"><Pencil :size="13.5" /></Button>
                  <Button size="icon" variant="ghost" class="text-red-500" @click="askDelete(r)" title="删除"><Trash2 :size="13.5" /></Button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>

    <Dialog v-model:open="ruleDlg.open" :title="ruleDlg.isEdit ? '编辑规则' : '新增规则'" width="480px">
      <div class="grid grid-cols-2 gap-3 text-[13px]">
        <div><label class="text-xs text-muted">匹配类型</label>
          <Select v-model="ruleDlg.form.match_type" class="mt-1"
                  :options="[{ value: 'model', label: '按模型名' }, { value: 'group', label: '按渠道分组' }]" /></div>
        <div><label class="text-xs text-muted">优先级</label>
          <Input v-model="ruleDlg.form.priority" type="number" class="mt-1" /></div>
        <div class="col-span-2"><label class="text-xs text-muted">匹配条件（逗号分隔多个，支持 * 通配）</label>
          <Input v-model="ruleDlg.form.match_value" class="mt-1" placeholder="如 gpt-4o,o3-mini 或 premium" /></div>
        <div class="col-span-2"><label class="text-xs text-muted">目标渠道组</label>
          <Input v-model="ruleDlg.form.target_group" class="mt-1" placeholder="premium" /></div>
        <label class="flex items-center gap-2">启用 <Switch v-model="ruleDlg.form.enabled" /></label>
      </div>
      <template #footer>
        <Button variant="outline" @click="ruleDlg.open = false">取消</Button>
        <Button @click="saveRule">保存</Button>
      </template>
    </Dialog>

    <ConfirmDialog v-model:open="confirmState.open" :title="confirmState.title" :message="confirmState.message" danger @confirm="confirmState.action && confirmState.action()" />
  </div>
</template>
