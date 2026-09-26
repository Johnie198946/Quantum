import SwiftUI

/// Comparison is read-only. The parent keeps the existing signed execution/receipt path.
struct CleanupMergeReviewView: View {
    let title: String
    let targetID: String
    let sourceID: String
    let snapshots: [[String: JSONScalar]]
    let locked: Bool
    var initialPreview: KnowledgeMergePreview? = nil
    let onAccept: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var preview: KnowledgeMergePreview?
    @State private var choices: [String: String] = [:]
    @State private var error: String?
    @State private var loading = false
    @State private var showResult = false

    private var result: String? { preview?.mergedMarkdown(choices: choices) }
    private var remaining: Int { preview?.segments.filter { $0.kind == "replace" && choices[$0.id] == nil }.count ?? 0 }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("两篇笔记，逐处看清").font(.title2.bold())
                        Text(title).font(.headline).textSelection(.enabled)
                        Text("保留目标笔记；另一篇合并后归档，可恢复。相同段落只保留一份，不同表述由你决定。")
                            .font(.subheadline).foregroundStyle(AppTheme.Colors.textSecondary)
                    }
                    if loading { ProgressView("正在比较两篇笔记…").frame(maxWidth: .infinity).padding(24) }
                    if let error {
                        VStack(alignment: .leading, spacing: 12) {
                            Label("暂时无法比较", systemImage: "exclamationmark.circle").font(.headline)
                            Text(error).font(.subheadline)
                            Button("重新比较") { Task { await load() } }.frame(minHeight: 44)
                        }.padding().background(AppTheme.Colors.surfaceElevated, in: RoundedRectangle(cornerRadius: 20))
                    }
                    if let preview {
                        summary(preview)
                        if preview.coarse {
                            Label("内容分段较多，已切换为全文核对；没有截断正文。", systemImage: "info.circle")
                                .font(.subheadline).foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                        Picker("查看方式", selection: $showResult) {
                            Text("只看差异").tag(false)
                            Text("合并后全文").tag(true)
                        }.pickerStyle(.segmented)
                        if showResult {
                            if let result {
                                Text(result).font(.body).lineSpacing(5).textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading).padding()
                                    .background(AppTheme.Colors.surfaceElevated, in: RoundedRectangle(cornerRadius: 20))
                            } else {
                                Label("还有 \(remaining) 处差异需要选择，选完即可查看完整结果。", systemImage: "checklist")
                            }
                        } else {
                            if preview.choiceCount == 0 && preview.addedCount == 0 && preview.segments.allSatisfy({ $0.kind == "equal" }) {
                                Label("正文完全一致，只需保留一份", systemImage: "checkmark.seal")
                                    .font(.headline).padding().frame(maxWidth: .infinity, alignment: .leading)
                                    .background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: 20))
                            }
                            ForEach(preview.segments.filter { $0.kind != "equal" }) { segment in difference(segment) }
                            if preview.commonCount > 0 {
                                DisclosureGroup("\(preview.commonCount) 段相同内容 · 已折叠") {
                                    ForEach(preview.segments.filter { $0.kind == "equal" }) { segment in
                                        Text(segment.before).font(.body).textSelection(.enabled).padding(.vertical, 8)
                                    }
                                }.font(.subheadline).padding()
                            }
                        }
                    }
                    if dynamicTypeSize.isAccessibilitySize { acceptance }
                }.padding(20)
            }
            .background(AppTheme.Colors.background)
            .safeAreaInset(edge: .bottom) {
                if !dynamicTypeSize.isAccessibilitySize { acceptance }
            }
            .navigationTitle("笔记差异").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("关闭") { dismiss() } } }
        }
        .task { if let initialPreview { preview = initialPreview } else { await load() } }
    }

    private var acceptance: some View {
        VStack(spacing: 8) {
            Button {
                if let result { onAccept(result) }
            } label: {
                Text(remaining > 0 ? "还有 \(remaining) 处待选择" : "采用结果，加入确认单")
                    .font(.headline).frame(maxWidth: .infinity, minHeight: 48)
            }
            .buttonStyle(.borderedProminent).tint(AppTheme.Colors.primary)
            .disabled(result == nil || locked || loading)
            .accessibilityIdentifier("cleanup-accept-merge")
            Text(preview != nil && remaining == 0 && result == nil ? "正文为空，无法加入合并确认单" : "此步只确认预览，不会修改或归档笔记").font(.caption).foregroundStyle(AppTheme.Colors.textSecondary)
        }.padding(.horizontal, 20).padding(.vertical, 12).background(AppTheme.Colors.surfaceElevated)
    }

    private func summary(_ preview: KnowledgeMergePreview) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) { summaryLabels(preview) }
            VStack(alignment: .leading, spacing: 12) { summaryLabels(preview) }
        }
        .font(.subheadline.weight(.semibold)).padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: 20))
    }

    @ViewBuilder private func summaryLabels(_ preview: KnowledgeMergePreview) -> some View {
        Label("相同 \(preview.commonCount) 段", systemImage: "equal.circle")
        Label("新增 \(preview.addedCount) 段", systemImage: "plus.circle")
        Label("不同 \(preview.choiceCount) 处", systemImage: "arrow.left.arrow.right.circle")
    }

    private func difference(_ segment: KnowledgeMergePreview.Segment) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Label(segment.kind == "replace" ? "不同表述 · 请选择" : segment.kind == "insert" ? "来源新增 · 将补入" : "仅保留笔记有 · 将保留",
                  systemImage: segment.kind == "replace" ? "arrow.left.arrow.right" : segment.kind == "insert" ? "plus.circle" : "checkmark.circle")
                .font(.headline)
            if !segment.before.isEmpty { passage("保留的笔记", runs: segment.beforeRuns, tint: AppTheme.Colors.accent) }
            if !segment.after.isEmpty { passage("合并来源", runs: segment.afterRuns, tint: AppTheme.Colors.primary) }
            if segment.kind == "replace" {
                // Vertical choices stay readable at accessibility text sizes.
                VStack(spacing: 0) {
                    choice("保留这篇的表述", value: "target", segment: segment)
                    choice("采用来源的表述", value: "source", segment: segment)
                    choice("两种都保留", value: "both", segment: segment)
                }
            }
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.surfaceElevated, in: RoundedRectangle(cornerRadius: 20))
            .overlay { RoundedRectangle(cornerRadius: 20).stroke(AppTheme.Colors.border, lineWidth: 1) }
    }

    private func passage(_ label: String, runs: [KnowledgeMergePreview.Run], tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label).font(.caption.weight(.semibold)).foregroundStyle(tint)
            runs.enumerated().reduce(Text("")) { text, entry in
                let run = entry.element
                let value = entry.offset == runs.count - 1 ? run.text.trimmingCharacters(in: .newlines) : run.text
                return text + (run.changed ? Text(value).bold().underline().foregroundColor(tint) : Text(value).foregroundColor(AppTheme.Colors.textPrimary))
            }.font(.body).lineSpacing(4).textSelection(.enabled)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(12)
            .background(tint.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
    }

    private func choice(_ label: String, value: String, segment: KnowledgeMergePreview.Segment) -> some View {
        Button { choices[segment.id] = value } label: {
            HStack(spacing: 12) {
                Image(systemName: choices[segment.id] == value ? "checkmark.circle.fill" : "circle")
                Text(label).multilineTextAlignment(.leading)
                Spacer(minLength: 0)
            }.frame(minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.plain).foregroundStyle(AppTheme.Colors.primary).disabled(locked)
            .accessibilityIdentifier("cleanup-choice-\(segment.id)-\(value)")
            .accessibilityAddTraits(choices[segment.id] == value ? .isSelected : [])
    }

    @MainActor private func load() async {
        guard !loading else { return }
        loading = true; error = nil; preview = nil; choices = [:]
        defer { loading = false }
        do {
            let value = try await APIClient.shared.request(KnowledgeMergePreview.self,
                path: "me/knowledge-actions/merge-preview", method: "POST",
                body: JSONScalar.object(["target_note_id": .string(targetID), "source_note_id": .string(sourceID),
                                         "local_notes": .array(snapshots.map(JSONScalar.object))]))
            guard !Task.isCancelled else { return }
            guard value.targetNoteId == targetID, value.sourceNoteId == sourceID,
                  snapshots.contains(where: { $0["id"] == .string(targetID) && $0["content_hash"] == .string(value.targetHash) }),
                  snapshots.contains(where: { $0["id"] == .string(sourceID) && $0["content_hash"] == .string(value.sourceHash) }) else {
                throw APIError.network("笔记版本已变化，请关闭并刷新建议")
            }
            preview = value
        } catch {
            guard !Task.isCancelled else { return }
            self.error = "暂时无法读取差异，请关闭并刷新建议后重试。本次没有改动笔记。"
        }
    }
}

