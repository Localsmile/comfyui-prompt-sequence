import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const IMAGE_SEQUENCE_CLASS = "ComfyUIPromptImageSequence";
const IMAGE_MASK_SEQUENCE_CLASS = "ComfyUIPromptImageMaskSequence";
const COMBO_CLASS = "ComfyUIPromptSequenceCombo";
const JOIN_CLASS = "ComfyUIPromptSequenceJoin";
const MAX_JOIN_INPUTS = 32;
const ALL_TOPICS = "__all_topics__";
const STYLE_ID = "prompt-sequence-style";
const WIDGET_TOOLTIPS = {
  ComfyUIPromptSequenceText: {
    prompts: "Each non-empty line becomes one prompt item.",
    mode: "sequential: output top to bottom. random: shuffle before output.",
    seed: "For random mode: -1 makes a new order each queue; a fixed value repeats the same order.",
  },
  ComfyUIPromptSequenceCombo: {
    prompts: "Used only when source is not connected. Hidden and ignored while source is connected.",
    mode: "sequential: keep source order. random: shuffle before max_items is applied.",
    max_items: "0 outputs all available prompts. A positive value outputs up to that many prompts.",
    seed: "Used only in random mode. -1 makes a new order each queue; a fixed value repeats the same order.",
  },
  ComfyUIPromptSequenceJoin: {
    input_count: "Number of visible text inputs. Click update inputs after changing it.",
    separator: "Text inserted between parts. Use \\n or /n for a newline, including ,\\n or ,/n.",
    skip_empty: "When enabled, blank missing parts are removed before joining, including their separator.",
    length_policy: "longest: emit up to the longest input. shortest: stop at the shortest connected input.",
    missing_policy: "blank: missing values become empty text. repeat_last: reuse the shorter input's final value.",
    max_items: "0 keeps all joined prompts. A positive value limits the final joined output count.",
    "update inputs": "Applies input_count by adding or removing visible text input slots.",
  },
  ComfyUIPromptTagFormatter: {
    text: "Normalizes line breaks and commas into one comma-space-separated tag line.",
  },
  ComfyUIPromptImageSequence: {
    selection_json: "Hidden picker state. Use the thumbnail grid instead of editing this manually.",
    mode: "sequential: use checked cards in order. random: shuffle checked cards before output.",
    seed: "For random mode: -1 makes a new order each queue; a fixed value repeats the same order.",
  },
  ComfyUIPromptImageMaskSequence: {
    selection_json: "Hidden picker state. Use the thumbnail grid instead of editing this manually.",
    mode: "sequential: use checked cards in order. random: shuffle checked cards before output.",
    seed: "For random mode: -1 makes a new order each queue; a fixed value repeats the same order.",
  },
};

