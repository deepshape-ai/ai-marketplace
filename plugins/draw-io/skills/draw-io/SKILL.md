---
name: draw-io
description: 生成高质量 draw.io 图表（架构图、流程图、时序图等）并导出 PNG。通过直接编辑 XML 创建 .drawio 文件。当用户需要：(1) 创建架构图、流程图、决策图、时序图等示意图，(2) 生成 .drawio 或 draw.io XML 文件，(3) 将图表导出为 PNG 图片，(4) 修改或优化现有 draw.io 图表时使用。
---

# draw.io Diagram Generation

## Workflow

1. Understand diagram requirements and plan layout (positions, connections)
2. Generate XML following the core rules below
3. Save XML to `output/assets/[name].drawio`
4. Export PNG: `drawio -x -f png -s 2 -t -o output/assets/[name].png output/assets/[name].drawio`
5. Validate against [CHECKLIST.md](CHECKLIST.md) before delivery

Output directory: `output/assets/`, English filenames, no spaces.

## Core Rules

### 1. Font Settings

```xml
<mxGraphModel defaultFontFamily="Noto Sans SC" page="0" ...>
<!-- Every text element's style MUST include fontFamily -->
<mxCell style="text;fontFamily=Noto Sans SC;fontSize=18;..." />
```

### 2. Z-Order: Edges Before Vertices

```xml
<root>
  <mxCell id="0" />
  <mxCell id="1" parent="0" />
  <!-- Declare edges FIRST (renders at back) -->
  <mxCell id="arrow1" edge="1" ... />
  <!-- Declare vertices AFTER (renders in front) -->
  <mxCell id="box1" vertex="1" ... />
</root>
```

### 3. Label-Arrow Spacing >= 20px

Label Y-coordinate must differ from arrow line by at least 20px to avoid overlap.

### 4. Chinese Text Width

Allocate 20-30px per Chinese character to prevent unwanted line breaks.

```xml
<!-- 8 chars x 25px = 200px minimum -->
<mxCell id="title" value="素材智能检索系统">
  <mxGeometry width="220" height="40" />
</mxCell>
```

## Reference Files

- **[REFERENCE.md](REFERENCE.md)** — Complete XML structure reference (element types, style properties, predefined shapes, coordinate system). Read when composing XML.
- **[EXAMPLES.md](EXAMPLES.md)** — 5 production-ready examples (flowchart, architecture, decision, sequence, titled diagram) with color schemes. Use as templates for new diagrams.
- **[CHECKLIST.md](CHECKLIST.md)** — Pre-export validation checklist. Run through before every PNG export.

