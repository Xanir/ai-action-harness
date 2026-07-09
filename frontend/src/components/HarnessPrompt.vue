<script setup lang="ts">
// Placeholder — AI Harness orchestration not yet implemented.
</script>

<template>
  <section class="panel panel-disabled">
    <div class="panel-header">
      <h2>AI Harness Prompt</h2>
      <span class="badge">Coming Soon</span>
    </div>
    <p class="panel-desc">
      Send a full prompt through the LangGraph orchestration layer with
      model-to-action routing.
    </p>

    <div class="form-group">
      <label for="harness-prompt">Prompt</label>
      <textarea
        id="harness-prompt"
        class="input"
        rows="4"
        placeholder="Describe what you want the harness to do..."
        disabled
      ></textarea>
    </div>

    <button class="btn btn-primary" disabled>Send to Harness</button>
  </section>
</template>

<style scoped>
.panel {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 1.5rem;
}

.panel-disabled {
  opacity: 0.55;
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
  background: #1f2a37;
  color: #58a6ff;
  border: 1px solid #1f6feb44;
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

.input,
select.input {
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
</style>