function injectStyle() {
  if (document.getElementById(STYLE_ID)) {
    return;
  }

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .ps-picker {
      box-sizing: border-box;
      width: 100%;
      min-width: 320px;
      padding: 8px;
      color: #ddd;
      font: 12px/1.4 Arial, sans-serif;
      background: #222;
      border: 1px solid #444;
      border-radius: 6px;
    }
    .ps-toolbar {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto auto;
      gap: 6px;
      align-items: center;
      margin-bottom: 8px;
    }
    .ps-picker select,
    .ps-picker input,
    .ps-picker textarea,
    .ps-picker button {
      box-sizing: border-box;
      width: 100%;
      min-height: 26px;
      color: #eee;
      background: #171717;
      border: 1px solid #555;
      border-radius: 4px;
      font: inherit;
    }
    .ps-picker textarea {
      min-height: 64px;
      resize: vertical;
    }
    .ps-picker button {
      width: auto;
      padding: 0 8px;
      cursor: pointer;
      background: #303030;
    }
    .ps-picker button:disabled {
      opacity: 0.55;
      cursor: wait;
    }
    .ps-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
      gap: 6px;
      padding-right: 2px;
    }
    .ps-card {
      position: relative;
      display: grid;
      grid-template-rows: auto 22px;
      gap: 4px;
      min-width: 0;
      padding: 5px;
      background: #191919;
      border: 1px solid #3d3d3d;
      border-radius: 6px;
      cursor: pointer;
      user-select: none;
    }
    .ps-card.ps-selected {
      border-color: #8fb7ff;
      box-shadow: inset 0 0 0 1px rgba(143, 183, 255, 0.45);
    }
    .ps-media {
      position: relative;
      width: 100%;
      aspect-ratio: 1 / 1;
      overflow: hidden;
      background: #101010;
      border-radius: 4px;
    }
    .ps-thumb {
      display: block;
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .ps-picker.ps-contain .ps-thumb {
      object-fit: contain;
    }
    .ps-placeholder {
      display: grid;
      place-items: center;
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      color: #888;
    }
    .ps-check {
      position: absolute;
      top: 8px;
      left: 8px;
      z-index: 30;
      width: auto !important;
      min-height: 0 !important;
    }
    .ps-name {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #f2f2f2;
      font-weight: 600;
      line-height: 22px;
    }
    .ps-detail {
      display: none;
      position: absolute;
      inset: 5px;
      z-index: 20;
      overflow: auto;
      padding: 8px;
      color: #eee;
      white-space: pre-wrap;
      background: rgba(24, 24, 24, 0.98);
      border: 1px solid #666;
      border-radius: 6px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
    }
    .ps-card:hover .ps-detail,
    .ps-card:focus-within .ps-detail {
      display: block;
    }
    .ps-empty {
      grid-column: 1 / -1;
      color: #999;
      padding: 10px 2px;
    }
    .ps-status {
      min-height: 18px;
      color: #aaa;
      margin-top: 6px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .ps-editor {
      display: none;
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid #444;
    }
    .ps-editor.ps-open {
      display: block;
    }
    .ps-editor-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin-bottom: 6px;
    }
    .ps-file-field {
      display: grid;
      grid-template-rows: auto auto;
      gap: 3px;
      min-width: 0;
      color: #bbb;
    }
    .ps-file-field span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 11px;
    }
    .ps-editor-actions {
      display: flex;
      gap: 6px;
      justify-content: flex-end;
      margin-top: 6px;
    }
    .ps-menu {
      position: fixed;
      z-index: 999999;
      display: none;
      min-width: 128px;
      padding: 4px;
      background: #202020;
      border: 1px solid #555;
      border-radius: 6px;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
    }
    .ps-menu button {
      display: block;
      width: 100%;
      min-height: 28px;
      padding: 0 8px;
      color: #eee;
      text-align: left;
      background: transparent;
      border: 0;
      border-radius: 4px;
      cursor: pointer;
      font: 12px/1.4 Arial, sans-serif;
    }
    .ps-menu button:hover {
      background: #383838;
    }
    @media (max-width: 520px) {
      .ps-grid {
        grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
      }
      .ps-toolbar {
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      }
    }
  `;
  document.head.appendChild(style);
}

function stopCanvasEvents(root) {
  [
    "pointerdown",
    "pointerup",
    "mousedown",
    "mouseup",
    "click",
    "dblclick",
    "contextmenu",
    "wheel",
    "keydown",
    "keyup",
    "input",
    "change",
  ].forEach((eventName) => {
    root.addEventListener(eventName, (event) => event.stopPropagation());
  });
}

function readSelection(widget) {
  try {
    const parsed = JSON.parse(widget?.value || "{}");
    return {
      project: parsed.project || "",
      topic: parsed.topic || "",
      selected: Array.isArray(parsed.selected) ? parsed.selected : [],
    };
  } catch {
    return { project: "", topic: "", selected: [] };
  }
}

function writeSelection(node, widget, state) {
  widget.value = JSON.stringify({
    project: state.project || "",
    topic: state.topic || "",
    selected: Array.from(new Set(state.selected || [])),
  });
  if (typeof node.setDirtyCanvas === "function") {
    node.setDirtyCanvas(true, true);
  } else {
    app.graph?.setDirtyCanvas(true, true);
  }
}

function findProject(library, projectId) {
  return library.projects.find((project) => project.id === projectId) || null;
}

function findTopic(project, topicId) {
  return project?.topics?.find((topic) => topic.id === topicId) || null;
}

function projectItems(project) {
  return (project?.topics || []).flatMap((topic) => topic.items || []);
}

function topicForItem(project, item) {
  const topicId = String(item?.id || "").split("/")[1] || "";
  return findTopic(project, topicId);
}

function currentItems(library, state) {
  const project = findProject(library, state.project);
  if (state.topic === ALL_TOPICS) {
    return projectItems(project);
  }
  const topic = findTopic(project, state.topic);
  return topic?.items || [];
}

function hideRawSelectionWidget(node) {
  const widget = node.widgets?.find((item) => item.name === "selection_json");
  if (!widget) {
    return null;
  }
  widget.type = "hidden";
  widget.computeSize = () => [0, -4];
  return widget;
}

function option(value, text, selected) {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = text;
  item.selected = selected;
  return item;
}

function makeInput(placeholder) {
  const input = document.createElement("input");
  input.placeholder = placeholder;
  return input;
}

function makeFileField(labelText) {
  const field = document.createElement("label");
  field.className = "ps-file-field";
  const label = document.createElement("span");
  label.textContent = labelText;
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  field.append(label, input);
  return { field, input };
}

function makeButton(text) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = text;
  return button;
}

function normalizeState(library, state) {
  const projects = library.projects || [];
  if (!projects.length) {
    return { project: "", topic: "", selected: [] };
  }
  const project = findProject(library, state.project) || projects[0];
  const topics = project.topics || [];
  if (!topics.length) {
    return { project: project.id, topic: "", selected: [] };
  }
  const topic = state.topic === ALL_TOPICS ? null : findTopic(project, state.topic);
  const nextTopic = state.topic === ALL_TOPICS || !topic ? ALL_TOPICS : topic.id;
  const items = nextTopic === ALL_TOPICS ? projectItems(project) : topic.items || [];
  const validIds = new Set(items.map((item) => item.id));
  return {
    project: project.id,
    topic: nextTopic,
    selected: (state.selected || []).filter((id) => validIds.has(id)),
  };
}

async function fetchLibrary() {
  const response = await api.fetchApi("/prompt_sequence/assets");
  if (!response.ok) {
    throw new Error(`Library request failed: ${response.status}`);
  }
  return response.json();
}

async function savePromptAsset(form) {
  const response = await api.fetchApi("/prompt_sequence/assets", {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Save failed: ${response.status}`);
  }
  return response.json();
}

