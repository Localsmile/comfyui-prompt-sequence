from __future__ import annotations

import hashlib
import json
import random
import re
import secrets
import shutil
import unicodedata
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = PACKAGE_DIR / "projects"
MAX_PREVIEW_SIDE = 512
MAX_JOIN_INPUTS = 32
SAFE_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")


def _split_prompt_lines(prompts: str) -> list[str]:
    lines = []
    for line in str(prompts or "").splitlines():
        text = line.strip()
        if text:
            lines.append(text)
    return lines or [""]


def _as_scalar(value: Any, default: Any = None) -> Any:
    if isinstance(value, list):
        if not value:
            return default
        return value[0]
    return default if value is None else value


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(_as_scalar(value, default))
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    scalar = _as_scalar(value, default)
    if isinstance(scalar, bool):
        return scalar
    if isinstance(scalar, str):
        return scalar.strip().lower() in {"1", "true", "yes", "on"}
    return bool(scalar)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _stable_hash(value: str, size: int = 8) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:size]


def _slugify(value: str, fallback_prefix: str) -> str:
    raw = str(value or "").strip()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", ascii_text).strip("-._").lower()
    slug = re.sub(r"-{2,}", "-", slug)[:80].strip("-._")
    if slug:
        return slug
    return f"{fallback_prefix}-{_stable_hash(raw or fallback_prefix)}"


def _safe_segment(value: str) -> bool:
    return bool(SAFE_SEGMENT_RE.match(str(value or "")))


def _safe_item_path(project: str, topic: str, item: str) -> Path | None:
    if not (_safe_segment(project) and _safe_segment(topic) and _safe_segment(item)):
        return None
    path = (PROJECTS_DIR / project / topic / item).resolve()
    try:
        path.relative_to(PROJECTS_DIR.resolve())
    except ValueError:
        return None
    return path


def _parse_item_id(item_id: str) -> tuple[str, str, str] | None:
    parts = str(item_id or "").split("/")
    if len(parts) != 3:
        return None
    if not all(_safe_segment(part) for part in parts):
        return None
    return parts[0], parts[1], parts[2]


def _json_load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _json_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ordered_values(values: list[str], mode: str, seed: int) -> list[str]:
    ordered = list(values) or [""]
    if mode == "random" and len(ordered) > 1:
        rng_seed = seed if seed >= 0 else secrets.randbits(64)
        random.Random(rng_seed).shuffle(ordered)
    return ordered


def _select_values(values: list[Any], mode: str, seed: int, max_items: int) -> list[Any]:
    selected = list(values)
    if mode == "random" and len(selected) > 1:
        rng_seed = seed if seed >= 0 else secrets.randbits(64)
        random.Random(rng_seed).shuffle(selected)
    limit = max(0, int(max_items))
    if limit:
        selected = selected[: min(limit, len(selected))]
    return selected or [""]


def _decode_separator(separator: str) -> str:
    text = str(separator or "")
    return text.replace("\\n", "\n").replace("/n", "\n").replace("\\t", "\t")


