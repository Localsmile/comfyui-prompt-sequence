from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from urllib.parse import unquote, urlparse
import tkinter as tk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = None
    TkinterDnD = None


MAX_PREVIEW_SIDE = 512
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
MASK_SUFFIXES = (
    "_mask",
    "-mask",
    " mask",
    ".mask",
    "_alpha",
    "-alpha",
    " alpha",
)
PROMPT_MODES = {
    "Sidecar .txt, else filename": "sidecar",
    "Filename": "filename",
    "Common prompt": "common",
    "Empty": "empty",
}


@dataclass
class CardDraft:
    image_path: Path
    name: str
    prompt: str
    project_name: str = "My Prompt Project"
    topic_name: str = "Default"
    mask_path: Path | None = None
    item_slug: str | None = None
    source_item_path: Path | None = None


def stable_hash(value: str, size: int = 8) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:size]


def slugify(value: str, fallback_prefix: str) -> str:
    raw = str(value or "").strip()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", ascii_text).strip("-._").lower()
    slug = re.sub(r"-{2,}", "-", slug)[:80].strip("-._")
    if slug:
        return slug
    return f"{fallback_prefix}-{stable_hash(raw or fallback_prefix)}"


def json_write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def json_load(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def clean_name(path: Path) -> str:
    text = re.sub(r"[_-]+", " ", path.stem).strip()
    return re.sub(r"\s+", " ", text) or path.stem


def read_sidecar_prompt(path: Path) -> str:
    sidecar = path.with_suffix(".txt")
    if not sidecar.exists():
        return ""
    try:
        return sidecar.read_text(encoding="utf-8-sig").strip()
    except UnicodeDecodeError:
        return sidecar.read_text(encoding="cp949", errors="ignore").strip()


def path_from_drop(raw: str) -> Path:
    text = raw.strip()
    if text.startswith("file:"):
        parsed = urlparse(text)
        text = unquote(parsed.path)
        if re.match(r"^/[a-zA-Z]:/", text):
            text = text[1:]
    return Path(text).expanduser()


def collect_image_paths(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS:
                    found.append(child)
        elif path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            found.append(path)
    return sorted(found, key=lambda item: str(item).lower())


def match_key(path: Path) -> str:
    stem = path.stem.lower()
    changed = True
    while changed:
        changed = False
        for suffix in MASK_SUFFIXES:
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                changed = True
    return re.sub(r"[^a-z0-9]+", "", stem)


def save_preview_image(input_path: Path, output_path: Path) -> str:
    try:
        from PIL import Image, ImageOps
    except Exception as exc:
        raise RuntimeError("Pillow is required. Install with: python -m pip install Pillow") from exc

    if input_path.resolve() == output_path.resolve():
        return output_path.name

    with Image.open(input_path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        image.thumbnail((MAX_PREVIEW_SIDE, MAX_PREVIEW_SIDE), resampling)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG", optimize=True)
    return output_path.name


def save_full_image(input_path: Path, output_path: Path) -> str:
    try:
        from PIL import Image, ImageOps
    except Exception as exc:
        raise RuntimeError("Pillow is required. Install with: python -m pip install Pillow") from exc

    if input_path.resolve() == output_path.resolve():
        return output_path.name

    with Image.open(input_path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG", optimize=True)
    return output_path.name


def unique_slug(topic_dir: Path, base_slug: str, overwrite: bool, used: set[str]) -> str:
    if overwrite and base_slug not in used:
        used.add(base_slug)
        return base_slug
    candidate = base_slug
    index = 2
    while candidate in used or (not overwrite and (topic_dir / candidate).exists()):
        candidate = f"{base_slug}-{index}"
        index += 1
    used.add(candidate)
    return candidate


def scan_topics(root_dir: Path) -> list[dict[str, object]]:
    projects_dir = root_dir / "projects"
    if not projects_dir.exists():
        return []
    topics: list[dict[str, object]] = []
    for project_dir in sorted([item for item in projects_dir.iterdir() if item.is_dir()], key=lambda item: item.name.lower()):
        project_meta = json_load(project_dir / "project.json", {})
        project_name = project_meta.get("name") if isinstance(project_meta, dict) else None
        project_name = str(project_name or project_dir.name)
        for topic_dir in sorted([item for item in project_dir.iterdir() if item.is_dir()], key=lambda item: item.name.lower()):
            topic_meta = json_load(topic_dir / "topic.json", {})
            topic_name = topic_meta.get("name") if isinstance(topic_meta, dict) else None
            topic_name = str(topic_name or topic_dir.name)
            card_count = sum(1 for item in topic_dir.iterdir() if item.is_dir() and (item / "prompt.json").exists())
            if card_count:
                topics.append(
                    {
                        "project_slug": project_dir.name,
                        "project_name": project_name,
                        "topic_slug": topic_dir.name,
                        "topic_name": topic_name,
                        "topic_dir": topic_dir,
                        "card_count": card_count,
                    }
                )
    return sorted(topics, key=lambda item: (str(item["project_name"]).lower(), str(item["topic_name"]).lower()))


def load_cards_from_topic(topic_dir: Path) -> tuple[str, str, list[CardDraft], str]:
    project_dir = topic_dir.parent
    project_meta = json_load(project_dir / "project.json", {})
    topic_meta = json_load(topic_dir / "topic.json", {})
    project_meta_name = project_meta.get("name") if isinstance(project_meta, dict) else None
    topic_meta_name = topic_meta.get("name") if isinstance(topic_meta, dict) else None
    project_name = str(project_meta_name or project_dir.name)
    topic_name = str(topic_meta_name or topic_dir.name)
    cards: list[CardDraft] = []
    has_full_image = False
    has_mask = False

    item_dirs = [item for item in topic_dir.iterdir() if item.is_dir() and (item / "prompt.json").exists()]
    for item_dir in sorted(item_dirs, key=lambda item: item.name.lower()):
        metadata = json_load(item_dir / "prompt.json", {})
        if not isinstance(metadata, dict):
            continue
        image_name = str(metadata.get("image") or "")
        image_path = item_dir / image_name if image_name else item_dir / "preview.png"
        if not image_path.exists():
            continue
        mask_name = str(metadata.get("mask") or "")
        mask_path = item_dir / mask_name if mask_name and (item_dir / mask_name).exists() else None
        name = str(metadata.get("name") or item_dir.name)
        prompt = str(metadata.get("prompt") or "")
        cards.append(
            CardDraft(
                image_path=image_path,
                name=name,
                prompt=prompt,
                project_name=project_name,
                topic_name=topic_name,
                mask_path=mask_path,
                item_slug=item_dir.name,
                source_item_path=item_dir,
            )
        )
        has_full_image = has_full_image or image_name == "image.png" or image_path.name == "image.png"
        has_mask = has_mask or mask_path is not None

    cards.sort(key=lambda item: item.name.lower())
    node_type = "image_mask_sequence" if has_full_image or has_mask else "image_sequence"
    return project_name, topic_name, cards, node_type


def load_cards_from_project(project_dir: Path) -> tuple[str, str, list[CardDraft], str]:
    project_meta = json_load(project_dir / "project.json", {})
    project_meta_name = project_meta.get("name") if isinstance(project_meta, dict) else None
    project_name = str(project_meta_name or project_dir.name)
    cards: list[CardDraft] = []
    has_mask_sequence = False
    topic_names: list[str] = []
    topic_dirs = [item for item in project_dir.iterdir() if item.is_dir()]
    for topic_dir in sorted(topic_dirs, key=lambda item: item.name.lower()):
        _, topic_name, topic_cards, node_type = load_cards_from_topic(topic_dir)
        if topic_cards:
            topic_names.append(topic_name)
            cards.extend(topic_cards)
            has_mask_sequence = has_mask_sequence or node_type == "image_mask_sequence"
    cards.sort(key=lambda item: (item.project_name.lower(), item.topic_name.lower(), item.name.lower()))
    default_topic = topic_names[0] if len(topic_names) == 1 else "Default"
    node_type = "image_mask_sequence" if has_mask_sequence else "image_sequence"
    return project_name, default_topic, cards, node_type


class PromptProjectApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.cards: list[CardDraft] = []
        self.projects: dict[str, set[str]] = {}
        self.deleted_item_paths: set[Path] = set()
        self.deleted_topic_paths: set[Path] = set()
        self.deleted_project_paths: set[Path] = set()
        self.drag_card_indices: list[int] = []
        self.last_selected_card_ids: set[int] = set()
        self.root_dir = tk.StringVar(value=str(Path(__file__).resolve().parent))
        self.node_type = tk.StringVar(value="image_sequence")
        self.prompt_mode = tk.StringVar(value=next(iter(PROMPT_MODES)))
        self.overwrite = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="")
        self.editor_loading = False
        self.sort_column = "name"
        self.sort_reverse = False

        self.root.title("Prompt Sequence Project Builder")
        self.root.geometry("1280x760")
        self.root.minsize(1100, 640)
        self.build_ui()
        self.ensure_project_topic("Project", "Default")
        self.refresh_all(select_project="Project")
        self.update_status()

    def build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        workspace = ttk.LabelFrame(self.root, text="Workspace", padding=10)
        workspace.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        workspace.columnconfigure(1, weight=1)
        ttk.Label(workspace, text="Custom node folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(workspace, textvariable=self.root_dir).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(workspace, text="Browse", command=self.browse_root).grid(row=0, column=2)
        ttk.Button(workspace, text="Load", command=self.open_load_project_dialog).grid(row=0, column=3, padx=(6, 0))
        ttk.Button(workspace, text="Open projects", command=self.open_projects_folder).grid(row=0, column=4, padx=(6, 0))

        import_frame = ttk.LabelFrame(self.root, text="Import and batch edit", padding=10)
        import_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        import_frame.columnconfigure(5, weight=1)
        ttk.Radiobutton(import_frame, text="Image Sequence", value="image_sequence", variable=self.node_type).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(import_frame, text="Image Mask Sequence", value="image_mask_sequence", variable=self.node_type).grid(row=0, column=1, sticky="w", padx=(14, 0))
        ttk.Checkbutton(import_frame, text="Overwrite on save", variable=self.overwrite).grid(row=0, column=2, sticky="w", padx=(14, 0))
        ttk.Label(import_frame, text="Prompt on add").grid(row=0, column=3, sticky="e", padx=(22, 6))
        ttk.Combobox(import_frame, textvariable=self.prompt_mode, values=list(PROMPT_MODES), state="readonly", width=28).grid(row=0, column=4, sticky="w")

        self.image_drop = ttk.Label(import_frame, text="Drop images/folders here", relief="ridge", anchor="center", padding=12)
        self.image_drop.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0), padx=(0, 6))
        self.mask_drop = ttk.Label(import_frame, text="Drop masks here", relief="ridge", anchor="center", padding=12)
        self.mask_drop.grid(row=1, column=3, columnspan=3, sticky="ew", pady=(8, 0), padx=(6, 0))
        self.enable_drop(self.image_drop, self.handle_image_drop)
        self.enable_drop(self.mask_drop, self.handle_mask_drop)

        common = ttk.Frame(import_frame)
        common.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        common.columnconfigure(1, weight=1)
        ttk.Label(common, text="Common prompt").grid(row=0, column=0, sticky="nw", padx=(0, 6))
        self.common_prompt = scrolledtext.ScrolledText(common, height=3, wrap="word")
        self.common_prompt.grid(row=0, column=1, sticky="ew")
        ttk.Button(common, text="Apply to selected", command=self.apply_common_to_selected).grid(row=0, column=2, sticky="ns", padx=(8, 0))
        ttk.Button(common, text="Apply to visible", command=self.apply_common_to_visible).grid(row=0, column=3, sticky="ns", padx=(6, 0))

        body = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=3)
        body.columnconfigure(2, weight=2)
        body.rowconfigure(0, weight=1)

        nav = ttk.LabelFrame(body, text="Projects and topics", padding=8)
        nav.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        nav.columnconfigure(0, weight=1)
        nav.columnconfigure(1, weight=1)
        nav.rowconfigure(0, weight=1)

        project_frame = ttk.Frame(nav)
        project_frame.grid(row=0, column=0, sticky="nsew")
        project_frame.columnconfigure(0, weight=1)
        project_frame.rowconfigure(0, weight=1)
        self.project_tree = ttk.Treeview(project_frame, columns=("project", "cards"), show="headings", selectmode="browse", height=8)
        self.project_tree.heading("project", text="Project")
        self.project_tree.heading("cards", text="Cards")
        self.project_tree.column("project", width=160, stretch=True)
        self.project_tree.column("cards", width=48, anchor="e", stretch=False)
        self.project_tree.grid(row=0, column=0, sticky="nsew")
        project_scroll = ttk.Scrollbar(project_frame, orient="vertical", command=self.project_tree.yview)
        project_scroll.grid(row=0, column=1, sticky="ns")
        self.project_tree.configure(yscrollcommand=project_scroll.set)
        self.project_tree.bind("<<TreeviewSelect>>", self.on_project_selected)

        project_controls = ttk.Frame(project_frame)
        project_controls.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 10))
        project_controls.columnconfigure(0, weight=1)
        self.project_entry = tk.StringVar()
        ttk.Entry(project_controls, textvariable=self.project_entry).grid(row=0, column=0, columnspan=3, sticky="ew")
        ttk.Button(project_controls, text="Add", command=self.add_project).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(project_controls, text="Rename", command=self.rename_project).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(4, 0))
        ttk.Button(project_controls, text="Remove", command=self.remove_project).grid(row=1, column=2, sticky="ew", padx=(4, 0), pady=(4, 0))
        ttk.Button(project_controls, text="Move selected here", command=self.move_selected_to_project).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        topic_frame = ttk.Frame(nav)
        topic_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        topic_frame.columnconfigure(0, weight=1)
        topic_frame.rowconfigure(0, weight=1)
        self.topic_tree = ttk.Treeview(topic_frame, columns=("topic", "cards"), show="headings", selectmode="browse", height=8)
        self.topic_tree.heading("topic", text="Topic")
        self.topic_tree.heading("cards", text="Cards")
        self.topic_tree.column("topic", width=160, stretch=True)
        self.topic_tree.column("cards", width=48, anchor="e", stretch=False)
        self.topic_tree.grid(row=0, column=0, sticky="nsew")
        topic_scroll = ttk.Scrollbar(topic_frame, orient="vertical", command=self.topic_tree.yview)
        topic_scroll.grid(row=0, column=1, sticky="ns")
        self.topic_tree.configure(yscrollcommand=topic_scroll.set)
        self.topic_tree.bind("<<TreeviewSelect>>", self.on_topic_selected)

        topic_controls = ttk.Frame(topic_frame)
        topic_controls.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        topic_controls.columnconfigure(0, weight=1)
        self.topic_entry = tk.StringVar()
        ttk.Entry(topic_controls, textvariable=self.topic_entry).grid(row=0, column=0, columnspan=3, sticky="ew")
        ttk.Button(topic_controls, text="Add", command=self.add_topic).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(topic_controls, text="Rename", command=self.rename_topic).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(4, 0))
        ttk.Button(topic_controls, text="Remove", command=self.remove_topic).grid(row=1, column=2, sticky="ew", padx=(4, 0), pady=(4, 0))
        ttk.Button(topic_controls, text="Move selected here", command=self.move_selected_to_topic).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        table_frame = ttk.LabelFrame(body, text="Images and prompts", padding=8)
        table_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("project", "topic", "name", "prompt", "image", "mask")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        for column, text, width in (
            ("project", "Project", 110),
            ("topic", "Topic", 110),
            ("name", "Name", 150),
            ("prompt", "Prompt", 240),
            ("image", "Image", 160),
            ("mask", "Mask", 120),
        ):
            self.tree.heading(column, text=text, command=lambda value=column: self.sort_cards(value))
            self.tree.column(column, width=width, stretch=column in {"prompt", "image"})
        self.tree.grid(row=0, column=0, sticky="nsew")
        table_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        table_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=table_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_card_selected)
        self.tree.bind("<ButtonPress-1>", self.on_card_drag_start)
        self.tree.bind("<ButtonRelease-1>", self.on_card_drag_release)

        buttons = ttk.Frame(table_frame)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Add images", command=self.browse_images).pack(side="left")
        ttk.Button(buttons, text="Add masks", command=self.browse_masks).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Use sidecars", command=self.use_sidecars).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Select visible", command=self.select_visible_cards).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Remove selected", command=self.remove_selected).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Clear visible", command=self.clear_visible_cards).pack(side="left", padx=(6, 0))

        editor = ttk.LabelFrame(body, text="Selected card", padding=10)
        editor.grid(row=0, column=2, sticky="nsew")
        editor.columnconfigure(1, weight=1)
        editor.rowconfigure(1, weight=1)
        ttk.Label(editor, text="Name").grid(row=0, column=0, sticky="w")
        self.card_name = tk.StringVar()
        ttk.Entry(editor, textvariable=self.card_name).grid(row=0, column=1, sticky="ew")
        self.card_name.trace_add("write", lambda *_args: self.on_card_name_changed())
        ttk.Label(editor, text="Prompt").grid(row=1, column=0, sticky="nw", pady=(8, 0))
        self.card_prompt = scrolledtext.ScrolledText(editor, height=10, wrap="word")
        self.card_prompt.grid(row=1, column=1, sticky="nsew", pady=(8, 0))
        self.card_prompt.bind("<<Modified>>", self.on_card_prompt_changed)
        ttk.Label(editor, text="Project").grid(row=2, column=0, sticky="w")
        self.project_label = tk.StringVar()
        ttk.Entry(editor, textvariable=self.project_label, state="readonly").grid(row=2, column=1, sticky="ew")
        ttk.Label(editor, text="Topic").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.topic_label = tk.StringVar()
        ttk.Entry(editor, textvariable=self.topic_label, state="readonly").grid(row=3, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(editor, text="Image").grid(row=4, column=0, sticky="w")
        self.image_label = tk.StringVar()
        ttk.Entry(editor, textvariable=self.image_label, state="readonly").grid(row=4, column=1, sticky="ew")
        ttk.Label(editor, text="Mask").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.mask_label = tk.StringVar()
        ttk.Entry(editor, textvariable=self.mask_label, state="readonly").grid(row=5, column=1, sticky="ew", pady=(8, 0))
        editor_buttons = ttk.Frame(editor)
        editor_buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(editor_buttons, text="Browse mask", command=self.browse_mask_for_selected).pack(side="left")
        ttk.Button(editor_buttons, text="Clear mask", command=self.clear_mask_for_selected).pack(side="left", padx=(6, 0))

        bottom = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.status).grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text="Save projects", command=self.save_projects).grid(row=0, column=1, sticky="e")

    def enable_drop(self, widget: tk.Widget, callback) -> None:
        if not DND_FILES or not hasattr(widget, "drop_target_register"):
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", lambda event: callback(self.parse_drop(event.data)))
        except tk.TclError:
            return

    def parse_drop(self, data: str) -> list[Path]:
        try:
            values = self.root.tk.splitlist(data)
        except tk.TclError:
            values = re.findall(r"\{([^}]*)\}|(\S+)", data)
            values = [first or second for first, second in values]
        return [path_from_drop(value) for value in values]

    def update_status(self, text: str | None = None) -> None:
        if text is not None:
            self.status.set(text)
            return
        if DND_FILES:
            self.status.set("Select a project, then add or drag images. Drag selected cards onto a project or topic to move them.")
        else:
            self.status.set("Install tkinterdnd2 to enable file drag and drop.")

    def ensure_project_topic(self, project: str, topic: str | None = None) -> None:
        project = project.strip() or "Project"
        if project not in self.projects:
            self.projects[project] = set()
        if topic is not None:
            topic = topic.strip() or "Default"
            self.projects[project].add(topic)

    def rebuild_projects_from_cards(self) -> None:
        for card in self.cards:
            self.ensure_project_topic(card.project_name, card.topic_name)

    def selected_project(self) -> str | None:
        selection = self.project_tree.selection()
        if not selection:
            return None
        values = self.project_tree.item(selection[0], "values")
        return str(values[0]) if values else None

    def selected_topic(self) -> str | None:
        selection = self.topic_tree.selection()
        if not selection:
            return None
        values = self.topic_tree.item(selection[0], "values")
        return str(values[0]) if values else None

    def current_import_target(self) -> tuple[str, str]:
        project = self.selected_project()
        if not project:
            project = sorted(self.projects, key=str.lower)[0] if self.projects else "Project"
        topics = self.projects.setdefault(project, set())
        topic = self.selected_topic()
        if not topic or topic not in topics:
            topic = sorted(topics, key=str.lower)[0] if topics else "Default"
        self.ensure_project_topic(project, topic)
        return project, topic

    def refresh_all(self, select_project: str | None = None, select_topic: str | None = None, select_card: int | None = None) -> None:
        self.rebuild_projects_from_cards()
        self.refresh_project_tree(select_project)
        self.refresh_topic_tree(select_topic)
        self.refresh_tree(select_card)
        self.load_selected_card()

    def project_card_count(self, project: str) -> int:
        return sum(1 for card in self.cards if card.project_name == project)

    def topic_card_count(self, project: str, topic: str) -> int:
        return sum(1 for card in self.cards if card.project_name == project and card.topic_name == topic)

    def refresh_project_tree(self, select_project: str | None = None) -> None:
        current = select_project or self.selected_project()
        self.project_tree.delete(*self.project_tree.get_children())
        for index, project in enumerate(sorted(self.projects, key=str.lower)):
            self.project_tree.insert("", "end", iid=f"project-{index}", values=(project, self.project_card_count(project)))
        if current:
            for item in self.project_tree.get_children():
                if self.project_tree.item(item, "values")[0] == current:
                    self.project_tree.selection_set(item)
                    self.project_tree.focus(item)
                    return
        children = self.project_tree.get_children()
        if children:
            self.project_tree.selection_set(children[0])
            self.project_tree.focus(children[0])

    def refresh_topic_tree(self, select_topic: str | None = None) -> None:
        project = self.selected_project()
        current = select_topic if select_topic is not None else self.selected_topic()
        self.topic_tree.delete(*self.topic_tree.get_children())
        if not project:
            return
        for index, topic in enumerate(sorted(self.projects.get(project, set()), key=str.lower)):
            self.topic_tree.insert("", "end", iid=f"topic-{index}", values=(topic, self.topic_card_count(project, topic)))
        if current:
            for item in self.topic_tree.get_children():
                if self.topic_tree.item(item, "values")[0] == current:
                    self.topic_tree.selection_set(item)
                    self.topic_tree.focus(item)
                    return

    def on_project_selected(self, _event: tk.Event) -> None:
        self.topic_tree.selection_remove(self.topic_tree.selection())
        self.refresh_topic_tree(None)
        self.refresh_tree()
        self.load_selected_card()

    def on_topic_selected(self, _event: tk.Event) -> None:
        self.refresh_tree()
        self.load_selected_card()

    def add_project(self) -> None:
        name = self.project_entry.get().strip()
        if not name:
            self.update_status("Enter a project name.")
            return
        if name in self.projects:
            self.update_status("Project already exists.")
            return
        self.projects[name] = {"Default"}
        self.project_entry.set("")
        self.refresh_all(select_project=name)
        self.update_status(f"Added project: {name}")

    def rename_project(self) -> None:
        old = self.selected_project()
        new = self.project_entry.get().strip()
        if not old or not new:
            self.update_status("Select a project and enter a new name.")
            return
        if new != old and new in self.projects:
            self.update_status("Project already exists.")
            return
        topics = self.projects.pop(old, set())
        self.projects[new] = topics
        for card in self.cards:
            if card.project_name == old:
                card.project_name = new
        self.project_entry.set("")
        self.refresh_all(select_project=new)
        self.update_status(f"Renamed project: {old} -> {new}")

    def remove_project(self) -> None:
        project = self.selected_project()
        if not project:
            return
        if not messagebox.askyesno("Remove project", f"Remove project '{project}' and its cards from this builder?"):
            return
        for card in self.cards:
            if card.project_name == project and card.source_item_path:
                self.deleted_item_paths.add(card.source_item_path)
                self.deleted_project_paths.add(card.source_item_path.parent.parent)
        self.cards = [card for card in self.cards if card.project_name != project]
        self.projects.pop(project, None)
        self.refresh_all()
        self.update_status(f"Removed project: {project}")

    def add_topic(self) -> None:
        project = self.selected_project()
        name = self.topic_entry.get().strip()
        if not project:
            self.update_status("Select a project first.")
            return
        if not name:
            self.update_status("Enter a topic name.")
            return
        if name in self.projects.setdefault(project, set()):
            self.update_status("Topic already exists.")
            return
        self.projects[project].add(name)
        self.topic_entry.set("")
        self.refresh_all(select_project=project, select_topic=name)
        self.update_status(f"Added topic: {project} / {name}")

    def rename_topic(self) -> None:
        project = self.selected_project()
        old = self.selected_topic()
        new = self.topic_entry.get().strip()
        if not project or not old or not new:
            self.update_status("Select a topic and enter a new name.")
            return
        if new != old and new in self.projects.get(project, set()):
            self.update_status("Topic already exists.")
            return
        topics = self.projects.setdefault(project, set())
        topics.discard(old)
        topics.add(new)
        for card in self.cards:
            if card.project_name == project and card.topic_name == old:
                card.topic_name = new
        self.topic_entry.set("")
        self.refresh_all(select_project=project, select_topic=new)
        self.update_status(f"Renamed topic: {old} -> {new}")

    def remove_topic(self) -> None:
        project = self.selected_project()
        topic = self.selected_topic()
        if not project or not topic:
            return
        if not messagebox.askyesno("Remove topic", f"Remove topic '{project} / {topic}' and its cards from this builder?"):
            return
        for card in self.cards:
            if card.project_name == project and card.topic_name == topic and card.source_item_path:
                self.deleted_item_paths.add(card.source_item_path)
                self.deleted_topic_paths.add(card.source_item_path.parent)
        self.cards = [card for card in self.cards if not (card.project_name == project and card.topic_name == topic)]
        self.projects.setdefault(project, set()).discard(topic)
        self.refresh_all(select_project=project)
        self.update_status(f"Removed topic: {project} / {topic}")

    def move_selected_to_project(self) -> None:
        project = self.selected_project()
        if not project:
            self.update_status("Select a project first.")
            return
        topics = self.projects.setdefault(project, set())
        topic = self.selected_topic() if self.selected_topic() in topics else None
        topic = topic or (sorted(topics, key=str.lower)[0] if topics else "Default")
        self.move_selected_cards(project, topic)

    def move_selected_to_topic(self) -> None:
        project = self.selected_project()
        topic = self.selected_topic()
        if not project or not topic:
            self.update_status("Select a topic first.")
            return
        self.move_selected_cards(project, topic)

    def move_selected_cards(self, project: str, topic: str) -> None:
        indices = self.selected_indices() or self.last_selected_indices()
        if not indices:
            self.update_status("Select one or more cards first.")
            return
        self.ensure_project_topic(project, topic)
        moved_ids = {id(self.cards[index]) for index in indices}
        for index in indices:
            self.cards[index].project_name = project
            self.cards[index].topic_name = topic
        self.refresh_all(select_project=project, select_topic=topic)
        selection = [str(index) for index, card in enumerate(self.cards) if id(card) in moved_ids and self.tree.exists(str(index))]
        if selection:
            self.tree.selection_set(selection)
            self.tree.focus(selection[0])
            self.load_selected_card()
        self.update_status(f"Moved {len(indices)} card(s) to {project} / {topic}.")

    def last_selected_indices(self) -> list[int]:
        return [index for index, card in enumerate(self.cards) if id(card) in self.last_selected_card_ids]

    def on_card_drag_start(self, event: tk.Event) -> None:
        row = self.tree.identify_row(event.y)
        if row:
            if row not in self.tree.selection():
                self.tree.selection_set(row)
            self.drag_card_indices = self.selected_indices()
        else:
            self.drag_card_indices = []

    def on_card_drag_release(self, event: tk.Event) -> None:
        if not self.drag_card_indices:
            return
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        if self.is_descendant(widget, self.project_tree):
            row = self.project_tree.identify_row(event.y_root - self.project_tree.winfo_rooty())
            if row:
                project = str(self.project_tree.item(row, "values")[0])
                topics = self.projects.setdefault(project, set())
                topic = sorted(topics, key=str.lower)[0] if topics else "Default"
                old_selection = self.tree.selection()
                self.tree.selection_set([str(index) for index in self.drag_card_indices if self.tree.exists(str(index))])
                self.move_selected_cards(project, topic)
                if not old_selection:
                    self.tree.selection_remove(self.tree.selection())
            self.drag_card_indices = []
            return
        if self.is_descendant(widget, self.topic_tree):
            row = self.topic_tree.identify_row(event.y_root - self.topic_tree.winfo_rooty())
            project = self.selected_project()
            if row and project:
                topic = str(self.topic_tree.item(row, "values")[0])
                self.tree.selection_set([str(index) for index in self.drag_card_indices if self.tree.exists(str(index))])
                self.move_selected_cards(project, topic)
            self.drag_card_indices = []

    def is_descendant(self, widget: tk.Widget | None, parent: tk.Widget) -> bool:
        while widget is not None:
            if widget == parent:
                return True
            widget = widget.master
        return False

    def browse_root(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.root_dir.get() or str(Path.cwd()))
        if chosen:
            self.root_dir.set(chosen)

    def open_projects_folder(self) -> None:
        target = Path(self.root_dir.get()).expanduser() / "projects"
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(target)

    def open_load_project_dialog(self) -> None:
        root_dir = Path(self.root_dir.get()).expanduser()
        topics = scan_topics(root_dir)
        if not topics:
            messagebox.showinfo("No projects", f"No saved prompt projects found in:\n{root_dir / 'projects'}")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Load existing project")
        dialog.geometry("760x420")
        dialog.transient(self.root)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        columns = ("project", "topic", "cards", "path")
        tree = ttk.Treeview(dialog, columns=columns, show="headings", selectmode="browse")
        tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=(10, 0))
        tree.configure(yscrollcommand=scrollbar.set)
        for column, text, width in (("project", "Project", 180), ("topic", "Topic", 180), ("cards", "Cards", 70), ("path", "Folder", 300)):
            tree.heading(column, text=text)
            tree.column(column, width=width, anchor="e" if column == "cards" else "w")

        sort_state = {"column": "project", "reverse": False}

        def draw() -> None:
            selection = tree.selection()
            selected_topic = topics[int(selection[0])] if selection else None
            tree.delete(*tree.get_children())
            for index, item in enumerate(topics):
                tree.insert("", "end", iid=str(index), values=(item["project_name"], item["topic_name"], item["card_count"], str(item["topic_dir"])))
            if selected_topic:
                for index, item in enumerate(topics):
                    if item["topic_dir"] == selected_topic["topic_dir"]:
                        tree.selection_set(str(index))
                        tree.focus(str(index))
                        break

        def sort_by(column: str) -> None:
            if sort_state["column"] == column:
                sort_state["reverse"] = not sort_state["reverse"]
            else:
                sort_state["column"] = column
                sort_state["reverse"] = False
            key_map = {
                "project": lambda item: str(item["project_name"]).lower(),
                "topic": lambda item: str(item["topic_name"]).lower(),
                "cards": lambda item: int(item["card_count"]),
                "path": lambda item: str(item["topic_dir"]).lower(),
            }
            topics.sort(key=key_map[column], reverse=sort_state["reverse"])
            draw()

        for column in columns:
            tree.heading(column, command=lambda value=column: sort_by(value))

        footer = ttk.Frame(dialog, padding=10)
        footer.grid(row=1, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, text="Double-click loads the selected topic.").grid(row=0, column=0, sticky="w")

        def selected_topic() -> dict[str, object] | None:
            selection = tree.selection()
            return topics[int(selection[0])] if selection else None

        def load_selected_topic() -> None:
            topic = selected_topic()
            if topic:
                dialog.destroy()
                self.load_existing_topic(Path(topic["topic_dir"]))

        def load_selected_project() -> None:
            topic = selected_topic()
            if topic:
                dialog.destroy()
                self.load_existing_project(Path(topic["topic_dir"]).parent)

        ttk.Button(footer, text="Cancel", command=dialog.destroy).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(footer, text="Load topic", command=load_selected_topic).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(footer, text="Load project", command=load_selected_project).grid(row=0, column=3, padx=(8, 0))
        tree.bind("<Double-1>", lambda _event: load_selected_topic())
        draw()
        if topics:
            tree.selection_set("0")
            tree.focus("0")

    def load_existing_topic(self, topic_dir: Path) -> None:
        if self.cards and not messagebox.askyesno("Load topic", "Replace the current builder contents?"):
            return
        try:
            project_name, topic_name, cards, node_type = load_cards_from_topic(topic_dir)
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc))
            return
        self.cards = cards
        self.projects = {project_name: {topic_name}}
        self.deleted_item_paths.clear()
        self.deleted_topic_paths.clear()
        self.deleted_project_paths.clear()
        self.node_type.set(node_type)
        self.overwrite.set(True)
        self.refresh_all(select_project=project_name, select_topic=topic_name, select_card=0 if cards else None)
        self.update_status(f"Loaded {len(cards)} card(s) from {topic_dir}.")

    def load_existing_project(self, project_dir: Path) -> None:
        if self.cards and not messagebox.askyesno("Load project", "Replace the current builder contents?"):
            return
        try:
            project_name, _topic_name, cards, node_type = load_cards_from_project(project_dir)
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc))
            return
        self.cards = cards
        self.projects = {}
        self.rebuild_projects_from_cards()
        if project_name not in self.projects:
            self.projects[project_name] = set()
        self.deleted_item_paths.clear()
        self.deleted_topic_paths.clear()
        self.deleted_project_paths.clear()
        self.node_type.set(node_type)
        self.overwrite.set(True)
        self.refresh_all(select_project=project_name, select_card=0 if cards else None)
        self.update_status(f"Loaded {len(cards)} card(s) from {project_dir}.")

    def browse_images(self) -> None:
        files = filedialog.askopenfilenames(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff")])
        self.add_images([Path(file) for file in files])

    def browse_masks(self) -> None:
        files = filedialog.askopenfilenames(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff")])
        self.add_masks([Path(file) for file in files])

    def browse_mask_for_selected(self) -> None:
        indices = self.selected_indices()
        if not indices:
            self.update_status("Select one card first.")
            return
        file = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff")])
        if file:
            self.cards[indices[0]].mask_path = Path(file)
            self.refresh_tree(indices[0])
            self.load_selected_card()

    def handle_image_drop(self, paths: list[Path]) -> None:
        self.add_images(paths)

    def handle_mask_drop(self, paths: list[Path]) -> None:
        self.add_masks(paths)

    def add_images(self, paths: list[Path]) -> None:
        project, topic = self.current_import_target()
        images = collect_image_paths(paths)
        existing = {card.image_path.resolve() for card in self.cards if card.image_path.exists()}
        added_indices: list[int] = []
        for image in images:
            resolved = image.resolve()
            if resolved in existing:
                continue
            name = clean_name(image)
            prompt = self.prompt_for_image(image, name)
            self.cards.append(CardDraft(image_path=image, name=name, prompt=prompt, project_name=project, topic_name=topic))
            added_indices.append(len(self.cards) - 1)
            existing.add(resolved)
        self.refresh_all(select_project=project, select_topic=topic)
        visible_selection = [str(index) for index in added_indices if self.tree.exists(str(index))]
        if visible_selection:
            self.tree.selection_set(visible_selection)
            self.tree.focus(visible_selection[0])
            self.load_selected_card()
        self.update_status(f"Added {len(added_indices)} image(s) to {project} / {topic}.")

    def add_masks(self, paths: list[Path]) -> None:
        masks = collect_image_paths(paths)
        if not masks:
            self.update_status("No mask images found.")
            return
        selected = self.selected_indices()
        if len(selected) == 1 and len(masks) == 1:
            self.cards[selected[0]].mask_path = masks[0]
            self.refresh_tree(selected[0])
            self.update_status("Mask assigned to selected card.")
            return
        by_key: dict[str, list[int]] = {}
        for index, card in enumerate(self.cards):
            by_key.setdefault(match_key(card.image_path), []).append(index)
        paired = 0
        for mask in masks:
            matches = by_key.get(match_key(mask), [])
            if len(matches) == 1:
                self.cards[matches[0]].mask_path = mask
                paired += 1
        self.refresh_tree()
        self.update_status(f"Paired {paired} mask(s).")

    def prompt_for_image(self, image: Path, name: str) -> str:
        mode = PROMPT_MODES.get(self.prompt_mode.get(), "sidecar")
        if mode == "sidecar":
            return read_sidecar_prompt(image) or name
        if mode == "filename":
            return name
        if mode == "common":
            return self.common_prompt.get("1.0", "end").strip()
        return ""

    def visible_indices(self) -> list[int]:
        project = self.selected_project()
        topic = self.selected_topic()
        indices: list[int] = []
        for index, card in enumerate(self.cards):
            if project and card.project_name != project:
                continue
            if topic and card.topic_name != topic:
                continue
            indices.append(index)
        return indices

    def selected_indices(self) -> list[int]:
        indices: list[int] = []
        for item in self.tree.selection():
            try:
                indices.append(int(item))
            except ValueError:
                pass
        return [index for index in indices if 0 <= index < len(self.cards)]

    def on_card_selected(self, _event: tk.Event) -> None:
        indices = self.selected_indices()
        if indices:
            self.last_selected_card_ids = {id(self.cards[index]) for index in indices}
        self.load_selected_card()

    def row_values(self, card: CardDraft) -> tuple[str, str, str, str, str, str]:
        prompt = card.prompt.replace("\n", " ")
        if len(prompt) > 80:
            prompt = prompt[:77] + "..."
        return (card.project_name, card.topic_name, card.name, prompt, str(card.image_path), str(card.mask_path or ""))

    def update_tree_row(self, index: int) -> None:
        item_id = str(index)
        if 0 <= index < len(self.cards) and self.tree.exists(item_id):
            self.tree.item(item_id, values=self.row_values(self.cards[index]))

    def sort_cards(self, column: str) -> None:
        selected_cards = {id(self.cards[index]) for index in self.selected_indices()}
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        key_map = {
            "project": lambda card: card.project_name.lower(),
            "topic": lambda card: card.topic_name.lower(),
            "name": lambda card: card.name.lower(),
            "prompt": lambda card: card.prompt.lower(),
            "image": lambda card: str(card.image_path).lower(),
            "mask": lambda card: str(card.mask_path or "").lower(),
        }
        self.cards.sort(key=key_map.get(column, key_map["name"]), reverse=self.sort_reverse)
        self.refresh_tree()
        selection = [str(index) for index, card in enumerate(self.cards) if id(card) in selected_cards and self.tree.exists(str(index))]
        if selection:
            self.tree.selection_set(selection)
            self.tree.focus(selection[0])
            self.load_selected_card()

    def refresh_tree(self, select_index: int | None = None) -> None:
        selection = self.selected_indices()
        self.tree.delete(*self.tree.get_children())
        for index in self.visible_indices():
            self.tree.insert("", "end", iid=str(index), values=self.row_values(self.cards[index]))
        if select_index is not None and self.tree.exists(str(select_index)):
            self.tree.selection_set(str(select_index))
            self.tree.focus(str(select_index))
        elif selection:
            valid = [str(index) for index in selection if self.tree.exists(str(index))]
            if valid:
                self.tree.selection_set(valid)

    def load_selected_card(self) -> None:
        self.editor_loading = True
        indices = self.selected_indices()
        if not indices:
            self.project_label.set("")
            self.topic_label.set("")
            self.card_name.set("")
            self.card_prompt.delete("1.0", "end")
            self.card_prompt.edit_modified(False)
            self.image_label.set("")
            self.mask_label.set("")
            self.editor_loading = False
            return
        card = self.cards[indices[0]]
        self.project_label.set(card.project_name)
        self.topic_label.set(card.topic_name)
        self.card_name.set(card.name)
        self.card_prompt.delete("1.0", "end")
        self.card_prompt.insert("1.0", card.prompt)
        self.card_prompt.edit_modified(False)
        self.image_label.set(str(card.image_path))
        self.mask_label.set(str(card.mask_path or ""))
        self.editor_loading = False

    def on_card_name_changed(self) -> None:
        if self.editor_loading:
            return
        indices = self.selected_indices()
        if indices:
            self.cards[indices[0]].name = self.card_name.get()
            self.update_tree_row(indices[0])

    def on_card_prompt_changed(self, _event: tk.Event) -> None:
        if not self.card_prompt.edit_modified():
            return
        self.card_prompt.edit_modified(False)
        if self.editor_loading:
            return
        indices = self.selected_indices()
        if indices:
            self.cards[indices[0]].prompt = self.card_prompt.get("1.0", "end").strip()
            self.update_tree_row(indices[0])

    def apply_common_to_selected(self) -> None:
        prompt = self.common_prompt.get("1.0", "end").strip()
        indices = self.selected_indices()
        if not indices:
            self.update_status("Select one or more cards first.")
            return
        for index in indices:
            self.cards[index].prompt = prompt
            self.update_tree_row(index)
        self.load_selected_card()
        self.update_status(f"Applied common prompt to {len(indices)} card(s).")

    def apply_common_to_visible(self) -> None:
        prompt = self.common_prompt.get("1.0", "end").strip()
        indices = self.visible_indices()
        for index in indices:
            self.cards[index].prompt = prompt
        self.refresh_tree()
        self.load_selected_card()
        self.update_status(f"Applied common prompt to {len(indices)} visible card(s).")

    def use_sidecars(self) -> None:
        changed = 0
        for index in self.visible_indices():
            prompt = read_sidecar_prompt(self.cards[index].image_path)
            if prompt:
                self.cards[index].prompt = prompt
                changed += 1
        self.refresh_tree()
        self.load_selected_card()
        self.update_status(f"Loaded {changed} sidecar prompt(s).")

    def select_visible_cards(self) -> None:
        visible = [str(index) for index in self.visible_indices() if self.tree.exists(str(index))]
        if visible:
            self.tree.selection_set(visible)
            self.tree.focus(visible[0])
            self.load_selected_card()

    def mark_deleted(self, card: CardDraft) -> None:
        if card.source_item_path:
            self.deleted_item_paths.add(card.source_item_path)

    def remove_selected(self) -> None:
        indices = sorted(self.selected_indices(), reverse=True)
        for index in indices:
            self.mark_deleted(self.cards[index])
            del self.cards[index]
        if indices:
            self.last_selected_card_ids.clear()
        self.refresh_all(select_project=self.selected_project(), select_topic=self.selected_topic())
        self.update_status(f"Removed {len(indices)} card(s).")

    def clear_visible_cards(self) -> None:
        indices = self.visible_indices()
        if not indices:
            return
        if not messagebox.askyesno("Clear visible", "Remove all visible cards from this builder?"):
            return
        for index in sorted(indices, reverse=True):
            self.mark_deleted(self.cards[index])
            del self.cards[index]
        self.last_selected_card_ids.clear()
        self.refresh_all(select_project=self.selected_project(), select_topic=self.selected_topic())
        self.update_status(f"Removed {len(indices)} visible card(s).")

    def clear_mask_for_selected(self) -> None:
        indices = self.selected_indices()
        if not indices:
            self.update_status("Select one or more cards first.")
            return
        for index in indices:
            self.cards[index].mask_path = None
            self.update_tree_row(index)
        self.load_selected_card()
        self.update_status(f"Cleared mask on {len(indices)} card(s).")

    def safe_remove_tree(self, root_dir: Path, target: Path) -> None:
        projects_root = (root_dir / "projects").resolve()
        target = target.resolve()
        try:
            target.relative_to(projects_root)
        except ValueError:
            return
        if target.exists():
            shutil.rmtree(target)

    def save_projects(self) -> None:
        root_dir = Path(self.root_dir.get()).expanduser()
        if not self.projects and not self.cards:
            messagebox.showerror("Nothing to save", "Add a project or image first.")
            return
        if not (root_dir / "nodes.py").exists():
            proceed = messagebox.askyesno("Folder check", "nodes.py was not found in the selected folder. Save projects there anyway?")
            if not proceed:
                return

        self.rebuild_projects_from_cards()
        overwrite = bool(self.overwrite.get())
        use_mask_sequence = self.node_type.get() == "image_mask_sequence"
        used_by_topic: dict[Path, set[str]] = {}
        touched_topics: set[Path] = set()
        active_project_paths: set[Path] = set()
        active_topic_paths: set[Path] = set()
        pending_item_deletes = set(self.deleted_item_paths)

        try:
            for project_name, topics in self.projects.items():
                project_slug = slugify(project_name, "project")
                project_dir = root_dir / "projects" / project_slug
                active_project_paths.add(project_dir.resolve())
                json_write(project_dir / "project.json", {"schema": 1, "name": project_name})
                for topic_name in topics:
                    topic_slug = slugify(topic_name, "topic")
                    topic_dir = project_dir / topic_slug
                    active_topic_paths.add(topic_dir.resolve())
                    touched_topics.add(topic_dir)
                    json_write(topic_dir / "topic.json", {"schema": 1, "name": topic_name})

            saved = 0
            for card in self.cards:
                if not card.image_path.exists():
                    raise RuntimeError(f"Image not found: {card.image_path}")
                project_name = card.project_name.strip() or "Project"
                topic_name = card.topic_name.strip() or "Default"
                project_slug = slugify(project_name, "project")
                topic_slug = slugify(topic_name, "topic")
                project_dir = root_dir / "projects" / project_slug
                topic_dir = project_dir / topic_slug
                used = used_by_topic.setdefault(topic_dir.resolve(), set())
                json_write(project_dir / "project.json", {"schema": 1, "name": project_name})
                json_write(topic_dir / "topic.json", {"schema": 1, "name": topic_name})
                item_name = card.name.strip() or clean_name(card.image_path)
                base_slug = card.item_slug if overwrite and card.item_slug else slugify(item_name, "prompt")
                item_slug = unique_slug(topic_dir, base_slug, overwrite, used)
                item_path = topic_dir / item_slug
                item_path.mkdir(parents=True, exist_ok=True)
                if use_mask_sequence:
                    image_name = save_full_image(card.image_path, item_path / "image.png")
                    mask_name = save_full_image(card.mask_path, item_path / "mask.png") if card.mask_path else None
                else:
                    image_name = save_preview_image(card.image_path, item_path / "preview.png")
                    mask_name = None
                item_id = f"{project_slug}/{topic_slug}/{item_slug}"
                metadata = {
                    "schema": 1,
                    "id": item_id,
                    "project": {"id": project_slug, "name": project_name},
                    "topic": {"id": topic_slug, "name": topic_name},
                    "name": item_name,
                    "prompt": card.prompt.strip(),
                    "image": image_name,
                    "mask": mask_name,
                    "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
                json_write(item_path / "prompt.json", metadata)
                if card.source_item_path and card.source_item_path.resolve() != item_path.resolve():
                    pending_item_deletes.add(card.source_item_path)
                card.project_name = project_name
                card.topic_name = topic_name
                card.item_slug = item_slug
                card.source_item_path = item_path
                touched_topics.add(topic_dir)
                active_project_paths.add(project_dir.resolve())
                active_topic_paths.add(topic_dir.resolve())
                saved += 1

            for item_path in pending_item_deletes:
                self.safe_remove_tree(root_dir, item_path)
            for topic_path in self.deleted_topic_paths:
                if topic_path.resolve() not in active_topic_paths:
                    self.safe_remove_tree(root_dir, topic_path)
            for project_path in self.deleted_project_paths:
                if project_path.resolve() not in active_project_paths:
                    self.safe_remove_tree(root_dir, project_path)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
            self.update_status("Save failed.")
            return

        self.deleted_item_paths.clear()
        self.deleted_topic_paths.clear()
        self.deleted_project_paths.clear()
        self.refresh_all(select_project=self.selected_project(), select_topic=self.selected_topic())
        target_text = "\n".join(str(path) for path in sorted(touched_topics, key=lambda item: str(item).lower())[:8])
        extra = "" if len(touched_topics) <= 8 else f"\n...and {len(touched_topics) - 8} more topic(s)"
        self.update_status(f"Saved {saved} card(s) across {len(touched_topics)} topic(s).")
        messagebox.showinfo("Done", f"Saved {saved} card(s) across {len(touched_topics)} topic(s).\n\n{target_text}{extra}")


def main() -> None:
    if TkinterDnD:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = PromptProjectApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