async function deletePromptAsset(itemId) {
  const params = new URLSearchParams({ id: itemId });
  const response = await api.fetchApi(`/prompt_sequence/assets?${params}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Delete failed: ${response.status}`);
  }
  return response.json();
}

function clampJoinInputCount(value) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return 2;
  }
  return Math.max(1, Math.min(MAX_JOIN_INPUTS, parsed));
}

function getWidget(node, name) {
  return node.widgets?.find((widget) => widget.name === name) || null;
}

function setWidgetTooltip(widget, text) {
  if (!widget || !text) {
    return;
  }
  widget.tooltip = text;
  widget.options = widget.options || {};
  widget.options.tooltip = text;
}

function setupNodeWidgetTooltips(node, nodeName) {
  const tooltips = WIDGET_TOOLTIPS[nodeName];
  if (!tooltips) {
    return;
  }
  for (const widget of node.widgets || []) {
    setWidgetTooltip(widget, tooltips[widget.name]);
  }
}

function setWidgetHidden(widget, hidden) {
  if (!widget) {
    return;
  }
  if (!widget._promptSequenceOriginalType) {
    widget._promptSequenceOriginalType = widget.type;
    widget._promptSequenceOriginalComputeSize = widget.computeSize;
  }
  if (hidden) {
    widget.type = "hidden";
    widget.computeSize = () => [0, -4];
  } else {
    widget.type = widget._promptSequenceOriginalType;
    widget.computeSize = widget._promptSequenceOriginalComputeSize;
  }
}

function isInputConnected(node, inputName) {
  return Boolean(
    (node.inputs || []).find((input) => input.name === inputName && input.link != null),
  );
}

function setupComboNode(node) {
  if (node._promptSequenceComboReady) {
    return;
  }
  node._promptSequenceComboReady = true;

  const syncWidgets = () => {
    const promptsWidget = getWidget(node, "prompts");
    const sourceWidget = getWidget(node, "source");
    const sourceConnected = isInputConnected(node, "source");
    setWidgetHidden(promptsWidget, sourceConnected);
    setWidgetHidden(sourceWidget, true);
    if (promptsWidget) {
      setWidgetTooltip(
        promptsWidget,
        sourceConnected
          ? "Source is connected. Local prompts are hidden, ignored, and saved only for later reuse."
          : WIDGET_TOOLTIPS.ComfyUIPromptSequenceCombo.prompts,
      );
    }
    node.setSize?.(node.computeSize?.() || node.size);
    app.graph?.setDirtyCanvas(true, true);
  };

  const previousOnConfigure = node.onConfigure;
  node.onConfigure = function () {
    const result = previousOnConfigure?.apply(this, arguments);
    syncWidgets();
    return result;
  };

  const previousOnConnectionsChange = node.onConnectionsChange;
  node.onConnectionsChange = function () {
    const result = previousOnConnectionsChange?.apply(this, arguments);
    syncWidgets();
    return result;
  };

  syncWidgets();
}

