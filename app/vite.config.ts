import { defineConfig } from "vitest/config";

export default defineConfig({
  // The bundle is served under /ciao-sun/ (spec #27, "Client app").
  base: "/ciao-sun/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "test/**/*.test.ts"],
  },
});
