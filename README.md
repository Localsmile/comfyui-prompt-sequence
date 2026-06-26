# ComfyUI Prompt Sequence

ComfyUI custom nodes for running prompt sequences from one queue.
Designed for simplicity, these nodes let you run sequences easily without building complicated workflows.


## Install

Place this folder in `ComfyUI/custom_nodes/` and restart ComfyUI.

```text
ComfyUI/
  custom_nodes/
    comfyu-prompt-sequence/
```

## Nodes

### Prompt Sequence Text

Outputs one text list from a multiline prompt box.

- each non-empty line becomes one prompt item
- `mode=sequential`: top to bottom
- `mode=random`: shuffled order
- `seed=-1`: new random order each queue

### Prompt Sequence Combo

Limits or shuffles a prompt sequence.

- unconnected: uses its own multiline prompt box
- connected: uses the connected `source` list and hides the local prompt box
- `mode=random`: shuffles before `max_items` is applied
- `seed=-1`: new random order each queue
- `seed>=0`: repeat the same random order
- `max_items=0`: output all available prompts
- `max_items>0`: output up to that many prompts

### Prompt Sequence Join

Joins multiple prompt sequences into one text list.

- starts with 2 text inputs
- change `input_count`, then click `update inputs`
- `separator` supports `\n`, `/n`, `,\n`, and `,/n`
- default policy is `length_policy=longest` and `missing_policy=blank`

Example with default policy:

```text
A: a1, a2, a3, a4
B: b1, b2

Output:
a1, b1
a2, b2
a3
a4
```

Use `missing_policy=repeat_last` if you want shorter inputs to repeat their final value.

### Prompt Tag Formatter

Normalizes pasted tag text into one comma-space-separated line.

```text
tag1
tag2,tag3

tag4
```

becomes:

```text
tag1, tag2, tag3, tag4
```

### Prompt Image Sequence

Stores prompt cards with preview images and outputs checked prompts as a text list.

- project/topic/card library
- square thumbnail grid
- hover card to view prompt text
- right-click card to edit or delete
- preview image is resized to max 512 px

### Prompt Image Mask Sequence

Stores prompt cards with source images and optional masks.

- outputs `STRING`, `IMAGE`, `MASK`
- prompt may be empty
- square thumbnail grid with full-image letterboxing
- image is saved without resizing
- optional mask upload

## Example Workflow

Import:

```text
examples/basic_prompt_sequence_workflow.json
```

Minimal graph:

```text
Prompt Sequence Text -> Prompt Sequence Combo -> Prompt Sequence Join
Prompt Sequence Text -> Prompt Sequence Combo -> Prompt Sequence Join
Prompt Image Mask Sequence -> Prompt Sequence Join
```

Connect the final text output to `CLIP Text Encode`.

## Library Storage

Cards are stored inside this custom node folder:

```text
projects/
  project-id/
    project.json
    topic-id/
      topic.json
      prompt-id/
        prompt.json
        preview.png
        image.png
        mask.png
```

Copy this custom node folder to share the stored library with a workflow.
