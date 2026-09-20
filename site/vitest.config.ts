import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.ts', 'tests/**/*.test.tsx'],
    // The suite is part of the PR CI budget (docs/process/working-agreements.md §1) and must
    // never reach the network: every fixture it reads lives under tests/fixtures/ or content/.
    testTimeout: 10_000,
  },
})
