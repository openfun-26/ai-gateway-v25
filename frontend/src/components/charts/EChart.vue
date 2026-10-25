<script setup>
// ECharts 通用封装：监听全局主题与强调色变化自动重绘
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '280px' }
})

const el = ref(null)
let chart = null
let ro = null

function isDark() {
  return document.documentElement.classList.contains('dark')
}

function themedOption() {
  // 先把 option 中引用的 CSS 变量（如 var(--card)）解析为实际色值，
  // ECharts/zrender 无法识别 CSS 变量，不解析会导致边框/背景异常
  const rootStyle = getComputedStyle(document.documentElement)
  let json = JSON.stringify(props.option)
  json = json.replace(/var\(--([a-zA-Z0-9-]+)\)/g, (_, name) => {
    const v = rootStyle.getPropertyValue(`--${name}`).trim()
    return v || 'transparent'
  })
  const opt = JSON.parse(json)
  const dark = isDark()
  const fg = dark ? '#d4d4d8' : '#3f3f46'
  const border = dark ? '#26282d' : '#e6e6e9'
  const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#14b8a6'
  opt.textStyle = { color: fg, fontFamily: 'Public Sans, sans-serif' }
  if (opt.legend) opt.legend = { ...opt.legend, textStyle: { color: fg }, inactiveColor: dark ? '#52525b' : '#a1a1aa' }
  if (opt.tooltip) opt.tooltip = { ...opt.tooltip, backgroundColor: dark ? '#1d1f23' : '#ffffff',
                                   borderColor: border, textStyle: { color: fg, fontSize: 12 } }
  // 网格线
  const gridColor = dark ? '#232529' : '#ececef'
  if (Array.isArray(opt.xAxis)) {
    opt.xAxis = opt.xAxis.map(a => ({ ...a, axisLine: { lineStyle: { color: border } }, axisLabel: { color: fg, fontSize: 11 },
                                      splitLine: { lineStyle: { color: gridColor } } }))
  } else if (opt.xAxis) {
    opt.xAxis = { ...opt.xAxis, axisLine: { lineStyle: { color: border } }, axisLabel: { color: fg, fontSize: 11 },
                  splitLine: { lineStyle: { color: gridColor } } }
  }
  if (Array.isArray(opt.yAxis)) {
    opt.yAxis = opt.yAxis.map(a => ({ ...a, axisLine: { show: false }, axisLabel: { color: fg, fontSize: 11 },
                                      splitLine: { lineStyle: { color: gridColor } } }))
  } else if (opt.yAxis) {
    opt.yAxis = { ...opt.yAxis, axisLine: { show: false }, axisLabel: { color: fg, fontSize: 11 },
                  splitLine: { lineStyle: { color: gridColor } } }
  }
  // 饼图/折线默认色带以强调色开头
  const palette = [accent, '#3b82f6', '#8b5cf6', '#f59e0b', '#f43f5e', '#10b981', '#06b6d4', '#a855f7', '#84cc16', '#f97316']
  if (opt.color) opt.color = [accent, ...opt.color.slice(1)]
  else opt.color = palette
  return opt
}

function render() {
  if (!el.value) return
  if (!chart) chart = echarts.init(el.value)
  chart.setOption(themedOption(), true)
}

onMounted(() => {
  render()
  ro = new ResizeObserver(() => chart && chart.resize())
  ro.observe(el.value)
  window.addEventListener('gw-theme-changed', render)
  window.addEventListener('gw-accent-changed', render)
})

onBeforeUnmount(() => {
  window.removeEventListener('gw-theme-changed', render)
  window.removeEventListener('gw-accent-changed', render)
  if (ro) ro.disconnect()
  if (chart) { chart.dispose(); chart = null }
})

watch(() => props.option, render, { deep: true })
</script>

<template>
  <div ref="el" :style="{ height, width: '100%' }" />
</template>
