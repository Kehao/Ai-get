import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

const variablesFile = path.resolve(__dirname, 'src/styles/variables.less').replace(/\\/g, '/');

/**
 * 把设计令牌注入每个 less 文件，使组件样式直接使用变量而无需逐个 @import。
 * 用绝对路径而非别名，避免依赖 less 的别名解析行为。
 */
const injectVariables = (source: string, filename: string): string => {
  if (filename.replace(/\\/g, '/').endsWith('styles/variables.less')) {
    return source;
  }
  return `@import "${variablesFile}";\n${source}`;
};

/** 前端开发服务器配置：/api 统一代理到本地 Python 服务。 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  css: {
    preprocessorOptions: {
      less: {
        javascriptEnabled: true,
        additionalData: injectVariables,
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