function isJoinTextInput(input) {
  return /^text_\d+$/.test(input?.name || "");
}

function joinInputNumber(input) {
  const match = /^text_(\d+)$/.exec(input?.name || "");
  return match ? Number.parseInt(match[1], 10) : 0;
}

function resizeJoinInputs(node, requestedCount) {
  const count = clampJoinInputCount(requestedCount);
  for (let index = (node.inputs?.length || 0) - 1; index >= 0; index -= 1) {
    const input = node.inputs[index];
    if (isJoinTextInput(input) && joinInputNumber(input) > count) {
      node.removeInput(index);
    }
  }

  const existing = new Set(
    (node.inputs || []).filter(isJoinTextInput).map((input) => joinInputNumber(input)),
  );
  for (let index = 1; index <= count; index += 1) {
    if (!existing.has(index)) {
      node.addInput(`text_${index}`, "STRING");
    }
  }

  const inputCountWidget = getWidget(node, "input_count");
  if (inputCountWidget) {
    inputCountWidget.value = count;
  }
  node.setSize?.(node.computeSize?.() || node.size);
  app.graph?.setDirtyCanvas(true, true);
}

function setupJoinNode(node) {
  if (node._promptSequenceJoinReady) {
    return;
  }
  node._promptSequenceJoinReady = true;

  const update = () => {
    const inputCountWidget = getWidget(node, "input_count");
    resizeJoinInputs(node, inputCountWidget?.value ?? 2);
  };

  const updateWidget = node.addWidget("button", "update inputs", null, update);
  setWidgetTooltip(updateWidget, WIDGET_TOOLTIPS.ComfyUIPromptSequenceJoin["update inputs"]);

  const previousOnConfigure = node.onConfigure;
  node.onConfigure = function () {
    const result = previousOnConfigure?.apply(this, arguments);
    update();
    return result;
  };

  update();
}

