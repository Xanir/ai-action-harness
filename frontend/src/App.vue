<script setup lang="ts">
import HarnessPrompt from "./components/HarnessPrompt.vue";
import McpPrompt from "./components/McpPrompt.vue";
</script>

<template>
  <div class="app">
    <header class="app-header">
      <h1>AI Action Harness</h1>
      <p class="subtitle">Manual prompt &amp; MCP tool testing interface</p>
    </header>

    <main class="app-main">
      <HarnessPrompt />
      <McpPrompt />
    </main>
  </div>
</template>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  background: #0f1117;
  color: #e1e4e8;
  min-height: 100vh;
}

.app {
  max-width: 960px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

.app-header {
  text-align: center;
  margin-bottom: 2.5rem;
}

.app-header h1 {
  font-size: 1.75rem;
  font-weight: 700;
  color: #f0f6fc;
}

.app-header .subtitle {
  margin-top: 0.35rem;
  font-size: 0.95rem;
  color: #8b949e;
}

.app-main {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}
</style>
