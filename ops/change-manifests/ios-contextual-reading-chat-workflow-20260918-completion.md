# Completion Manifest

- task_id: `ios-contextual-reading-chat-workflow-20260918`
- goal: 重构工作流详情、长文阅读分段、书籍/笔记选词提问与批注，并让工作流及知识入口直接显示在 Chat 消息中；补充年轻清新的章节插图、低密度排版、中英文阅读操作、原文批注标记、同页选词问答、独立公式卡、富文本行内数学符号、学生笔记编辑器、Chat 保存笔记四阶段流程，以及旅行笔记概览/日程/地点/检查四态；保持现有后端协议。
- status: `TESTED`

## Changed files

- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Services/MarkdownBlockParser.swift`
- `ios/AIPlatformApp/Views/Chat/Cards/MarkdownCards.swift`
- `ios/AIPlatformApp/Views/Chat/Cards/TableCard.swift`
- `ios/AIPlatformApp/Views/Chat/ChatView.swift`
- `ios/AIPlatformApp/Views/Chat/Cards/ClarifyCard.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatTopBarView.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/Chat/Dispatchers/BlockCardDispatcher.swift`
- `ios/AIPlatformApp/Views/Chat/Dispatchers/PluginRenderContext.swift`
- `ios/AIPlatformApp/Views/Chat/MessageBubbleView.swift`
- `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`
- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `backend/api/chat.py`
- `scripts/hermes_bridge.py`
- `tests/test_knowledge_consumption_gate_server.py`
- `tests/test_product_capabilities.py`

## Architecture reuse

- Reused QCP workflow and knowledge-navigation events; no backend schema or endpoint was added.
- Reused `MessageBlock -> BlockCardDispatcher`, `AppState` navigation, `KnowledgeNoteStore`, native `UITextView` selection, and the existing bounded long-answer preview/full-reader path.
- Added only two semantic message block cases so workflow and knowledge navigation cards persist with chat history.
- Reused the same native text-selection and note-save path for contextual bilingual actions, paragraph spacing, and lightweight SwiftUI chapter illustrations; no image dependency or parallel annotation store was added.
- Reused `/api/chat/stream` with `quoted_context` and the existing book/local-note context scopes for in-reader answers; selection context is clipped to the backend's 2,000-character contract and no new endpoint or schema was added.
- Reused `FormulaCard` and fixed the shared Markdown parser so block LaTeX, fenced `math`/`latex`/`tex`, and authored headings drive dedicated formula cards and semantic section cards.
- Reused `KnowledgeNoteStore` as the annotation source of truth; saved passages now render as tappable underline/highlighter marks and legacy excerpt notes remain parseable.
- Reused the note Markdown file for inline annotation metadata; the reading renderer removes that metadata from the visible report, restores the mark at the original passage, and opens the student-note detail sheet from either the underline or margin bookmark.
- Reused the signed selected-book `book_scope`; a server-authored selection marker now excludes only authorized selected-text questions from the unrelated tenant-Wiki consumption gate. Ordinary book and internal-knowledge questions remain gated.
- Reused the existing `scrollPosition` path and stopped history identity refreshes from overwriting it after a user drag; no competing scroll controller was added.
- Reused `MarkdownBlockParser -> FormulaCard`; common LaTeX operators, Greek letters, fractions, subscripts, and superscripts now render as native serif mathematical glyphs without adding a WebView or dependency.
- Completed long/structured Chat answers now use the full-width warm report surface, compact navigation, authored section flow, and the same report layout in the full-answer reader.
- Reused `MathFormulaPresentation` for `$…$`, `\(…\)`, and `\[…\]` inside normal Markdown, table cells, books, and notes; dedicated formula cards remain the path for block formulas.
- Reused `KnowledgeActionBlock` and `TenantSessionCoordinator.handleKnowledgeAction` for the requested clarify → confirm → processing → completion save-to-notes flow; no parallel state machine, repository, or endpoint was introduced.
- Reused `KnowledgeNoteEditor` and `KnowledgeNoteStore` for the warm student-notes editor/read view, pastel tags, related-content sheet, and existing annotation marks/details.
- Reused `TravelPlanResultView`, `TravelPlanDocument` and `MapKit` for the reference-matched travel note cover, live route map, five-day timeline, place detail and readiness check; no second travel model or service was added.
- Reused the native `UITextView` edit menu and the existing annotation persistence path for the exact selected-text actions `提问 / 高亮 / 批注 / 复制`; Q&A can be saved through the same note store and is classified as `问答` in the annotation center.

## Git preflight

- status: worktree already contained the user's ongoing V3-V5 redesign changes; they were preserved and not reset, staged, or committed.
- branch: `codex/ios-v3-v5-style-sandbox-20260917`
- HEAD: `58d212f18ed1edd71d0a95d18b12fc0b820eb277`
- remote: `origin` local `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0`; `source` `https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/Users/dengzhaoyu/Documents/AI Lab/.worktrees/quantum-ios-style-sandbox-20260917`

## Validation

- `git diff --check`: passed.
- iOS Simulator build: passed for `AIPlatformApp`, iOS Simulator 26.1.
- Focused test class: 145 tests executed, 0 failed, including:
  - semantic reading sections and contiguous server Markdown coalescing;
  - workflow/knowledge cards persist across chat history round-trip;
  - English passages switch to English reading actions while Chinese passages retain Chinese actions.
  - Markdown block formula extraction and standalone formula-card paging;
  - real book annotation quote/detail/book/section metadata parsing;
  - heading-based reading sections preserve continuous prose;
  - bilingual reading-action detection.
- New annotation extraction regression passed: the original passage remains visible, stored callout metadata stays hidden, and quote/detail/id round-trip exactly.
- Visual check: long book fixture launched in the simulator and verified a single chapter heading, semantic illustration, wider leading, and continuous prose. The temporary persistent hint was subsequently removed per user feedback; ask/annotation controls now appear only after native text selection.
- Signed physical iOS device build: passed for Xcode destination `00008150-000C50980244401C`; bundle id `com.ailab.AIPlatformApp`, team `AALA948YY5`.
- Physical-device install and launch: passed at 23:21 on `囧尼部落` (`CFE79F35-1270-527D-8BD7-9AB60449B6DF`), iPhone 17 Pro, after the final streaming-question, inline-annotation, and report-layout changes.
- 2026-09-19 regression: `WorkflowLifecycleDTOTests` executed 145 tests with 0 failures, including user-owned scroll-position protection and native math presentation.
- Knowledge-gate regression: `python3 -m pytest -q tests/test_knowledge_consumption_gate_server.py` executed 15 tests with 0 failures.
- Signed physical-device rebuild, install, and launch passed again at 00:02 on `囧尼部落`; bundle id `com.ailab.AIPlatformApp`.
- Visual smoke check: the isolated iPhone 17 Pro simulator confirmed the compact non-capsule navigation and stable Chat layout. The generated ImageToCode report/formula references were used as the implementation baseline.
- 2026-09-19 final physical-device unit run: `AIPlatformAppTests.xctest` executed 208 tests with 0 failures, including the new inline-math parser regression.
- Final unsigned generic iOS build passed; final signed device build passed; `git diff --check` passed.
- Final physical-device install and launch passed at 00:57 on `囧尼部落` (`CFE79F35-1270-527D-8BD7-9AB60449B6DF`), bundle id `com.ailab.AIPlatformApp`.
- 2026-09-19 travel/annotation pass: signed physical-device compilation completed for the updated travel note and reader UI. The focused test bundle compiled and signed; execution initially waited because `囧尼部落` was locked.
- 2026-09-19 travel/annotation regression: `WorkflowLifecycleDTOTests` executed 145 tests with 0 failures on the booted iPhone 17 Pro simulator, including travel-plan decoding and the updated annotation note/Q&A classification.
- Updated signed app installed successfully at 02:02 on `囧尼部落`; launch automation was denied only because SpringBoard reported the phone locked. The app is installed and can be opened immediately after unlock.
- 2026-09-19 note/bookshelf/PPT pass: ordinary notes now enter the travel template only through an explicit `旅行`/`travel`/`trip` tag; prose mentioning travel no longer changes the document type. Ordinary photos remain inline Markdown attachments rather than opening the travel moment composer.
- The note editor now opens a compact student compose surface for empty notes and shares the same `NoteReadingView` document renderer with display mode for headings, quote/callout cards, images, inline annotations and charts. Voice input reuses `SpeechRecognizerService` and persists its transcript as a normal Markdown callout.
- The bookshelf root now matches the supplied warm editorial reference: serif title, circular search/refresh controls, underline tabs, two prominent current-reading covers with progress and continuation buttons, and a compact recommendation row. Existing bookshelf DTOs, subscription state and book reader remain unchanged.
- `presentation.create_from_text` was already implemented end to end. The actual failure was model routing: explicit PPT creation requests had no mandatory native-tool directive. The bridge now instructs Hermes to call `app_presentation_create_from_text`, emit the existing `capability.proposed` confirmation card, and never expose internal durable-proposal/token wording.
- PPT capability regression: `python3 -m pytest -q tests/test_product_capabilities.py` executed 27 tests with 0 failures.
- iOS regression: `WorkflowLifecycleDTOTests` executed 145 tests with 0 failures, including the shared native chart parser used by Chat and notes.
- Unsigned generic iOS Simulator build passed. Signed iPhone build passed with Apple Development profile, then installed and launched successfully at 02:54 on `囧尼部落` (`CFE79F35-1270-527D-8BD7-9AB60449B6DF`), bundle id `com.ailab.AIPlatformApp`.
- The final signed build, including bookshelf recommendation de-duplication, installed successfully again at 03:06 on `囧尼部落`; automatic launch at 03:07 was denied only because SpringBoard reported the phone locked.

## Delivery evidence

- commit SHA: not created; user did not request a commit.
- GitHub remote/ref/SHA: not pushed; no push authorization.
- server_before: current iOS build points to `https://120.24.248.58`; server version was not changed.
- server_after: not deployed; the selected-text gate correction and PPT Hermes routing correction are locally tested but require explicit server deployment authorization before the physical phone can receive them.
- health_check: simulator Chat/reader fixtures and physical-device app launched successfully; server deployment not performed.
- functional_check: simulator visual check, prior 208-test iOS unit suite, 15-test server gate suite, and the final 145-test related regression suite passed. The updated signed app installed on the physical device; automatic launch was blocked by the phone lock, so final touch/visual acceptance remains with the user after unlock.
- rollback_point: current HEAD `58d212f18ed1edd71d0a95d18b12fc0b820eb277`; changes remain uncommitted in the isolated worktree.

## Remaining risks

- Device installation and launch are verified, but final touch interaction and visual preference still require the user's physical-device acceptance.
- Inline selection Q&A uses the live `/api/chat/stream` contract and therefore still depends on current backend availability; progressive frontend states and protocol compatibility are verified in code, while live answer quality remains a server/model concern.
- The physical app targets `https://120.24.248.58`; until the locally tested backend changes are explicitly deployed, selected-book questions can still show the old knowledge gate and Chat PPT requests can still show the old internal proposal/token wording.
- Native math formatting intentionally covers common school/report notation. Matrix, cases, and deeply nested TeX still require a dedicated TeX renderer if they become a real content requirement.
- The native `UITextViewDelegate` link callback used for tapping underline marks is deprecated from iOS 17 but remains supported and compiled successfully; migrate only when the deployment baseline drops the compatibility callback.
- Final travel/annotation touch acceptance still requires the user to unlock the connected phone and open the already-installed app.
