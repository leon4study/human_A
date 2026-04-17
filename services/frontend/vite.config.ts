// frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: {
    // 여기에 global을 window로 매핑해줍니다.
    global: 'window',
  },
})