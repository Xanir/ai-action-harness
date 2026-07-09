<script setup lang="ts">
import { ref, computed, onMounted } from "vue";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface McpTool {
  name: string;
  description: string;
  args_schema: {
    type: string;
    properties: Record<string, { type: string; description?: string; title?: string }>;
    required: string[];
  } | null;
}

interface McpServer {
  name: string;
  prompt: string | null;
  transport: string;
  url: string;
  tools: McpTool[];
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const servers = ref<McpServer[]>([]);
const selectedServer = ref("");
const selectedTool = ref("");
const promptText = ref("");
const argValues = ref<Record<string, string>>({});
const loading = ref(false);
const result = ref<{ success: boolean; result?: unknown; error?: string } | null>(null);
const error = ref<string | null>(null);

// ---------------------------------------------------------------------------
// Derived
// ---------------------------------------------------------------------------

const currentServer = computed(() =>
  servers.value.find((s) => s.name === selectedServer.value),
);

const currentTool = computed(() =>
  currentServer.value?.tools.find((t) => t.name === selectedTool.value),
);

const toolsForServer = computed(() => currentServer.value?.tools ?? []);

/** Whether the selected tool has user-facing parameters. */
const hasParameters = computed(() => {
  const props = currentTool.value?.args_schema?.properties;
  return props != null && Object.keys(props).length > 0;
});

/**
 * Ordered list of parameter definitions for the selected tool.
 * Falls back to a single "prompt" field when the schema is unavailable
 * (legacy server / stdio transport).
 */
const parameterFields = computed(() => {
  const schema = currentTool.value?.args_schema;
  if (!schema || !schema.properties || Object.keys(schema.properties).length === 0) {
    // No schema — treat the text area as a raw-JSON / legacy "prompt" field.
    return [{ name: "prompt", type: "string", required: true, title: "Arguments (JSON)" }];
  }
  return Object.entries(schema.properties).map(([name, info]) => ({
    name,
    type: info.type ?? "string",
    required: (schema.required ?? []).includes(name),
    title: info.title ?? name,
  }));
});

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function fetchServers() {
  try {
    const res = await fetch("/api/mcp/servers");
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    servers.value = await res.json();
  } catch (e) {
    error.value = `Failed to load MCP servers: ${e}`;
  }
}

async function sendPrompt() {
  if (!selectedServer.value || !selectedTool.value) return;

  loading.value = true;
  result.value = null;
  error.value = null;

  try {
    // Build arguments from parameter fields or legacy prompt text.
    let args: Record<string, string>;
    if (hasParameters.value) {
      args = { ...argValues.value };
    } else {
      // Legacy fallback: parse the text area as JSON, or wrap as "prompt".
      let parsed: unknown;
      try {
        parsed = JSON.parse(promptText.value);
      } catch {
        parsed = { prompt: promptText.value };
      }
      args = parsed as Record<string, string>;
    }

    const res = await fetch("/api/mcp/call", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        server_name: selectedServer.value,
        tool_name: selectedTool.value,
        arguments: args,
      }),
    });

    const data = await res.json();
    if (!res.ok) {
      error.value = data.detail ?? `HTTP ${res.status}`;
    } else {
      result.value = data;
    }
  } catch (e) {
    error.value = `Request failed: ${e}`;
  } finally {
    loading.value = false;
  }
}

// Clear dependent dropdowns when server changes
function onServerChange() {
  selectedTool.value = "";
  argValues.value = {};
  promptText.value = "";
  result.value = null;
  error.value = null;
}