/// Reuses the cleanup workspace and comparison UI inside Chat; only a fresh proposal is returned.
struct ChatCleanupReviewSheet: View {
    let target: KnowledgeNavigationTarget
    @ObservedObject var coordinator: TenantSessionCoordinator
    @Environment(\.dismiss) private var dismiss
    @State private var snapshots: [[String: JSONScalar]] = []
    @State private var title = "笔记比较"
    @State private var scope = ""
    @State private var sessionID = ""
    @State private var error: String?

    var body: some View {
        Group {
            if target.destination == "cleanup" {
                NavigationStack {
                    ScrollView { VStack(spacing: 16) { CleanupWorkspaceView(onLater: { dismiss() }) }.padding() }
                        .navigationTitle("整理建议")
                        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("关闭") { dismiss() } } }
                }
            } else if snapshots.count == 2, let targetID = target.noteId, let sourceID = target.sourceNoteId {
                CleanupMergeReviewView(title: title, targetID: targetID, sourceID: sourceID, snapshots: snapshots, locked: coordinator.cleanupProposalBusy) { markdown in
                    Task { _ = await coordinator.proposeComparedMerge(targetID: targetID, sourceID: sourceID, snapshots: snapshots, markdown: markdown, sessionID: sessionID, accountScope: scope) }
                }
            } else {
                NavigationStack {
                    ContentUnavailableView("暂时无法比较", systemImage: "doc.text.magnifyingglass", description: Text(error ?? "正在读取当前笔记…"))
                        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("关闭") { dismiss() } } }
                }
            }
        }
        .interactiveDismissDisabled(coordinator.cleanupProposalBusy)
        .task {
            guard target.destination == "note_comparison", let targetID = target.noteId, let sourceID = target.sourceNoteId, targetID != sourceID else { return }
            let store = KnowledgeNoteStore.shared
            scope = store.authorizationScope
            sessionID = coordinator.sessionManager.activeSessionID()
            let notes = [targetID, sourceID].compactMap { store.anyNote(id: $0) }
            guard notes.count == 2, notes.allSatisfy({ $0.archivedAt == nil && store.markdown(for: $0).count <= 20_000 }) else {
                error = "笔记已变化、不可用或超出本次比较范围，请同步后重新选择。"
                return
            }
            title = notes.map(\.title).joined(separator: " / ")
            snapshots = notes.map { note in ["id": .string(note.id), "title": .string(note.title), "markdown": .string(store.markdown(for: note)), "content_hash": .string(store.contentHash(for: note)), "tags": .array(note.tags.map(JSONScalar.string)), "archived": .bool(false)] }
        }
    }
}

