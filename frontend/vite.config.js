import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 构建产物直接输出到项目根 dist/（后端托管目录）
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500
  },
  server: {
    port: 5173,
    proxy: {
      '/admin': 'http://127.0.0.1:9010',
      '/v1': 'http://127.0.0.1:9010'
    }
  }
})