def _clean_prompt_tag(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,")


def _split_prompt_tags(value: str) -> list[str]:
    tags: list[str] = []
    buffer: list[str] = []
    quote_char = ""
    escaped = False
    round_depth = 0
    square_depth = 0
    brace_depth = 0
    angle_depth = 0

    def flush() -> None:
        tag = _clean_prompt_tag("".join(buffer))
        buffer.clear()
        if tag:
            tags.append(tag)

    for char in str(value or "").replace("\r\n", "\n").replace("\r", "\n"):
        if quote_char:
            buffer.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote_char:
                quote_char = ""
            continue

        if char in {'"', "'"}:
            quote_char = char
            buffer.append(char)
            continue

        if char == "(":
            round_depth += 1
        elif char == ")" and round_depth:
            round_depth -= 1
        elif char == "[":
            square_depth += 1
        elif char == "]" and square_depth:
            square_depth -= 1
        elif char == "{":
            brace_depth += 1
        elif char == "}" and brace_depth:
            brace_depth -= 1
        elif char == "<":
            angle_depth += 1
        elif char == ">" and angle_depth:
            angle_depth -= 1

        if (
            char in {",", "\n"}
            and round_depth == 0
            and square_depth == 0
            and brace_depth == 0
            and angle_depth == 0
        ):
            flush()
        else:
            buffer.append(char)

    flush()
    return tags


def _parse_selection(selection_json: str) -> dict[str, Any]:
    try:
        data = json.loads(selection_json or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    selected = data.get("selected", [])
    if not isinstance(selected, list):
        selected = []
    data["selected"] = [str(item) for item in selected]
    return data


def _load_selected_asset_prompts(selection_json: str) -> list[str]:
    selection = _parse_selection(selection_json)
    prompts: list[str] = []
    for item_id in selection["selected"]:
        parts = item_id.split("/")
        if len(parts) != 3:
            continue
        item_path = _safe_item_path(parts[0], parts[1], parts[2])
        if item_path is None:
            continue
        metadata = _json_load(item_path / "prompt.json", {})
        if not isinstance(metadata, dict):
            continue
        prompt = str(metadata.get("prompt") or metadata.get("name") or "").strip()
        if prompt:
            prompts.append(prompt)
    return prompts


def _load_selected_asset_records(selection_json: str) -> list[dict[str, Any]]:
    selection = _parse_selection(selection_json)
    records: list[dict[str, Any]] = []
    for item_id in selection["selected"]:
        parsed_item_id = _parse_item_id(item_id)
        if not parsed_item_id:
            continue
        item_path = _safe_item_path(*parsed_item_id)
        if item_path is None:
            continue
        metadata = _json_load(item_path / "prompt.json", {})
        if not isinstance(metadata, dict):
            continue
        records.append({"id": item_id, "path": item_path, "metadata": metadata})
    return records


def _library_signature(selection_json: str) -> str:
    selection = _parse_selection(selection_json)
    digest = hashlib.sha1()
    digest.update(json.dumps(selection, sort_keys=True).encode("utf-8"))
    for item_id in selection["selected"]:
        parts = item_id.split("/")
        if len(parts) != 3:
            continue
        item_path = _safe_item_path(parts[0], parts[1], parts[2])
        metadata_path = item_path / "prompt.json" if item_path else None
        if metadata_path and metadata_path.exists():
            stat = metadata_path.stat()
            digest.update(str(metadata_path).encode("utf-8"))
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
            digest.update(str(stat.st_size).encode("ascii"))
    return digest.hexdigest()


def _list_asset_library() -> dict[str, Any]:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    projects: list[dict[str, Any]] = []

    for project_dir in sorted([p for p in PROJECTS_DIR.iterdir() if p.is_dir()]):
        if not _safe_segment(project_dir.name):
            continue
        project_meta = _json_load(project_dir / "project.json", {})
        project_name = str(project_meta.get("name") or project_dir.name)
        topics: list[dict[str, Any]] = []

        for topic_dir in sorted([p for p in project_dir.iterdir() if p.is_dir()]):
            if not _safe_segment(topic_dir.name):
                continue
            topic_meta = _json_load(topic_dir / "topic.json", {})
            topic_name = str(topic_meta.get("name") or topic_dir.name)
            items: list[dict[str, Any]] = []

            for item_dir in sorted([p for p in topic_dir.iterdir() if p.is_dir()]):
                if not _safe_segment(item_dir.name):
                    continue
                metadata = _json_load(item_dir / "prompt.json", {})
                if not isinstance(metadata, dict):
                    continue
                image_name = metadata.get("image")
                mask_name = metadata.get("mask")
                has_image = bool(image_name and (item_dir / str(image_name)).exists())
                has_mask = bool(mask_name and (item_dir / str(mask_name)).exists())
                item_id = f"{project_dir.name}/{topic_dir.name}/{item_dir.name}"
                item = {
                    "id": item_id,
                    "name": str(metadata.get("name") or item_dir.name),
                    "prompt": str(metadata.get("prompt") or ""),
                    "image": image_name if has_image else None,
                    "mask": mask_name if has_mask else None,
                    "image_url": (
                        "/prompt_sequence/assets/image"
                        f"?project={quote(project_dir.name)}"
                        f"&topic={quote(topic_dir.name)}"
                        f"&item={quote(item_dir.name)}"
                    )
                    if has_image
                    else None,
                    "mask_url": (
                        "/prompt_sequence/assets/mask"
                        f"?project={quote(project_dir.name)}"
                        f"&topic={quote(topic_dir.name)}"
                        f"&item={quote(item_dir.name)}"
                    )
                    if has_mask
                    else None,
                    "updated_at": metadata.get("updated_at"),
                }
                items.append(item)

            items.sort(key=lambda value: value["name"].lower())
            topics.append(
                {
                    "id": topic_dir.name,
                    "name": topic_name,
                    "items": items,
                }
            )

        topics.sort(key=lambda value: value["name"].lower())
        projects.append(
            {
                "id": project_dir.name,
                "name": project_name,
                "topics": topics,
            }
        )

    projects.sort(key=lambda value: value["name"].lower())
    return {"schema": 1, "projects": projects}


def _save_preview_image(raw: bytes, output_path: Path) -> str:
    try:
        from PIL import Image, ImageOps
    except Exception as exc:
        raise RuntimeError("Pillow is required to resize prompt preview images.") from exc

    with Image.open(BytesIO(raw)) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        image.thumbnail((MAX_PREVIEW_SIDE, MAX_PREVIEW_SIDE), resampling)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG", optimize=True)
    return output_path.name


def _save_full_image(raw: bytes, output_path: Path) -> str:
    try:
        from PIL import Image, ImageOps
    except Exception as exc:
        raise RuntimeError("Pillow is required to save prompt images.") from exc

    with Image.open(BytesIO(raw)) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG", optimize=True)
    return output_path.name


def _load_image_tensor(image_path: Path):
    try:
        import numpy as np
        import torch
        from PIL import Image, ImageOps
    except Exception as exc:
        raise RuntimeError("Pillow, numpy, and torch are required to load images.") from exc

    with Image.open(image_path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode == "I":
            image = image.point(lambda value: value * (1 / 255))
        alpha = None
        if "A" in image.getbands():
            alpha = image.getchannel("A")
        rgb_image = image.convert("RGB")
        image_array = np.array(rgb_image).astype(np.float32) / 255.0
        image_tensor = torch.from_numpy(image_array)[None,]
        if alpha is not None:
            mask_array = 1.0 - (np.array(alpha).astype(np.float32) / 255.0)
            alpha_mask = torch.from_numpy(mask_array)[None,]
        else:
            alpha_mask = torch.zeros(
                (1, rgb_image.height, rgb_image.width),
                dtype=torch.float32,
            )
    return image_tensor, alpha_mask


def _load_mask_tensor(mask_path: Path):
    try:
        import numpy as np
        import torch
        from PIL import Image, ImageOps
    except Exception as exc:
        raise RuntimeError("Pillow, numpy, and torch are required to load masks.") from exc

    with Image.open(mask_path) as mask:
        mask = ImageOps.exif_transpose(mask)
        mask = mask.convert("L")
        mask_array = np.array(mask).astype(np.float32) / 255.0
    return torch.from_numpy(mask_array)[None,]


def _blank_image_and_mask():
    try:
        import torch
    except Exception as exc:
        raise RuntimeError("torch is required to create blank image outputs.") from exc
    return (
        torch.zeros((1, 1, 1, 3), dtype=torch.float32),
        torch.zeros((1, 1, 1), dtype=torch.float32),
    )


def _asset_record_to_outputs(record: dict[str, Any]):
    metadata = record["metadata"]
    item_path = record["path"]
    image_name = str(metadata.get("image") or "")
    mask_name = str(metadata.get("mask") or "")

    image_path = item_path / image_name if image_name else None
    if image_path and image_path.exists():
        image_tensor, alpha_mask = _load_image_tensor(image_path)
    else:
        image_tensor, alpha_mask = _blank_image_and_mask()

    mask_path = item_path / mask_name if mask_name else None
    if mask_path and mask_path.exists():
        mask_tensor = _load_mask_tensor(mask_path)
    else:
        mask_tensor = alpha_mask

    return image_tensor, str(metadata.get("prompt") or ""), mask_tensor


class PromptSequenceText:
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "build"
    CATEGORY = "prompt sequence"
    OUTPUT_IS_LIST = (True,)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompts": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Each non-empty line becomes one prompt item.",
                    },
                ),
                "mode": (
                    ["sequential", "random"],
                    {
                        "default": "sequential",
                        "tooltip": "sequential: output top to bottom. random: shuffle before output.",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": -1,
                        "min": -1,
                        "max": 2**63 - 1,
                        "tooltip": "For random mode: -1 makes a new order each queue; a fixed value repeats the same order.",
                    },
                ),
                "max_items": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 10000,
                        "step": 1,
                        "tooltip": "0 outputs all available prompts. A positive value outputs up to that many prompts.",
                    },
                ),
            }
        }

    @classmethod
    def IS_CHANGED(cls, prompts: str, mode: str, seed: int, max_items: int):
        if mode == "random" and int(seed) < 0:
            return float("NaN")
        payload = {
            "prompts": prompts,
            "mode": mode,
            "seed": int(seed),
            "max_items": _as_int(max_items, 0),
        }
        return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def build(self, prompts: str, mode: str, seed: int, max_items: int):
        return (_select_values(_split_prompt_lines(prompts), mode, int(seed), _as_int(max_items, 0)),)