// Reset arg values when tool changes
function onToolChange() {
  argValues.value = {};
  promptText.value = "";
  result.value = null;
  error.value = null;
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(fetchServers);
</script>

<template>
  <section class="panel">
    <div class="panel-header">
      <h2>MCP Tool Prompt</h2>
      <span class="badge badge-active">Active</span>
    </div>
    <p class="panel-desc">
      Select a configured MCP server and tool, then send a prompt directly.
    </p>

    <!-- Error banner -->
    <div v-if="error" class="banner banner-error">{{ error }}</div>

    <!-- Server dropdown -->
    <div class="form-group">
      <label for="mcp-server">MCP Server</label>
      <select
        id="mcp-server"
        v-model="selectedServer"
        class="input"
        @change="onServerChange"
      >
        <option value="" disabled>-- Select a server --</option>
        <option
          v-for="server in servers"
          :key="server.name"
          :value="server.name"
        >
          {{ server.name }}
        </option>
      </select>
      <p v-if="currentServer?.prompt" class="hint">
        {{ currentServer.prompt }}
      </p>
    </div>

    <!-- Tool dropdown -->
    <div class="form-group">
      <label for="mcp-tool">MCP Tool</label>
      <select
        id="mcp-tool"
        v-model="selectedTool"
        class="input"
        :disabled="!selectedServer"
        @change="onToolChange"
      >
        <option value="" disabled>-- Select a tool --</option>
        <option
          v-for="tool in toolsForServer"
          :key="tool.name"
          :value="tool.name"
        >
          {{ tool.name }}
        </option>
      </select>
      <p v-if="currentTool?.description" class="hint">
        {{ currentTool.description }}
      </p>
    </div>

    <!-- Dynamic parameter fields (when args_schema is available) -->
    <template v-if="hasParameters">
      <div
        v-for="field in parameterFields"
        :key="field.name"
        class="form-group"
      >
        <label :for="'mcp-arg-' + field.name">
          {{ field.title }}
          <span v-if="field.required" class="required">*</span>
        </label>
        <textarea
          v-if="field.name === 'query' || field.name === 'prompt'"
          :id="'mcp-arg-' + field.name"
          v-model="argValues[field.name]"
          class="input"
          rows="3"
          :placeholder="'Enter ' + field.title.toLowerCase() + '...'"
        ></textarea>
        <input
          v-else
          :id="'mcp-arg-' + field.name"
          v-model="argValues[field.name]"
          class="input"
          type="text"
          :placeholder="'Enter ' + field.title.toLowerCase() + '...'"
        />
      </div>
    </template>

    <!-- Legacy prompt field (when no args_schema is available) -->
    <div v-else class="form-group">
      <label for="mcp-prompt">Arguments</label>
      <textarea
        id="mcp-prompt"
        v-model="promptText"
        class="input"
        rows="4"
        placeholder='JSON arguments, e.g. {"project_name": "my-project", "query": "What does the project do?"}'
        :disabled="!selectedTool"
      ></textarea>
      <p class="hint">
        This tool's parameter schema is unavailable. Enter arguments as a JSON
        object.
      </p>
    </div>

    <button
      class="btn btn-primary"
      :disabled="!selectedTool || (!hasParameters && !promptText.trim()) || loading"
      @click="sendPrompt"
    >
      <span v-if="loading" class="spinner"></span>
      {{ loading ? "Sending..." : "Send to MCP Tool" }}
    </button>

    <!-- Result -->
    <div v-if="result" class="result" :class="{ 'result-error': !result.success }">
      <div class="result-header">
        {{ result.success ? "Response" : "Error" }}
      </div>
      <pre class="result-body">{{
        result.success
          ? JSON.stringify(result.result, null, 2)
          : result.error
      }}</pre>
    </div>
  </section>
</template>

<style scoped>
.panel {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 1.5rem;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.panel-header h2 {
  font-size: 1.15rem;
  font-weight: 600;
  color: #f0f6fc;
}

.badge {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.15rem 0.6rem;
  border-radius: 999px;
  border: 1px solid transparent;
}

.badge-active {
  background: #1b3826;
  color: #3fb950;
  border-color: #2ea04344;
}

.panel-desc {
  font-size: 0.85rem;
  color: #8b949e;
  margin-bottom: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-bottom: 1rem;
}

.form-group label {
  font-size: 0.85rem;
  font-weight: 500;
  color: #c9d1d9;
}

.input {
  width: 100%;
  padding: 0.6rem 0.75rem;
  font-size: 0.9rem;
  font-family: inherit;
  color: #c9d1d9;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  outline: none;
  transition: border-color 0.15s;
}

.input:focus {
  border-color: #58a6ff;
}

.input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

textarea.input {
  resize: vertical;
}

select.input {
  cursor: pointer;
}

.hint {
  font-size: 0.8rem;
  color: #6e7681;
  line-height: 1.4;
  white-space: pre-wrap;
}

.required {
  color: #f85149;
  margin-left: 2px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.55rem 1.2rem;
  font-size: 0.875rem;
  font-weight: 600;
  font-family: inherit;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-primary {
  background: #238636;
  color: #fff;
  border-color: #2ea04344;
}

.btn-primary:hover:not(:disabled) {
  background: #2ea043;
}

/* Spinner */
.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid #ffffff66;
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Banner */
.banner {
  padding: 0.6rem 0.8rem;
  border-radius: 6px;
  font-size: 0.85rem;
  margin-bottom: 1rem;
}

.banner-error {
  background: #2d1518;
  color: #f85149;
  border: 1px solid #f8514944;
}

/* Result */
.result {
  margin-top: 1.25rem;
  border: 1px solid #30363d;
  border-radius: 6px;
  overflow: hidden;
}

.result-error {
  border-color: #f8514944;
}

.result-header {
  padding: 0.4rem 0.75rem;
  font-size: 0.8rem;
  font-weight: 600;
  background: #1c2128;
  color: #3fb950;
  border-bottom: 1px solid #30363d;
}

.result-error .result-header {
  color: #f85149;
}

.result-body {
  padding: 0.75rem;
  font-size: 0.8rem;
  font-family: "SF Mono", "Fira Code", "Cascadia Code", monospace;
  color: #c9d1d9;
  background: #0d1117;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 360px;
  overflow-y: auto;
}
</style>
