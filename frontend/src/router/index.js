import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '仪表盘总览' } },
  { path: '/models', name: 'models', component: () => import('../views/ModelMonitor.vue'), meta: { title: '模型监控' } },
  { path: '/channels', name: 'channels', component: () => import('../views/Channels.vue'), meta: { title: '上游渠道管理' } },
  { path: '/keys', name: 'keys', component: () => import('../views/ApiKeys.vue'), meta: { title: '客户端密钥管理' } },
  { path: '/routing', name: 'routing', component: () => import('../views/Routing.vue'), meta: { title: '路由&分流策略' } },
  { path: '/logs', name: 'logs', component: () => import('../views/Logs.vue'), meta: { title: '调用日志' } },
  { path: '/errors', name: 'errors', component: () => import('../views/ErrorLogs.vue'), meta: { title: '错误日志' } },
  { path: '/settings', name: 'settings', component: () => import('../views/Settings.vue'), meta: { title: '系统设置' } }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.afterEach((to) => {
  document.title = `${to.meta.title || ''} · AI 聚合网关`
})

export default router