class PromptSequenceCombo:
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "build"
    CATEGORY = "prompt sequence"
    INPUT_IS_LIST = True
    OUTPUT_IS_LIST = (True,)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompts": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Used only when source is not connected. Hidden and ignored while source is connected.",
                    },
                ),
                "mode": (
                    ["sequential", "random"],
                    {
                        "default": "sequential",
                        "tooltip": "sequential: keep source order. random: shuffle before max_items is applied.",
                    },
                ),
                "max_items": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 10000,
                        "step": 1,
                        "tooltip": "0 outputs all available prompts. A positive value outputs up to that many prompts.",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": -1,
                        "min": -1,
                        "max": 2**63 - 1,
                        "tooltip": "For random mode: -1 makes a new order each queue; a fixed value repeats the same order.",
                    },
                ),
            },
            "optional": {
                "source": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "When connected, this source list replaces the local prompt box.",
                    },
                ),
            },
        }

    @classmethod
    def IS_CHANGED(cls, prompts, mode, max_items, seed, source=None):
        mode_value = str(_as_scalar(mode, "sequential"))
        seed_value = _as_int(seed, -1)
        if mode_value == "random" and seed_value < 0:
            return float("NaN")
        payload = {
            "prompts": prompts,
            "mode": mode,
            "max_items": max_items,
            "seed": seed,
            "source": source,
        }
        return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def build(self, prompts, mode, max_items, seed, source=None):
        mode_value = str(_as_scalar(mode, "sequential"))
        max_items_value = _as_int(max_items, 0)
        seed_value = _as_int(seed, -1)

        if source is None:
            values = _split_prompt_lines(str(_as_scalar(prompts, "")))
        elif isinstance(source, list):
            values = []
            for item in source:
                if isinstance(item, str) and "\n" in item:
                    values.extend(_split_prompt_lines(item))
                else:
                    values.append(str(item or ""))
            values = values or [""]
        else:
            values = _split_prompt_lines(str(source))

        return (_select_values(values, mode_value, seed_value, max_items_value),)


