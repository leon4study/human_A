// frontend/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Vite dev server 설정
export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    // 일부 라이브러리에서 global 참조할 때 window로 매핑
    global: "window",
  },
  server: {
    proxy: {
      // 프론트에서 /predict로 요청하면
      // Vite가 inference-api(8000)로 전달
      "/predict": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});