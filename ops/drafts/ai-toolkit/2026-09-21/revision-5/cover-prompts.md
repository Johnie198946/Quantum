# 《用 Gemini Notebook 把一份长 PDF 变成可核对的学习笔记》封面生成规格

## 书架封面（竖版）

**用途**：书架卡片；不能依赖小字传达信息。

**提示词**：

> Editorial book cover illustration for a beginner Chinese AI tools field guide about turning one long PDF into trustworthy study notes with source citations. A warm desk scene viewed slightly from above: one open PDF document, a clean notebook, three color-coded citation tabs connected by thin lines, and a small friendly AI spark organizing information. Calm cobalt blue, cream, and coral palette, tactile paper-cut editorial style, clear single focal point, generous negative space at top for a Chinese title added later, no readable text, no logos, no app interface, no product branding, premium publishing design.

**目标尺寸/比例**：竖版 9:16，至少 1440×2560。

## 阅读页封面（横版）

**用途**：打开文章后位于标题下方；必须是独立构图，不从竖版机械裁切。

**提示词**：

> Wide editorial hero illustration for a step-by-step beginner guide: a long PDF on the left flows through a gentle AI-assisted path into three verified study cards on the right, each connected back to highlighted source passages with visible citation lines. Show the visual idea of upload, ask precise questions, click citations, correct notes, and export a final checklist. Calm cobalt blue, cream, and coral palette, modern paper-cut infographic style, welcoming to non-technical readers, spacious center composition, no readable text, no logos, no branded UI, 16:9.

**目标尺寸/比例**：横版 16:9，至少 2560×1440。

## 统一验收

- 主旨必须能看出“长文档 → 笔记 → 回到引用核对”，而不是泛化的机器人或大脑图。
- 不在模型图片中生成中文标题，避免错字；标题由产品 UI 叠加。
- 不使用 Gemini、Google、NotebookLM 标志或界面截图。
- 两张图色彩和材质一致，但构图不同。
- 记录模型、提示词、生成时间、原始文件 SHA-256、最终文件 SHA-256。

## 本次生成结果

`GENERATED`：已通过 Codex 内置 `image_generation` 生成并人工目视验收：

- `assets/shelf-cover.png`：1440×2560，SHA-256 `c51b9ebe03a646d9537192ba2d579b6552e6850dcf2c7727ca63b32f7b1c1f12`。
- `assets/reader-cover.png`：2560×1440，SHA-256 `f0a46ec59ffafa6f538bb8ebeea5451969c62ac98ae43e94c590ad9085d7df58`。
- `assets/image-manifest.json`：记录提示词、生成时间、后端、尺寸、hash 与验收结果。

两张图片均为原生目标比例和独立构图；未发现可读文字、Logo、品牌 UI 或水印。图片资产已进入修订包，但尚未接入书架/阅读页 API，也未发布。