class PromptSequenceJoin:
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "join"
    CATEGORY = "prompt sequence"
    INPUT_IS_LIST = True
    OUTPUT_IS_LIST = (True,)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_count": (
                    "INT",
                    {
                        "default": 2,
                        "min": 1,
                        "max": MAX_JOIN_INPUTS,
                        "step": 1,
                        "tooltip": "Number of visible text inputs. Click update inputs after changing it.",
                    },
                ),
                "separator": (
                    "STRING",
                    {
                        "default": ", ",
                        "multiline": False,
                        "tooltip": "Text inserted between parts. Use \\n or /n for a newline, including ,\\n or ,/n.",
                    },
                ),
                "skip_empty": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "When enabled, blank missing parts are removed before joining, including their separator.",
                    },
                ),
                "length_policy": (
                    ["longest", "shortest"],
                    {
                        "default": "longest",
                        "tooltip": "longest: emit up to the longest input. shortest: stop at the shortest connected input.",
                    },
                ),
                "missing_policy": (
                    ["blank", "repeat_last"],
                    {
                        "default": "blank",
                        "tooltip": "blank: missing values become empty text. repeat_last: reuse the shorter input's final value.",
                    },
                ),
                "max_items": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 10000,
                        "step": 1,
                        "tooltip": "0 keeps all joined prompts. A positive value limits the final joined output count.",
                    },
                ),
            },
            "optional": {
                f"text_{index}": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Connect a prompt sequence. Missing values follow missing_policy.",
                    },
                )
                for index in range(1, MAX_JOIN_INPUTS + 1)
            },
        }

    def join(
        self,
        input_count: int,
        separator: str,
        skip_empty: bool,
        length_policy: str,
        missing_policy: str,
        max_items: int,
        **kwargs,
    ):
        count = max(1, min(MAX_JOIN_INPUTS, _as_int(input_count, 2)))
        sep = _decode_separator(str(_as_scalar(separator, ", ")))
        skip = _as_bool(skip_empty, True)
        length_mode = str(_as_scalar(length_policy, "longest"))
        missing_mode = str(_as_scalar(missing_policy, "blank"))
        max_count = _as_int(max_items, 0)

        streams = []
        for index in range(1, count + 1):
            values = ["" if value is None else str(value) for value in _as_list(kwargs.get(f"text_{index}"))]
            streams.append(values)

        connected_lengths = [len(values) for values in streams if values]
        if not connected_lengths:
            return ([""],)

        if length_mode == "shortest":
            output_count = min(connected_lengths)
        else:
            output_count = max(connected_lengths)

        if max_count > 0:
            output_count = min(output_count, max_count)
        output_count = max(1, output_count)

        joined_values = []
        for item_index in range(output_count):
            parts = []
            for values in streams:
                if item_index < len(values):
                    part = values[item_index]
                elif missing_mode == "repeat_last" and values:
                    part = values[-1]
                else:
                    part = ""
                if not skip or part.strip():
                    parts.append(part)
            joined_values.append(sep.join(parts))

        return (joined_values,)