#if DEBUG
struct CleanupMergeReviewPreview: View {
    @State private var accepted = false
    private var fixture: KnowledgeMergePreview {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(KnowledgeMergePreview.self, from: Data(#"{"target_note_id": "target", "source_note_id": "source", "target_hash": "8fb89d2df5a8427da1f03eda89b510dbd27b65ef386feccdaf5db44aa221ec11", "source_hash": "33a32271f85eec2d36565c0302d5c7bcfe75d05de4a965af215299791190c11f", "coarse": false, "segments": [{"id": "0", "kind": "equal", "before": "旅行安排\n\n", "after": "旅行安排\n\n", "before_runs": [{"text": "旅行安排\n\n", "changed": false}], "after_runs": [{"text": "旅行安排\n\n", "changed": false}], "target_blocks": 1, "source_blocks": 1}, {"id": "1", "kind": "replace", "before": "上午参观博物馆，门票预算 300 元。\n\n", "after": "上午参观博物馆，门票预算 500 元。\n\n", "before_runs": [{"text": "上午参观博物馆，门票预算 ", "changed": false}, {"text": "3", "changed": true}, {"text": "00 元。\n\n", "changed": false}], "after_runs": [{"text": "上午参观博物馆，门票预算 ", "changed": false}, {"text": "5", "changed": true}, {"text": "00 元。\n\n", "changed": false}], "target_blocks": 1, "source_blocks": 1}, {"id": "2", "kind": "equal", "before": "下午沿河散步，晚餐在老城区。\n\n", "after": "下午沿河散步，晚餐在老城区。\n\n", "before_runs": [{"text": "下午沿河散步，晚餐在老城区。\n\n", "changed": false}], "after_runs": [{"text": "下午沿河散步，晚餐在老城区。\n\n", "changed": false}], "target_blocks": 1, "source_blocks": 1}, {"id": "3", "kind": "insert", "before": "", "after": "新增提醒：周一闭馆，请提前预约。\n", "before_runs": [], "after_runs": [{"text": "新增提醒：周一闭馆，请提前预约。\n", "changed": true}], "target_blocks": 0, "source_blocks": 1}]}"#.utf8))
    }
    var body: some View {
        if accepted { Text("已加入确认单").accessibilityIdentifier("cleanup-preview-accepted") }
        else {
            CleanupMergeReviewView(title: "旅行计划", targetID: "target", sourceID: "source", snapshots: [], locked: false, initialPreview: fixture) { _ in accepted = true }

        }
    }
}
#endif