function setupPicker(node, pickerOptions = {}) {
  const options = {
    containThumb: false,
    preserveImage: false,
    requireImage: false,
    supportsMask: false,
    ...pickerOptions,
  };

  injectStyle();
  const selectionWidget = hideRawSelectionWidget(node);
  if (!selectionWidget) {
    return;
  }

  const root = document.createElement("div");
  root.className = `ps-picker${options.containThumb ? " ps-contain" : ""}`;
  stopCanvasEvents(root);

  const state = readSelection(selectionWidget);
  const editor = { item: null };
  let library = { projects: [] };

  const menu = document.createElement("div");
  menu.className = "ps-menu";
  document.body.append(menu);

  const toolbar = document.createElement("div");
  toolbar.className = "ps-toolbar";
  const projectSelect = document.createElement("select");
  const topicSelect = document.createElement("select");
  const refreshButton = makeButton("Refresh");
  const addButton = makeButton("Add");
  toolbar.append(projectSelect, topicSelect, refreshButton, addButton);

  const grid = document.createElement("div");
  grid.className = "ps-grid";

  const editorPanel = document.createElement("div");
  editorPanel.className = "ps-editor";
  const editorGrid = document.createElement("div");
  editorGrid.className = "ps-editor-grid";
  const projectInput = makeInput("Project");
  const topicInput = makeInput("Topic");
  const nameInput = makeInput("Prompt name");
  const imageField = makeFileField(options.supportsMask ? "Image file" : "Preview image");
  const imageInput = imageField.input;
  const maskField = makeFileField("Mask file");
  const maskInput = maskField.input;
  if (options.supportsMask) {
    editorGrid.append(projectInput, topicInput, nameInput, imageField.field, maskField.field);
  } else {
    editorGrid.append(projectInput, topicInput, nameInput, imageField.field);
  }

  const promptInput = document.createElement("textarea");
  promptInput.placeholder = "Prompt";

  const editorActions = document.createElement("div");
  editorActions.className = "ps-editor-actions";
  const cancelButton = makeButton("Cancel");
  const saveButton = makeButton("Save");
  editorActions.append(cancelButton, saveButton);
  editorPanel.append(editorGrid, promptInput, editorActions);

  const status = document.createElement("div");
  status.className = "ps-status";

  root.append(toolbar, grid, editorPanel, status);

  const hideMenu = () => {
    menu.style.display = "none";
    menu.textContent = "";
  };

  const openEditor = (item = null) => {
    const project = findProject(library, state.project);
    const topic = item
      ? topicForItem(project, item)
      : findTopic(project, state.topic) || project?.topics?.[0] || null;
    editor.item = item;
    projectInput.value = project?.name || "";
    topicInput.value = topic?.name || "";
    nameInput.value = item?.name || "";
    promptInput.value = item?.prompt || "";
    imageInput.value = "";
    maskInput.value = "";
    editorPanel.classList.add("ps-open");
    nameInput.focus();
  };

  const closeEditor = () => {
    editor.item = null;
    editorPanel.classList.remove("ps-open");
    projectInput.value = "";
    topicInput.value = "";
    nameInput.value = "";
    promptInput.value = "";
    imageInput.value = "";
    maskInput.value = "";
  };

  const renderProjects = () => {
    projectSelect.textContent = "";
    if (!library.projects.length) {
      projectSelect.append(option("", "No projects", true));
      return;
    }
    for (const project of library.projects) {
      projectSelect.append(option(project.id, project.name, project.id === state.project));
    }
  };

  const renderTopics = () => {
    topicSelect.textContent = "";
    const project = findProject(library, state.project);
    const topics = project?.topics || [];
    if (!topics.length) {
      topicSelect.append(option("", "No topics", true));
      return;
    }
    topicSelect.append(option(ALL_TOPICS, "All topics", state.topic === ALL_TOPICS));
    for (const topic of topics) {
      topicSelect.append(option(topic.id, topic.name, topic.id === state.topic));
    }
  };

  const renderMenu = (event, item) => {
    event.preventDefault();
    event.stopPropagation();
    hideMenu();

    const editButton = makeButton("Edit");
    const deleteButton = makeButton("Delete");
    menu.append(editButton, deleteButton);
    menu.style.left = `${event.clientX}px`;
    menu.style.top = `${event.clientY}px`;
    menu.style.display = "block";

    editButton.addEventListener("click", () => {
      hideMenu();
      openEditor(item);
    });

    deleteButton.addEventListener("click", async () => {
      hideMenu();
      if (!confirm(`Delete "${item.name}"?`)) {
        return;
      }
      status.textContent = "Deleting";
      try {
        const result = await deletePromptAsset(item.id);
        library = result.library || (await fetchLibrary());
        state.selected = (state.selected || []).filter((id) => id !== item.id);
        writeSelection(node, selectionWidget, state);
        render();
        status.textContent = "Deleted";
      } catch (error) {
        status.textContent = error.message || "Delete failed";
      }
    });
  };

  const toggleItem = (item, checked) => {
    const selected = new Set(state.selected || []);
    if (checked) {
      selected.add(item.id);
    } else {
      selected.delete(item.id);
    }
    state.selected = Array.from(selected);
    writeSelection(node, selectionWidget, state);
    renderItems();
  };

  const renderItems = () => {
    grid.textContent = "";
    const items = currentItems(library, state);
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "ps-empty";
      empty.textContent = state.topic === ALL_TOPICS ? "No prompts in this project." : "No prompts in this topic.";
      grid.append(empty);
      return;
    }

    const selected = new Set(state.selected || []);
    for (const item of items) {
      const card = document.createElement("label");
      card.className = `ps-card${selected.has(item.id) ? " ps-selected" : ""}`;
      card.tabIndex = 0;
      card.addEventListener("contextmenu", (event) => renderMenu(event, item));

      const checkbox = document.createElement("input");
      checkbox.className = "ps-check";
      checkbox.type = "checkbox";
      checkbox.checked = selected.has(item.id);
      checkbox.addEventListener("change", () => toggleItem(item, checkbox.checked));

      const mediaWrap = document.createElement("div");
      mediaWrap.className = "ps-media";
      const media = item.image_url ? document.createElement("img") : document.createElement("div");
      if (item.image_url) {
        media.className = "ps-thumb";
        media.src = `${item.image_url}&t=${encodeURIComponent(item.updated_at || "")}`;
        media.alt = item.name;
      } else {
        media.className = "ps-placeholder";
        media.textContent = "No image";
      }
      mediaWrap.append(media);

      const name = document.createElement("div");
      name.className = "ps-name";
      name.textContent = item.name;

      const detail = document.createElement("div");
      detail.className = "ps-detail";
      detail.textContent = item.prompt || "(empty prompt)";

      card.append(checkbox, mediaWrap, name, detail);
      grid.append(card);
    }
  };

  const render = () => {
    Object.assign(state, normalizeState(library, state));
    writeSelection(node, selectionWidget, state);
    renderProjects();
    renderTopics();
    renderItems();
  };

  const refresh = async () => {
    refreshButton.disabled = true;
    status.textContent = "Loading";
    try {
      library = await fetchLibrary();
      render();
      status.textContent = "";
    } catch (error) {
      status.textContent = error.message || "Failed";
    } finally {
      refreshButton.disabled = false;
    }
  };

  projectSelect.addEventListener("change", () => {
    state.project = projectSelect.value;
    state.topic = ALL_TOPICS;
    state.selected = [];
    closeEditor();
    render();
  });

  topicSelect.addEventListener("change", () => {
    state.topic = topicSelect.value;
    state.selected = [];
    closeEditor();
    render();
  });

  refreshButton.addEventListener("click", refresh);
  addButton.addEventListener("click", () => openEditor(null));
  cancelButton.addEventListener("click", closeEditor);

  saveButton.addEventListener("click", async () => {
    const form = new FormData();
    if (editor.item?.id) {
      form.set("id", editor.item.id);
    }
    if (options.preserveImage) {
      form.set("preserve_image", "1");
    }
    form.set("project", projectInput.value.trim());
    form.set("topic", topicInput.value.trim());
    form.set("name", nameInput.value.trim());
    form.set("prompt", promptInput.value.trim());
    if (imageInput.files?.[0]) {
      form.set("image", imageInput.files[0]);
    }
    if (options.supportsMask && maskInput.files?.[0]) {
      form.set("mask", maskInput.files[0]);
    }

    if (!form.get("project") || !form.get("topic") || !form.get("name")) {
      status.textContent = "Project, topic, and name are required.";
      return;
    }
    if (options.requireImage && !editor.item?.image && !imageInput.files?.[0]) {
      status.textContent = "Image is required.";
      return;
    }

    saveButton.disabled = true;
    status.textContent = "Saving";
    try {
      const result = await savePromptAsset(form);
      library = result.library || (await fetchLibrary());
      state.project = result.item?.project?.id || state.project;
      state.topic = result.item?.topic?.id || state.topic;
      state.selected = [result.item?.id].filter(Boolean);
      closeEditor();
      render();
      status.textContent = "Saved";
    } catch (error) {
      status.textContent = error.message || "Save failed";
    } finally {
      saveButton.disabled = false;
    }
  });

  document.addEventListener("click", hideMenu);
  const previousOnRemoved = node.onRemoved;
  node.onRemoved = function () {
    previousOnRemoved?.apply(this, arguments);
    hideMenu();
    document.removeEventListener("click", hideMenu);
    menu.remove();
  };

  node.addDOMWidget("prompt_assets", "custom", root, {
    getValue: () => selectionWidget.value,
    setValue: (value) => {
      selectionWidget.value = value || "{}";
      Object.assign(state, readSelection(selectionWidget));
      render();
    },
  });

  const previousOnResize = node.onResize;
  node.onResize = function (size) {
    previousOnResize?.apply(this, arguments);
    root.style.width = `${Math.max(320, size[0] - 20)}px`;
  };

  node.setSize([Math.max(node.size[0], 420), Math.max(node.size[1], 500)]);
  refresh();
}

app.registerExtension({
  name: "comfyui.prompt_sequence",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!WIDGET_TOOLTIPS[nodeData.name]) {
      return;
    }

    const baseOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = baseOnNodeCreated?.apply(this, arguments);
      setupNodeWidgetTooltips(this, nodeData.name);
      return result;
    };

    if (nodeData.name === IMAGE_SEQUENCE_CLASS) {
      const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const result = onNodeCreated?.apply(this, arguments);
        setupPicker(this);
        return result;
      };
    }

    if (nodeData.name === IMAGE_MASK_SEQUENCE_CLASS) {
      const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const result = onNodeCreated?.apply(this, arguments);
        setupPicker(this, {
          containThumb: true,
          preserveImage: true,
          requireImage: true,
          supportsMask: true,
        });
        return result;
      };
    }

    if (nodeData.name === JOIN_CLASS) {
      const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const result = onNodeCreated?.apply(this, arguments);
        setupJoinNode(this);
        return result;
      };
    }

    if (nodeData.name === COMBO_CLASS) {
      const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const result = onNodeCreated?.apply(this, arguments);
        setupComboNode(this);
        return result;
      };
    }
  },
});