class PromptTagFormatter:
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "format_prompt"
    CATEGORY = "prompt sequence"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "tag1\ntag2,tag3\n\ntag4",
                        "tooltip": "Normalizes line breaks and commas into one comma-space-separated tag line.",
                    },
                ),
            }
        }

    def format_prompt(self, text: str):
        return (", ".join(_split_prompt_tags(text)),)


class PromptImageSequence:
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "build"
    CATEGORY = "prompt sequence"
    OUTPUT_IS_LIST = (True,)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "selection_json": (
                    "STRING",
                    {
                        "default": "{}",
                        "multiline": False,
                        "tooltip": "Hidden picker state. Use the thumbnail grid instead of editing this manually.",
                    },
                ),
                "mode": (
                    ["sequential", "random"],
                    {
                        "default": "sequential",
                        "tooltip": "sequential: use checked cards in order. random: shuffle checked cards before output.",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": -1,
                        "min": -1,
                        "max": 2**63 - 1,
                        "tooltip": "For random mode: -1 makes a new order each queue; a fixed value repeats the same order.",
                    },
                ),
                "max_items": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 10000,
                        "step": 1,
                        "tooltip": "0 outputs all checked prompts. A positive value outputs up to that many prompts.",
                    },
                ),
            }
        }

    @classmethod
    def IS_CHANGED(
        cls,
        selection_json: str,
        mode: str,
        seed: int,
        max_items: int,
    ):
        if mode == "random" and int(seed) < 0:
            return float("NaN")
        payload = {
            "selection": selection_json,
            "mode": mode,
            "seed": int(seed),
            "max_items": _as_int(max_items, 0),
            "library": _library_signature(selection_json),
        }
        return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def build(
        self,
        selection_json: str,
        mode: str,
        seed: int,
        max_items: int,
    ):
        prompts = _load_selected_asset_prompts(selection_json)
        if not prompts:
            prompts = [""]
        return (_select_values(prompts, mode, int(seed), _as_int(max_items, 0)),)


