const form = document.querySelector("#generate-form");
const editor = document.querySelector("#editor");
const preview = document.querySelector("#preview");
const toast = document.querySelector("#toast");
const count = document.querySelector("#count");
const generateButton = document.querySelector("#generate");
const imageResults = document.querySelector("#image-results");
const imageList = document.querySelector("#image-list");
const publishDrawer = document.querySelector("#publish-drawer");
const queueList = document.querySelector("#queue-list");
const queueEmpty = document.querySelector("#queue-empty");
const queueCount = document.querySelector("#queue-count");
let exportsReady = {};
let queueItems = [];

function words(text) {
  return (text.trim().match(/\b[\w'-]+\b/g) || []).length;
}

function updateCount() {
  count.textContent = `${words(editor.value)} words`;
}

function showToast(text, kind = "") {
  toast.textContent = text;
  toast.className = `toast ${kind}`.trim();
}

function switchView(name) {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${name}`);
  });
}

async function readJson(response) {
  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      if (!response.ok) {
        throw new Error(text);
      }
      throw new Error("The server returned an invalid response.");
    }
  }
  if (!response.ok) throw new Error(data.error || text || "Something went wrong.");
  return data;
}

function briefPayload() {
  return {
    topic: document.querySelector("#topic").value.trim(),
    brief: document.querySelector("#brief").value.trim(),
    keyword: document.querySelector("#keyword").value.trim(),
    subtitle: document.querySelector("#subtitle").value.trim(),
    format: document.querySelector("#format").value,
    image_count: Number(document.querySelector("#image-count").value),
    word_count: Number(document.querySelector("#word-count").value),
    audience: "everyone"
  };
}

function applyBrief(item) {
  document.querySelector("#topic").value = item.topic || "";
  document.querySelector("#brief").value = item.brief || "";
  document.querySelector("#keyword").value = item.keyword || "";
  document.querySelector("#subtitle").value = item.subtitle || "";
  document.querySelector("#word-count").value = String(item.word_count || 1200);
  document.querySelector("#image-count").value = String(item.image_count ?? 2);
  document.querySelector("#format").value = item.format || "newsletter";
  switchView("create");
  showToast("Brief loaded. Edit if needed, then generate.", "done");
}

function openQueueDraft(item) {
  editor.value = item.article_md || "";
  updateCount();
  renderImages(item.images || []);
  switchView("draft");
  showToast("Draft loaded from the Queue.", "done");
}

function applyGenerationResult(data, successMessage) {
  editor.value = data.article_md;
  exportsReady = data;
  updateCount();
  renderImages(data.images || []);
  const substack = data.substack_draft;
  let message = successMessage;
  if (substack?.edit_url) {
    message += ` Open in Substack: ${substack.edit_url}`;
  }
  showToast(message, "done");
  switchView("draft");
}

async function generateDraft() {
  const payload = briefPayload();
  if (!payload.topic) throw new Error("Add a topic first.");

  generateButton.disabled = true;

  const imageText = payload.image_count
    ? ` and ${payload.image_count} image${payload.image_count === 1 ? "" : "s"}`
    : "";
  showToast(`Generating your draft${imageText}…`, "working");

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const data = await readJson(response);
    const successMessage = `Draft ready${data.images?.length ? ` with ${data.images.length} images` : ""}. Review it in the Draft tab.`;
    applyGenerationResult(data, successMessage);
    return data;
  } finally {
    generateButton.disabled = false;
  }
}

function renderImages(images) {
  imageList.innerHTML = "";
  imageResults.hidden = !images.length;
  images.forEach((image, index) => {
    const link = document.createElement("a");
    link.className = "image-link";
    link.href = image.url;
    link.download = image.filename || `article-image-${index + 1}.png`;
    link.title = "Download image";
    const img = document.createElement("img");
    img.src = image.url;
    img.alt = image.alt || `Generated article image ${index + 1}`;
    link.appendChild(img);
    imageList.appendChild(link);
  });
}

function updateQueueCount() {
  const pending = queueItems.filter((item) => item.status === "pending").length;
  queueCount.textContent = String(pending);
}

function queueMeta(item) {
  const parts = [
    item.format || "newsletter",
    `${item.word_count || 1200} words`,
    `${item.image_count ?? 0} images`
  ];
  if (item.substack_edit_url) parts.push("in Substack");
  if (item.error) parts.push(item.error);
  return parts.join(" · ");
}

function renderQueue() {
  queueList.innerHTML = "";
  queueEmpty.hidden = queueItems.length > 0;
  updateQueueCount();

  queueItems.forEach((item) => {
    const li = document.createElement("li");
    li.className = "queue-item";
    li.innerHTML = `
      <div class="queue-item-main">
        <p class="queue-item-title">
          <span class="status-badge ${item.status || "pending"}">${item.status || "pending"}</span>
          ${item.topic}
        </p>
        <p class="queue-item-meta">${queueMeta(item)}</p>
      </div>
      <div class="queue-item-actions"></div>
    `;

    const actions = li.querySelector(".queue-item-actions");

    const runButton = document.createElement("button");
    runButton.type = "button";
    runButton.className = "btn btn-ghost btn-sm";
    if (item.article_md) {
      runButton.textContent = "Open draft";
      runButton.addEventListener("click", () => openQueueDraft(item));
    } else {
      runButton.textContent = "Run";
      runButton.addEventListener("click", () => runQueueItem(item.id));
    }

    const loadButton = document.createElement("button");
    loadButton.type = "button";
    loadButton.className = "btn btn-ghost btn-sm";
    loadButton.textContent = "Edit brief";
    loadButton.addEventListener("click", () => applyBrief(item));

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "btn btn-ghost btn-sm";
    deleteButton.textContent = "Remove";
    deleteButton.style.color = "var(--danger)";
    deleteButton.addEventListener("click", () => deleteQueueItem(item.id));

    actions.append(runButton, loadButton, deleteButton);
    queueList.appendChild(li);
  });
}

async function loadQueue() {
  const response = await fetch("/api/queue");
  const data = await readJson(response);
  queueItems = data.items || [];
  renderQueue();
}

async function addCurrentBriefToQueue() {
  const payload = briefPayload();
  if (!payload.topic) throw new Error("Add a topic first.");
  showToast("Adding to queue…", "working");
  const response = await fetch("/api/queue", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
  await readJson(response);
  await loadQueue();
  showToast("Added to queue. Run it from the Queue tab.", "done");
}

async function deleteQueueItem(itemId) {
  const response = await fetch(`/api/queue/${itemId}`, {method: "DELETE"});
  await readJson(response);
  await loadQueue();
}

async function runQueueItem(itemId) {
  document.querySelector("#queue-run-next").disabled = true;
  showToast("Running queued topic…", "working");
  try {
    const response = await fetch(`/api/queue/${itemId}/run`, {
      method: "POST",
      headers: {"Content-Type": "application/json"}
    });
    const data = await readJson(response);
    applyGenerationResult(data, "Queued topic finished.");
    await loadQueue();
  } catch (error) {
    showToast(error.message, "error");
    await loadQueue();
  } finally {
    document.querySelector("#queue-run-next").disabled = false;
  }
}

async function runNextQueueItem() {
  document.querySelector("#queue-run-next").disabled = true;
  showToast("Running next topic…", "working");
  try {
    const response = await fetch("/api/queue/run-next", {
      method: "POST",
      headers: {"Content-Type": "application/json"}
    });
    const data = await readJson(response);
    applyGenerationResult(data, "Next topic finished.");
    await loadQueue();
  } catch (error) {
    showToast(error.message, "error");
    await loadQueue();
  } finally {
    document.querySelector("#queue-run-next").disabled = false;
  }
}

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    switchView(btn.dataset.view);
    if (btn.dataset.view === "agent") loadAgentTab().catch((error) => showToast(error.message, "error"));
  });
});

document.querySelectorAll(".segmented-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".segmented-btn").forEach((item) => item.classList.remove("active"));
    btn.classList.add("active");
    const showPreview = btn.dataset.editorView === "preview";
    editor.hidden = showPreview;
    preview.hidden = !showPreview;
    if (showPreview) preview.innerHTML = marked.parse(editor.value);
  });
});

editor.addEventListener("input", updateCount);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await generateDraft();
  } catch (error) {
    showToast(error.message, "error");
  }
});

async function prepareCopies() {
  if (!editor.value.trim()) {
    showToast("Write or generate a draft first.", "error");
    return;
  }
  showToast("Preparing copy formats…", "working");
  try {
    const response = await fetch("/api/export", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({article_md: editor.value})
    });
    exportsReady = await readJson(response);
    publishDrawer.hidden = false;
    document.querySelectorAll("#publish-drawer button").forEach((button) => button.disabled = false);
    showToast("Copy buttons are ready below.", "done");
  } catch (error) {
    showToast(error.message, "error");
  }
}

document.querySelectorAll(".prepare-copy-btn").forEach((button) => {
  button.addEventListener("click", prepareCopies);
});

async function copyValue(key, button) {
  await navigator.clipboard.writeText(exportsReady[key] || "");
  const original = button.textContent;
  button.textContent = "Copied";
  setTimeout(() => button.textContent = original, 1400);
}

document.querySelector("#copy-gutenberg").addEventListener("click", (event) => copyValue("gutenberg", event.currentTarget));
document.querySelector("#copy-substack").addEventListener("click", (event) => copyValue("substack", event.currentTarget));
document.querySelector("#copy-markdown").addEventListener("click", (event) => copyValue("article_md", event.currentTarget));

document.querySelector("#queue-add").addEventListener("click", async () => {
  try {
    await addCurrentBriefToQueue();
  } catch (error) {
    showToast(error.message, "error");
  }
});

document.querySelector("#queue-run-next").addEventListener("click", runNextQueueItem);

function toTimeInputValue(hhmm) {
  const [hour, minute] = (hhmm || "06:00").split(":");
  return `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
}

function fromTimeInputValue(value) {
  const [hour, minute] = (value || "06:00").split(":");
  return `${Number(hour)}:${minute.padStart(2, "0")}`;
}

function fillAgentConfigForm(config) {
  document.querySelector("#agent-enabled").checked = Boolean(config.enabled);
  document.querySelector("#agent-timezone").value = config.schedule?.timezone || "America/New_York";
  document.querySelector("#agent-research-time").value = toTimeInputValue(config.schedule?.research_time);
  document.querySelector("#agent-draft-time").value = toTimeInputValue(config.schedule?.draft_time);
  document.querySelector("#agent-articles-per-day").value = String(config.schedule?.articles_per_day ?? 1);
  document.querySelector("#agent-research-areas").value = (config.research_areas || []).join("\n");
  document.querySelector("#agent-research-model").value = config.research?.model || "sonar-pro";
  document.querySelector("#agent-topics-per-area").value = String(config.research?.topics_per_area ?? 3);
  document.querySelector("#agent-lookback-days").value = String(config.research?.lookback_days ?? 7);
  document.querySelector("#agent-auto-pick").checked = Boolean(config.selection?.auto_pick);
  document.querySelector("#agent-min-trend-score").value = String(config.selection?.min_trend_score ?? 6);
  document.querySelector("#agent-max-pool-age").value = String(config.selection?.max_pool_age_days ?? 14);
  document.querySelector("#agent-format").value = config.article_defaults?.format || "newsletter";
  document.querySelector("#agent-word-count").value = String(config.article_defaults?.word_count ?? 1200);
  document.querySelector("#agent-image-count").value = String(config.article_defaults?.image_count ?? 2);
  document.querySelector("#agent-audience").value = config.article_defaults?.audience || "everyone";
}

function collectAgentConfigForm() {
  return {
    enabled: document.querySelector("#agent-enabled").checked,
    research_areas: document.querySelector("#agent-research-areas").value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean),
    schedule: {
      timezone: document.querySelector("#agent-timezone").value.trim(),
      research_time: fromTimeInputValue(document.querySelector("#agent-research-time").value),
      draft_time: fromTimeInputValue(document.querySelector("#agent-draft-time").value),
      articles_per_day: Number(document.querySelector("#agent-articles-per-day").value)
    },
    research: {
      model: document.querySelector("#agent-research-model").value,
      topics_per_area: Number(document.querySelector("#agent-topics-per-area").value),
      lookback_days: Number(document.querySelector("#agent-lookback-days").value)
    },
    selection: {
      auto_pick: document.querySelector("#agent-auto-pick").checked,
      min_trend_score: Number(document.querySelector("#agent-min-trend-score").value),
      max_pool_age_days: Number(document.querySelector("#agent-max-pool-age").value)
    },
    article_defaults: {
      format: document.querySelector("#agent-format").value,
      word_count: Number(document.querySelector("#agent-word-count").value),
      image_count: Number(document.querySelector("#agent-image-count").value),
      audience: document.querySelector("#agent-audience").value,
      auto_substack_draft: false
    }
  };
}

async function loadAgentConfig() {
  const response = await fetch("/api/agent/config");
  const data = await readJson(response);
  fillAgentConfigForm(data);
}

async function loadAgentStatus() {
  const response = await fetch("/api/agent/status");
  const data = await readJson(response);
  const box = document.querySelector("#agent-status");
  const stats = [
    ["Pool", data.pool_available],
    ["Queue", data.queue_pending],
    ["Left today", data.drafts_remaining_today],
    ["Research due", data.research_due ? "Yes" : "No"],
    ["Draft due", data.draft_due ? "Yes" : "No"],
    ["Enabled", data.enabled ? "Yes" : "No"]
  ];
  box.innerHTML = stats.map(([label, value]) => `
    <div class="agent-stat"><strong>${value}</strong><span>${label}</span></div>
  `).join("");
}

async function loadAgentTab() {
  await Promise.all([loadAgentStatus(), loadAgentConfig()]);
}

document.querySelector("#agent-config-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#agent-save");
  button.disabled = true;
  showToast("Saving agent settings…", "working");
  try {
    const response = await fetch("/api/agent/config", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(collectAgentConfigForm())
    });
    const data = await readJson(response);
    fillAgentConfigForm(data);
    await loadAgentStatus();
    showToast("Agent settings saved.", "done");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#agent-run").addEventListener("click", async () => {
  const button = document.querySelector("#agent-run");
  button.disabled = true;
  showToast("Running agent (research → pick → draft)…", "working");
  try {
    const response = await fetch("/api/agent/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({force: true})
    });
    const data = await readJson(response);
    await loadAgentStatus();
    await loadQueue();
    showToast("Agent run finished. Check the Queue for generated drafts.", "done");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
  }
});

loadQueue().catch((error) => showToast(error.message, "error"));