class PromptImageMaskSequence:
    RETURN_TYPES = ("STRING", "IMAGE", "MASK")
    RETURN_NAMES = ("prompt", "image", "mask")
    FUNCTION = "build"
    CATEGORY = "prompt sequence"
    OUTPUT_IS_LIST = (True, True, True)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "selection_json": (
                    "STRING",
                    {
                        "default": "{}",
                        "multiline": False,
                        "tooltip": "Hidden picker state. Use the thumbnail grid instead of editing this manually.",
                    },
                ),
                "mode": (
                    ["sequential", "random"],
                    {
                        "default": "sequential",
                        "tooltip": "sequential: use checked cards in order. random: shuffle checked cards before output.",
                    },
                ),
                "seed": (
                    "INT",
                    {
                        "default": -1,
                        "min": -1,
                        "max": 2**63 - 1,
                        "tooltip": "For random mode: -1 makes a new order each queue; a fixed value repeats the same order.",
                    },
                ),
                "max_items": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 10000,
                        "step": 1,
                        "tooltip": "0 outputs all checked records. A positive value outputs up to that many records.",
                    },
                ),
            }
        }

    @classmethod
    def IS_CHANGED(cls, selection_json: str, mode: str, seed: int, max_items: int):
        if mode == "random" and int(seed) < 0:
            return float("NaN")
        payload = {
            "selection": selection_json,
            "mode": mode,
            "seed": int(seed),
            "max_items": _as_int(max_items, 0),
            "library": _library_signature(selection_json),
        }
        return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def build(self, selection_json: str, mode: str, seed: int, max_items: int):
        records = _load_selected_asset_records(selection_json)
        records = _select_values(records, mode, int(seed), _as_int(max_items, 0))
        images = []
        prompts = []
        masks = []

        if not records or records == [""]:
            image, mask = _blank_image_and_mask()
            return ([""], [image], [mask])

        for record in records:
            image, prompt, mask = _asset_record_to_outputs(record)
            images.append(image)
            prompts.append(prompt)
            masks.append(mask)
        return (prompts, images, masks)


NODE_CLASS_MAPPINGS = {
    "ComfyUIPromptSequenceText": PromptSequenceText,
    "ComfyUIPromptSequenceCombo": PromptSequenceCombo,
    "ComfyUIPromptSequenceJoin": PromptSequenceJoin,
    "ComfyUIPromptTagFormatter": PromptTagFormatter,
    "ComfyUIPromptImageSequence": PromptImageSequence,
    "ComfyUIPromptImageMaskSequence": PromptImageMaskSequence,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ComfyUIPromptSequenceText": "Prompt Sequence Text",
    "ComfyUIPromptSequenceCombo": "Prompt Sequence Filter",
    "ComfyUIPromptSequenceJoin": "Prompt Sequence Join",
    "ComfyUIPromptTagFormatter": "Prompt Tag Formatter",
    "ComfyUIPromptImageSequence": "Prompt Image Sequence",
    "ComfyUIPromptImageMaskSequence": "Prompt Image Mask Sequence",
}


_ROUTES_REGISTERED = False


def register_routes() -> bool:
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return True

    try:
        from aiohttp import web
        from server import PromptServer
    except Exception:
        return False

    routes = PromptServer.instance.routes

    @routes.get("/prompt_sequence/assets")
    async def list_assets(_request):
        return web.json_response(_list_asset_library())

    @routes.get("/prompt_sequence/assets/image")
    async def get_asset_image(request):
        project = request.query.get("project", "")
        topic = request.query.get("topic", "")
        item = request.query.get("item", "")
        item_path = _safe_item_path(project, topic, item)
        if item_path is None:
            raise web.HTTPBadRequest(reason="Invalid asset path.")

        metadata = _json_load(item_path / "prompt.json", {})
        image_name = str(metadata.get("image") or "")
        image_path = item_path / image_name if image_name else None
        if not image_path or not image_path.exists():
            raise web.HTTPNotFound(reason="Prompt image not found.")
        return web.FileResponse(image_path)

    @routes.get("/prompt_sequence/assets/mask")
    async def get_asset_mask(request):
        project = request.query.get("project", "")
        topic = request.query.get("topic", "")
        item = request.query.get("item", "")
        item_path = _safe_item_path(project, topic, item)
        if item_path is None:
            raise web.HTTPBadRequest(reason="Invalid asset path.")

        metadata = _json_load(item_path / "prompt.json", {})
        mask_name = str(metadata.get("mask") or "")
        mask_path = item_path / mask_name if mask_name else None
        if not mask_path or not mask_path.exists():
            raise web.HTTPNotFound(reason="Prompt mask not found.")
        return web.FileResponse(mask_path)

    @routes.post("/prompt_sequence/assets")
    async def save_asset(request):
        data = await request.post()
        item_id = str(data.get("id") or "").strip()
        project_name = str(data.get("project") or "").strip()
        topic_name = str(data.get("topic") or "").strip()
        item_name = str(data.get("name") or "").strip()
        prompt = str(data.get("prompt") or "").strip()
        preserve_image = str(data.get("preserve_image") or "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        if not project_name or not topic_name or not item_name:
            raise web.HTTPBadRequest(reason="Project, topic, and name are required.")

        parsed_item_id = _parse_item_id(item_id)
        if parsed_item_id:
            project_slug, topic_slug, item_slug = parsed_item_id
        else:
            project_slug = _slugify(project_name, "project")
            topic_slug = _slugify(topic_name, "topic")
            item_slug = _slugify(item_name, "prompt")
        item_path = _safe_item_path(project_slug, topic_slug, item_slug)
        if item_path is None:
            raise web.HTTPBadRequest(reason="Invalid generated asset path.")

        project_dir = PROJECTS_DIR / project_slug
        topic_dir = project_dir / topic_slug
        item_path.mkdir(parents=True, exist_ok=True)
        _json_write(project_dir / "project.json", {"schema": 1, "name": project_name})
        _json_write(topic_dir / "topic.json", {"schema": 1, "name": topic_name})

        existing = _json_load(item_path / "prompt.json", {})
        image_name = existing.get("image") if isinstance(existing, dict) else None
        mask_name = existing.get("mask") if isinstance(existing, dict) else None
        image_field = data.get("image")
        if getattr(image_field, "file", None):
            raw = image_field.file.read()
            if raw:
                image_name = (
                    _save_full_image(raw, item_path / "image.png")
                    if preserve_image
                    else _save_preview_image(raw, item_path / "preview.png")
                )

        mask_field = data.get("mask")
        if getattr(mask_field, "file", None):
            raw = mask_field.file.read()
            if raw:
                mask_name = _save_full_image(raw, item_path / "mask.png")

        item_id = f"{project_slug}/{topic_slug}/{item_slug}"
        metadata = {
            "schema": 1,
            "id": item_id,
            "project": {"id": project_slug, "name": project_name},
            "topic": {"id": topic_slug, "name": topic_name},
            "name": item_name,
            "prompt": prompt,
            "image": image_name,
            "mask": mask_name,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        _json_write(item_path / "prompt.json", metadata)
        return web.json_response({"ok": True, "item": metadata, "library": _list_asset_library()})

    @routes.delete("/prompt_sequence/assets")
    async def delete_asset(request):
        item_id = request.query.get("id", "")
        parsed_item_id = _parse_item_id(item_id)
        if not parsed_item_id:
            raise web.HTTPBadRequest(reason="Invalid asset id.")

        item_path = _safe_item_path(*parsed_item_id)
        if item_path is None:
            raise web.HTTPBadRequest(reason="Invalid asset path.")
        if not item_path.exists():
            raise web.HTTPNotFound(reason="Prompt asset not found.")

        shutil.rmtree(item_path)
        return web.json_response({"ok": True, "library": _list_asset_library()})

    _ROUTES_REGISTERED = True
    return True
