//
//  ChatStatusCards.swift
//  AIPlatformApp
//
//  Status & Error Cards (Pending, Degraded, Interrupted, Orphan)
//  Extracted from ChatView for modularity and minimal footprint.
//

import SwiftUI

// MARK: - In-Flight & Queue Models

public struct PendingItem: Identifiable, Sendable {
    public let id: String
    public let text: String
    public let quote: QuotedContext?
    public let contextScope: ChatContextScopeDTO
    public let clientSessionContext: ClientSessionContextDTO?

    public init(id: String = UUID().uuidString, text: String, quote: QuotedContext? = nil, contextScope: ChatContextScopeDTO = ChatContextScopeDTO(), clientSessionContext: ClientSessionContextDTO? = nil) {
        self.id = id
        self.text = text
        self.quote = quote
        self.contextScope = contextScope
        self.clientSessionContext = clientSessionContext
    }
}

public struct InFlightRequest: Identifiable, Sendable {
    public let id: String
    public let sessionId: String
    public let text: String
    public let quote: QuotedContext?
    public let regenerate: Bool
    public let agentId: String?
    public let contextScope: ChatContextScopeDTO
    public let clientSessionContext: ClientSessionContextDTO?
    public var didRetry404: Bool = false
    public var phase: InFlightPhase = .thinking

    public init(
        id: String = UUID().uuidString,
        sessionId: String,
        text: String,
        quote: QuotedContext? = nil,
        regenerate: Bool = false,
        agentId: String? = nil,
        contextScope: ChatContextScopeDTO = ChatContextScopeDTO(),
        clientSessionContext: ClientSessionContextDTO? = nil,
        didRetry404: Bool = false,
        phase: InFlightPhase = .thinking
    ) {
        self.id = id
        self.sessionId = sessionId
        self.text = text
        self.quote = quote
        self.regenerate = regenerate
        self.agentId = agentId
        self.contextScope = contextScope
        self.clientSessionContext = clientSessionContext
        self.didRetry404 = didRetry404
        self.phase = phase
    }
}

public enum InFlightPhase: Equatable, Sendable {
    case thinking
    case timeout
    case networkError
    case serverError(String)
}

public struct NoteDraftCard: View {
    @State private var showingDetails = false
    @State private var showingMergePreview = false

    public let draft: NoteDraftBlock
    public let onSave: () -> Void
    public let onMerge: () -> Void
    public let onEdit: () -> Void
    public let onDiscard: () -> Void

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                headerView
                previewView
                if hasMergeCandidates {
                    mergeNoticeView
                }
            }
            .contentShape(Rectangle())
            .onTapGesture { showingDetails = true }
            .accessibilityAddTraits(.isButton)
            .accessibilityHint("打开完整笔记草稿")
            if draft.state == .awaitingConfirmation {
                actionView
            } else {
                statusView
            }
        }
        .padding(AppTheme.Spacing.xl)
        .quantumCard()
        .accessibilityElement(children: .contain)
        .sheet(isPresented: $showingDetails) {
            NoteDraftDetailSheet(draft: draft)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
        .fullScreenCover(isPresented: $showingMergePreview) {
            NoteMergePreviewView(
                draft: draft,
                onConfirm: {
                    showingMergePreview = false
                    onMerge()
                },
                onSaveNew: {
                    showingMergePreview = false
                    onSave()
                },
                onDismiss: { showingMergePreview = false }
            )
        }
    }

    private var hasMergeCandidates: Bool {
        !(draft.mergeCandidates ?? []).isEmpty
    }

    private var headerView: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            ZStack {
                Circle()
                    .fill(draft.state == .awaitingConfirmation ? AppTheme.Colors.quantumViolet.opacity(0.12) : AppTheme.Icons.success)
                Image(systemName: draft.state == .awaitingConfirmation ? "wand.and.stars" : "checkmark")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(draft.state == .awaitingConfirmation ? AppTheme.Icons.intelligence : Color.white)
            }
            .frame(width: 40, height: 40)
            .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text(draft.state == .awaitingConfirmation ? "整理完成，请确认" : "已保存到书架")
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text(draft.state == .awaitingConfirmation ? "已按你的要求生成结构化笔记。" : "知识已为你整理完成。")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
            Spacer(minLength: 0)
            Image(systemName: "ellipsis")
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textTertiary)
                .accessibilityHidden(true)
        }
    }

    private var previewView: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            ZStack {
                LinearGradient(colors: [AppTheme.Colors.mistSky, AppTheme.Colors.mistMint], startPoint: .top, endPoint: .bottom)
                VStack(spacing: 7) {
                    Text(draft.title).font(.system(size: 12, weight: .bold, design: .serif)).multilineTextAlignment(.center).lineLimit(4)
                    Image(systemName: "mountain.2.fill").foregroundStyle(AppTheme.Icons.interactive)
                }
            }
            .frame(width: 92, height: 124)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Text(draft.title).font(.system(.title3, design: .serif, weight: .bold)).lineLimit(3)
                Text(previewText).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary).lineLimit(3)
                HStack(spacing: 5) {
                    ForEach(draft.tags.prefix(3), id: \.self) { tag in
                        Text(tag).font(.system(size: 10, weight: .medium))
                            .padding(.horizontal, 7).padding(.vertical, 5)
                            .background(AppTheme.Colors.mistMint.opacity(0.66), in: Capsule())
                    }
                }
            }
            Spacer(minLength: 0)
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.76))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private var mergeNoticeView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "sparkles")
                    .foregroundStyle(AppTheme.Colors.emberOrange)
                Text("发现 \(draft.mergeCandidates?.count ?? 0) 篇相关笔记")
                    .font(AppTheme.Typography.supporting.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Spacer(minLength: 0)
            }

            HStack(spacing: AppTheme.Spacing.xs) {
                ForEach((draft.mergeCandidates ?? []).prefix(2)) { candidate in
                    Text(candidate.title)
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(1)
                        .padding(.horizontal, AppTheme.Spacing.sm)
                        .padding(.vertical, 6)
                        .background(AppTheme.Colors.cardBackground.opacity(0.82))
                        .clipShape(Capsule())
                }
                if let count = draft.mergeCandidates?.count, count > 2 {
                    Text("+\(count - 2)")
                        .font(AppTheme.Typography.micro.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }
            }

            Text("合并会重新编排内容，旧笔记会移入可恢复的归档。")
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textTertiary)
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.warningSurface)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private var actionView: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.sm) {
                draftDecision("保存", detail: draft.isUpdate ? "应用到原笔记" : "存入书架", icon: "bookmark.fill", selected: true, action: onSave)
                draftDecision("合并", detail: hasMergeCandidates ? "与现有笔记合并" : "暂无相似笔记", icon: "arrow.triangle.merge", selected: false) { showingMergePreview = true }
                    .disabled(!hasMergeCandidates)
                draftDecision("丢弃", detail: "不保存此内容", icon: "trash", selected: false, action: onDiscard)
            }
            Button(action: onEdit) {
                Label("先编辑内容", systemImage: "pencil")
                    .font(AppTheme.Typography.supporting)
            }
        }
    }

    private func draftDecision(
        _ title: String, detail: String, icon: String, selected: Bool, action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            VStack(spacing: 5) {
                Image(systemName: icon).font(.title3)
                Text(title).font(AppTheme.Typography.label)
                Text(detail).font(.system(size: 9)).foregroundStyle(AppTheme.Colors.textTertiary).lineLimit(2)
            }
            .frame(maxWidth: .infinity, minHeight: 92)
            .foregroundStyle(selected ? AppTheme.Icons.interactive : AppTheme.Colors.textPrimary)
            .background(selected ? AppTheme.Colors.mistSky.opacity(0.42) : Color.white.opacity(0.74), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(selected ? AppTheme.Icons.interactive : AppTheme.Colors.border) }
        }
        .buttonStyle(.plain)
    }

    private var statusView: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: statusIcon)
                .foregroundStyle(draft.state == .discarded ? AppTheme.Colors.textTertiary : AppTheme.Icons.success)
            Text(statusText)
                .font(AppTheme.Typography.supporting.weight(.medium))
                .foregroundStyle(AppTheme.Colors.textSecondary)
            Spacer(minLength: 0)
        }
        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
        .padding(.horizontal, AppTheme.Spacing.md)
        .background(draft.state == .discarded ? AppTheme.Colors.surfaceTint : AppTheme.Colors.successSurface)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private var previewText: String {
        var value = draft.markdown
        value = value.replacingOccurrences(of: "(?m)^#{1,6}\\s*", with: "", options: .regularExpression)
        value = value.replacingOccurrences(of: "(?m)^\\s*[-*]\\s+", with: "• ", options: .regularExpression)
        return value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var statusText: String {
        switch draft.state {
        case .saved: return draft.isUpdate ? "已更新并同步" : "已保存并同步"
        case .savedLocally: return draft.isUpdate ? "已更新到本地，等待同步" : "已保存到本地，等待同步"
        case .discarded: return "已放弃"
        case .awaitingConfirmation: return "等待确认"
        }
    }

    private var badgeText: String {
        switch draft.state {
        case .awaitingConfirmation: return draft.isUpdate ? "待应用" : "待确认"
        case .saved, .savedLocally: return draft.isUpdate ? "已更新" : "已保存"
        case .discarded: return "已放弃"
        }
    }

    private var statusIcon: String {
        draft.state == .discarded ? "xmark.circle" : "checkmark.circle.fill"
    }
}

public struct NoteMergePreviewView: View {
    public let draft: NoteDraftBlock
    public let onConfirm: () -> Void
    public let onSaveNew: () -> Void
    public let onDismiss: () -> Void
    @State private var showsMerged = true

    public init(
        draft: NoteDraftBlock,
        onConfirm: @escaping () -> Void,
        onSaveNew: @escaping () -> Void,
        onDismiss: @escaping () -> Void
    ) {
        self.draft = draft
        self.onConfirm = onConfirm
        self.onSaveNew = onSaveNew
        self.onDismiss = onDismiss
    }

    public var body: some View {
        ZStack {
            QuantumMistBackground()
            VStack(spacing: 0) {
                compactHeader("合并预览")
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        Picker("预览模式", selection: $showsMerged) {
                            Text("合并前").tag(false)
                            Text("合并后").tag(true)
                        }
                        .pickerStyle(.segmented)

                        sourceNotes
                        if showsMerged { mergedPreview } else { originalPreview }
                    }
                    .padding(AppTheme.Spacing.lg)
                }

                VStack(spacing: AppTheme.Spacing.sm) {
                    Button(action: onConfirm) {
                        Label("合并并归档旧笔记", systemImage: "arrow.triangle.merge")
                    }
                    .buttonStyle(QuantumPrimaryButtonStyle())
                    Button("保存为新笔记", action: onSaveNew)
                        .font(AppTheme.Typography.label)
                        .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                        .buttonStyle(.bordered)
                        .tint(AppTheme.Colors.primary)
                }
                .padding(AppTheme.Spacing.lg)
                .background(.ultraThinMaterial)
            }
        }
    }

    private func compactHeader(_ title: String) -> some View {
        HStack {
            Button(action: onDismiss) {
                Image(systemName: "chevron.left").minimumTouchTarget()
            }
            .buttonStyle(SoftButtonStyle())
            Spacer()
            Text(title).font(AppTheme.Typography.cardTitle)
            Spacer()
            Image(systemName: "ellipsis")
                .minimumTouchTarget()
                .foregroundStyle(AppTheme.Icons.secondary)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(.thinMaterial)
    }

    private var sourceNotes: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Text("来源笔记（\((draft.mergeCandidates ?? []).count)）")
                .font(AppTheme.Typography.label)
            HStack(spacing: AppTheme.Spacing.sm) {
                ForEach((draft.mergeCandidates ?? []).prefix(2)) { note in
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Image(systemName: "doc.text.fill")
                            .foregroundStyle(AppTheme.Icons.interactive)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(note.title).font(AppTheme.Typography.supporting.weight(.semibold)).lineLimit(1)
                            Text(note.updatedAt ?? "最近更新")
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(AppTheme.Colors.textTertiary)
                        }
                    }
                    .frame(maxWidth: .infinity, minHeight: 58, alignment: .leading)
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                }
            }
        }
    }

    private var mergedPreview: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Label("合并后标题", systemImage: "doc.text")
                .font(AppTheme.Typography.label)
            HStack {
                Text(draft.mergedTitle ?? draft.title)
                    .font(AppTheme.Typography.body.weight(.semibold))
                Spacer()
                Image(systemName: "chevron.right")
                    .foregroundStyle(AppTheme.Icons.tertiary)
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))

            Text("标签").font(AppTheme.Typography.label)
            HStack(spacing: AppTheme.Spacing.xs) {
                ForEach((draft.mergedTags ?? draft.tags).prefix(3), id: \.self) { tag in
                    Text(tag)
                        .font(AppTheme.Typography.micro)
                        .padding(.horizontal, AppTheme.Spacing.sm)
                        .padding(.vertical, 6)
                        .background(AppTheme.Colors.surfaceTint, in: Capsule())
                }
                Image(systemName: "plus")
                    .frame(width: 32, height: 32)
                    .background(AppTheme.Colors.cardBackground, in: Circle())
            }

            Text("内容变化（示例）").font(AppTheme.Typography.label)
            changeCard(
                icon: "plus.circle.fill",
                title: "新增 3 处",
                lines: ["增加了全球与本地的案例对比", "补充了大学生可以采取的行动建议"],
                color: AppTheme.Icons.success
            )
            changeCard(
                icon: "minus.circle.fill",
                title: "移除 2 处",
                lines: ["删除了重复的背景介绍", "精简了过时的数据"],
                color: AppTheme.Icons.destructive
            )
        }
    }

    private var originalPreview: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Text(draft.title).font(AppTheme.Typography.sectionTitle)
            Text(draft.markdown)
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
    }

    private func changeCard(icon: String, title: String, lines: [String], color: Color) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            Label(title, systemImage: icon)
                .font(AppTheme.Typography.supporting.weight(.semibold))
                .foregroundStyle(color)
            ForEach(lines, id: \.self) { line in
                Text("•  \(line)")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(AppTheme.Spacing.md)
        .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
    }
}

public struct NoteMergeCompletionView: View {
    public let draft: NoteDraftBlock
    public let onArchive: () -> Void
    public let onSaveNew: () -> Void
    public let onUndo: () -> Void
    public let onRetrySync: () -> Void

    public init(
        draft: NoteDraftBlock,
        onArchive: @escaping () -> Void = {},
        onSaveNew: @escaping () -> Void = {},
        onUndo: @escaping () -> Void = {},
        onRetrySync: @escaping () -> Void = {}
    ) {
        self.draft = draft
        self.onArchive = onArchive
        self.onSaveNew = onSaveNew
        self.onUndo = onUndo
        self.onRetrySync = onRetrySync
    }

    public var body: some View {
        ZStack {
            QuantumMistBackground()
            VStack(spacing: 0) {
                HStack {
                    Image(systemName: "chevron.left").minimumTouchTarget()
                    Spacer()
                    Text("合并完成").font(AppTheme.Typography.cardTitle)
                    Spacer()
                    Image(systemName: "ellipsis").minimumTouchTarget()
                }
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm)
                .background(.thinMaterial)

                ScrollView {
                    VStack(spacing: AppTheme.Spacing.xl) {
                        Image(systemName: "checkmark")
                            .font(.system(size: 34, weight: .bold))
                            .foregroundStyle(AppTheme.Icons.success)
                            .frame(width: 72, height: 72)
                            .background(AppTheme.Icons.success.opacity(0.12), in: Circle())
                        VStack(spacing: AppTheme.Spacing.xs) {
                            Text("笔记已合并").font(.title2.weight(.bold))
                            Text("内容更完整，结构更清晰。")
                                .font(AppTheme.Typography.supporting)
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                        }

                        HStack(spacing: AppTheme.Spacing.md) {
                            Image(systemName: "doc.text.fill")
                                .foregroundStyle(AppTheme.Icons.interactive)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(draft.mergedTitle ?? draft.title)
                                    .font(AppTheme.Typography.label)
                                Text("已保存到 我的笔记")
                                    .font(AppTheme.Typography.micro)
                                    .foregroundStyle(AppTheme.Colors.textTertiary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                        }
                        .padding(AppTheme.Spacing.md)
                        .quantumCard()

                        VStack(spacing: AppTheme.Spacing.sm) {
                            Button("合并并归档旧笔记", action: onArchive)
                                .buttonStyle(QuantumPrimaryButtonStyle())
                            Button("保存为新笔记", action: onSaveNew)
                                .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                                .buttonStyle(.bordered)
                                .tint(AppTheme.Colors.primary)
                        }

                        Divider()
                        HStack {
                            Label("10 秒内可撤销", systemImage: "clock.arrow.circlepath")
                            Spacer()
                            Button("撤销", action: onUndo)
                        }
                        .font(AppTheme.Typography.supporting)
                        .padding(AppTheme.Spacing.md)
                        .quantumCard()

                        HStack {
                            Label("已同步", systemImage: "checkmark.icloud.fill")
                                .foregroundStyle(AppTheme.Icons.success)
                            VStack(alignment: .leading) {
                                Text("已同步")
                                Text("上次同步 9:41")
                                    .font(AppTheme.Typography.micro)
                                    .foregroundStyle(AppTheme.Colors.textTertiary)
                            }
                            Spacer()
                            Button("重试", action: onRetrySync)
                        }
                        .font(AppTheme.Typography.supporting)
                        .padding(AppTheme.Spacing.md)
                        .quantumCard()
                    }
                    .padding(AppTheme.Spacing.xl)
                }
            }
        }
    }
}

#if DEBUG
public struct V4ClarifyMergePrototypeHost: View {
    public let pageID: String

    public init(pageID: String) {
        self.pageID = pageID
    }

    public var body: some View {
        if pageID.hasSuffix("p03") {
            NoteMergePreviewView(draft: draft, onConfirm: {}, onSaveNew: {}, onDismiss: {})
        } else if pageID.hasSuffix("p04") {
            NoteMergeCompletionView(draft: draft)
        } else {
            ZStack {
                QuantumMistBackground()
                VStack(spacing: 0) {
                    ChatTopBarView(
                        isGenerating: false,
                        title: pageID.hasSuffix("p02") ? "确认需求" : "与 Quantum 对话",
                        onTitleTap: {}, onNewSession: {}, onHistoryTap: {}, onClearTap: {}
                    )
                    ScrollView {
                        if pageID.hasSuffix("p02") {
                            RequirementConfirmationCard(
                                block: confirmationBlock
                            )
                            .padding(AppTheme.Spacing.lg)
                        } else {
                            VStack(spacing: AppTheme.Spacing.md) {
                                MessageBubbleView(
                                    message: ChatMessage(
                                        role: .user,
                                        content: "我想整理关于气候变化的笔记，可以先帮我确认几个问题吗？"
                                    )
                                )
                                NoteOrganizationClarifyView(block: clarifyBlock)
                                    .padding(.horizontal, AppTheme.Spacing.md)
                            }
                            .padding(.vertical, AppTheme.Spacing.lg)
                        }
                    }
                }
            }
        }
    }

    private var clarifyBlock: ClarifyBlock {
        ClarifyBlock(
            question: "好的！为了更好地帮助你，请先告诉我你的主要目的？",
            choices: ["学习理解", "写作准备", "梳理观点", "课程项目"],
            submitLabel: "确认",
            source: "note_organization"
        )
    }

    private var confirmationBlock: ClarifyBlock {
        ClarifyBlock(
            question: """
            请确认需求单
            目标：把气候变化笔记整理成适合大学生复习的学习卡片
            交付物：重点摘要、概念关系和行动建议
            目标用户与场景：大学生课前预习与考前回顾
            MVP 范围：基于已选择的 2 篇笔记，不补充外部材料
            约束与验收：保留引用来源，重要结论可回溯
            """,
            choices: ["确认，进入方案设计", "需要调整"],
            submitLabel: "确认并继续",
            source: "workflow"
        )
    }

    private var draft: NoteDraftBlock {
        NoteDraftBlock(
            id: "climate-merge-preview",
            title: "气候变化：现状、影响与行动",
            markdown: "气候变化影响生态、经济与日常生活，需要结合全球趋势和本地行动综合理解。",
            tags: ["气候变化", "环境", "大学生"],
            sourceSessionId: "preview-session",
            sourceMessageIds: ["preview-message"],
            mergeCandidates: [
                NoteMergeCandidate(id: "climate-1", title: "气候变化概述", snippet: "成因与影响", updatedAt: "2024.04.12"),
                NoteMergeCandidate(id: "climate-2", title: "可持续的未来", snippet: "行动与案例", updatedAt: "2024.05.03"),
            ],
            mergedTitle: "气候变化：现状、影响与行动",
            mergedMarkdown: "整合后的结构化笔记",
            mergedTags: ["气候变化", "环境", "大学生"]
        )
    }
}
#endif

private struct NoteDraftDetailSheet: View {
    @Environment(\.dismiss) private var dismiss
    let draft: NoteDraftBlock

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    if draft.isUpdate {
                        Label(
                            "将更新：\(draft.targetNoteTitle ?? draft.title)",
                            systemImage: "arrow.triangle.2.circlepath"
                        )
                        .font(AppTheme.Typography.supporting.weight(.semibold))
                        .foregroundStyle(AppTheme.Icons.intelligence)
                        .padding(AppTheme.Spacing.md)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(AppTheme.Colors.surfaceTint)
                        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                    }

                    Text(draft.title)
                        .font(AppTheme.Typography.sectionTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)

                    Text(.init(draft.markdown))
                        .font(AppTheme.Typography.body)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineSpacing(4)
                        .textSelection(.enabled)

                    if !draft.tags.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: AppTheme.Spacing.xs) {
                            ForEach(draft.tags, id: \.self) { tag in
                                Text("#\(tag)")
                                    .font(AppTheme.Typography.micro)
                                    .foregroundStyle(AppTheme.Icons.intelligence)
                                    .padding(.horizontal, AppTheme.Spacing.sm)
                                    .padding(.vertical, 6)
                                    .background(AppTheme.Colors.surfaceTint)
                                    .clipShape(Capsule())
                            }
                            }
                        }
                    }
                }
                .padding(AppTheme.Spacing.xl)
            }
            .background(AppTheme.Colors.background)
            .navigationTitle(draft.isUpdate ? "完善方案详情" : "笔记草稿详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
        }
    }
}

// MARK: - Placeholder Views

public struct PendingPlaceholderView: View {
    public let position: Int
    public let onCancel: () -> Void

    public init(position: Int, onCancel: @escaping () -> Void) {
        self.position = position
        self.onCancel = onCancel
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            HStack(spacing: AppTheme.Spacing.xs) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Icons.tertiary)
                Text("排队中 · 第 \(position) 位")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                Spacer()
                Button(action: onCancel) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 13))
                        .foregroundColor(AppTheme.Icons.tertiary)
                }
                .buttonStyle(SoftButtonStyle())
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm + 2)
            .background(AppTheme.Colors.cardBackground.opacity(0.7))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.5)
            )
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }
}

public struct StatusCardView: View {
    public let icon: String
    public let iconColor: Color
    public let title: String
    public let message: String
    public let primary: (label: String, action: () -> Void)
    public let secondary: (label: String, action: () -> Void)?

    public init(
        icon: String,
        iconColor: Color,
        title: String,
        message: String,
        primary: (label: String, action: () -> Void),
        secondary: (label: String, action: () -> Void)? = nil
    ) {
        self.icon = icon
        self.iconColor = iconColor
        self.title = title
        self.message = message
        self.primary = primary
        self.secondary = secondary
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: icon)
                        .font(.system(size: 12))
                        .foregroundColor(iconColor)
                    Text(title)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Text(message)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                HStack(spacing: AppTheme.Spacing.sm) {
                    actionChip(primary.label, primary.action)
                    if let secondary {
                        actionChip(secondary.label, secondary.action)
                    }
                }
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(iconColor.opacity(0.25), lineWidth: 0.5)
            )
            .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private func actionChip(_ label: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(AppTheme.Colors.primary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, 6)
                .background(AppTheme.Colors.primary.opacity(0.08))
                .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
    }
}

public struct DegradedCardView: View {
    public let message: String
    public let onRetry: () -> Void

    public init(message: String, onRetry: @escaping () -> Void) {
        self.message = message
        self.onRetry = onRetry
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.system(size: 12))
                    .foregroundColor(AppTheme.Icons.warning)
                    Text("服务暂时不可用")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Text(message.isEmpty ? "服务暂时不可用，请稍后重试" : message)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                retryChip
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.securityYellow.opacity(0.25), lineWidth: 0.5)
            )
            .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private var retryChip: some View {
        Button(action: onRetry) {
            HStack(spacing: 4) {
                Image(systemName: "arrow.clockwise")
                Text("重试")
            }
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(AppTheme.Icons.interactive)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, 6)
            .background(AppTheme.Colors.primary.opacity(0.08))
            .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
    }
}

public struct BackgroundProcessingCardView: View {
    public let isReconnecting: Bool
    public let confirmedRunning: Bool

    public init(isReconnecting: Bool = true, confirmedRunning: Bool = false) {
        self.isReconnecting = isReconnecting
        self.confirmedRunning = confirmedRunning
    }

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            if isReconnecting { ProgressView().controlSize(.mini) }
            Text(statusText)
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textSecondary)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(statusText)
    }

    private var statusText: String {
        if confirmedRunning { return "原任务仍在执行，结果会自动续接" }
        if isReconnecting { return "正在重新连接原任务…" }
        return "原任务进度已保留，网络恢复后会自动续接"
    }
}

public struct OrphanPendingCardView: View {
    public let onRetry: () -> Void

    public init(onRetry: @escaping () -> Void) {
        self.onRetry = onRetry
    }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            QuantumAvatarView(size: 32).padding(.top, 2)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: 6) {
                    Image(systemName: "clock.badge.exclamationmark")
                        .font(.system(size: 12))
                    .foregroundColor(AppTheme.Icons.tertiary)
                    Text("未完成")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Text("该回复在上次中断前未完成，可继续重试。")
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                retryChip
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.5)
            )
            .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
            Spacer(minLength: 44)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private var retryChip: some View {
        Button(action: onRetry) {
            HStack(spacing: 4) {
                Image(systemName: "arrow.clockwise")
                Text("继续 / 重试")
            }
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(AppTheme.Icons.interactive)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, 6)
            .background(AppTheme.Colors.primary.opacity(0.08))
            .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
    }
}

public struct KnowledgeActionCard: View {
    public let action: KnowledgeActionBlock
    public let onApply: () -> Void
    public var onCompare: (() -> Void)? = nil
    public let onDiscard: () -> Void
    public let onOpenResult: () -> Void
    public var body: some View {
        Group {
            switch action.state {
            case .proposed:
                confirmationView
            case .applying:
                progressView
            case .synced:
                completionView
            case .localApplied, .syncPending, .failed, .stale:
                recoveryView
            case .discarded:
                statusStrip("已放弃此次整理", icon: "xmark.circle", color: AppTheme.Colors.textTertiary)
            }
        }
        .foregroundStyle(AppTheme.Colors.textPrimary)
        .padding(AppTheme.Spacing.lg)
        .background(Color(hex: "FFFCF6"), in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.lg).stroke(AppTheme.Colors.border.opacity(0.72)) }
    }

    private var confirmationView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                QuantumAvatarView(size: 30)
                VStack(alignment: .leading, spacing: 3) {
                    Text("请确认以下内容")
                        .font(.system(.title3, design: .serif, weight: .bold))
                    Text("我将基于这些信息开始整理。")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
            }
            requirementSection("目标", icon: "scope", value: action.summary)
            requirementSection(
                "参考来源", icon: "doc.text",
                value: action.beforePreview.isEmpty ? "当前对话 · 已选择内容" : action.beforePreview
            )
            requirementSection(
                "输出形式", icon: "doc.badge.gearshape",
                value: action.steps.map { stepLabel($0.kind) }.joined(separator: " · ")
            )
            if action.steps.contains(where: { $0.kind == "merge_notes" && $0.sourceNoteIds.count == 1 }), let onCompare {
                Button("查看差异并调整", action: onCompare).frame(minHeight: 44)
            }
            if !action.afterPreview.isEmpty {
                requirementSection("执行后的内容", icon: "doc.text", value: action.afterPreview)
            }
            ForEach(action.steps.filter { $0.markdown?.isEmpty == false }) { step in
                DisclosureGroup("完整结果 · \(step.title ?? "笔记")") {
                    Text(step.markdown ?? "").textSelection(.enabled)
                }
            }
            if !action.markdownDiff.isEmpty {
                DisclosureGroup("修改明细") { Text(action.markdownDiff).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
            }
            cardButton("确认并开始", filled: true, action: onApply)
            Button("修改需求", action: onDiscard)
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .frame(maxWidth: .infinity)
        }
    }

    private var progressView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(spacing: AppTheme.Spacing.sm) {
                QuantumAvatarView(size: 30)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Quantum 正在为你整理…").font(AppTheme.Typography.cardTitle)
                    Text("大约需要 1–2 分钟")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
            }

            VStack(alignment: .leading, spacing: 0) {
                progressRow("理解需求", detail: "分析你的问题和关注点", state: .done, time: "00:08")
                progressRow("检索资料", detail: "来自对话与优质来源", state: .active, time: "00:24")
                progressRow("整理与生成", detail: "提炼要点、组织内容", state: .pending, time: "")
                progressRow("检查与优化", detail: "确保准确性与可读性", state: .pending, time: "")
            }

            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Label("正在检索相关资料…", systemImage: "waveform")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.Icons.interactive)
                Text("•  正在匹配当前对话与已有笔记\n•  正在筛选可追溯内容\n•  正在准备结构化笔记")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineSpacing(7)
            }
            .padding(AppTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.mistSky.opacity(0.38), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
        }
    }

    private enum ProgressState { case done, active, pending }

    private func progressRow(_ title: String, detail: String, state: ProgressState, time: String) -> some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            ZStack {
                Circle()
                    .fill(state == .done ? AppTheme.Icons.success : Color.clear)
                    .overlay { Circle().stroke(state == .active ? AppTheme.Icons.interactive : AppTheme.Colors.border, lineWidth: state == .active ? 3 : 2) }
                if state == .done { Image(systemName: "checkmark").font(.caption.bold()).foregroundStyle(.white) }
                if state == .active { Circle().fill(AppTheme.Icons.interactive).padding(6) }
            }
            .frame(width: 28, height: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(AppTheme.Typography.label)
                Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
            }
            Spacer()
            Text(time).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary)
        }
        .padding(.vertical, AppTheme.Spacing.sm)
    }

    private var completionView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            statusStrip("已保存到书架", icon: "checkmark", color: AppTheme.Icons.success)
            notePreview
            HStack(spacing: AppTheme.Spacing.sm) {
                decisionButton("保存", detail: "已存入书架", icon: "bookmark.fill", selected: true, action: onOpenResult)
                decisionButton(
                    "合并",
                    detail: didMerge ? "已与现有笔记合并" : "未执行合并",
                    icon: "arrow.triangle.merge",
                    selected: didMerge,
                    disabled: !didMerge,
                    action: onOpenResult
                )
                decisionButton("丢弃", detail: "操作已完成", icon: "trash", selected: false, disabled: true, action: {})
            }
            if action.steps.contains(where: { $0.kind == "merge_notes" }) {
                statusStrip("已合并相似内容，避免重复笔记", icon: "exclamationmark", color: AppTheme.Colors.emberOrange)
            }
            HStack {
                Label("操作已完成", systemImage: "checkmark.circle.fill")
                Spacer()
                Button("打开", action: onOpenResult)
            }
            .font(AppTheme.Typography.supporting.weight(.semibold))
            .padding(AppTheme.Spacing.md)
            .background(Color.white.opacity(0.76), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
        }
    }

    private var recoveryView: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            statusStrip(
                action.state == .stale ? "内容已变化，需要重新确认" : "同步未完成",
                icon: "exclamationmark", color: AppTheme.Colors.statusError
            )
            notePreview
            if let error = action.errorMessage, !error.isEmpty {
                Text(error).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
            }
            HStack(spacing: AppTheme.Spacing.sm) {
                cardButton("重试", filled: true, action: onApply)
                cardButton("打开本地结果", filled: false, action: onOpenResult)
            }
        }
    }

    private var notePreview: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            ZStack {
                LinearGradient(colors: [AppTheme.Colors.mistSky, AppTheme.Colors.mistMint], startPoint: .top, endPoint: .bottom)
                VStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: "mountain.2.fill").foregroundStyle(AppTheme.Icons.interactive)
                    Text(primaryTitle).font(.system(size: 12, weight: .bold, design: .serif)).multilineTextAlignment(.center)
                }.padding(8)
            }
            .frame(width: 92, height: 124)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Text(primaryTitle).font(.system(.title3, design: .serif, weight: .bold)).lineLimit(3)
                Text("\(max(action.steps.count, 1)) 条整理 · 今天")
                    .font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                HStack(spacing: 5) {
                    ForEach(primaryTags.prefix(3), id: \.self) { tag in
                        Text(tag).font(.system(size: 10, weight: .medium))
                            .padding(.horizontal, 7).padding(.vertical, 5)
                            .background(AppTheme.Colors.mistMint.opacity(0.65), in: Capsule())
                    }
                }
            }
            Spacer(minLength: 0)
        }
        .padding(AppTheme.Spacing.md)
        .background(Color.white.opacity(0.76), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
    }

    private var primaryStep: KnowledgeActionStep? {
        action.steps.first(where: { $0.kind == "create_note" || $0.kind == "create_daily_note" || $0.kind == "update_note" || $0.kind == "merge_notes" }) ?? action.steps.first
    }
    private var primaryTitle: String { primaryStep?.title ?? action.summary }
    private var primaryTags: [String] { primaryStep?.tags.isEmpty == false ? primaryStep!.tags : ["学习笔记"] }

    private func requirementSection(_ title: String, icon: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack {
                Label(title, systemImage: icon).font(AppTheme.Typography.label)
                Spacer()
                Text("编辑").font(AppTheme.Typography.micro.weight(.semibold)).foregroundStyle(AppTheme.Icons.interactive)
            }
            Text(value)
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .lineLimit(4)
                .padding(AppTheme.Spacing.md)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white.opacity(0.76), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(AppTheme.Colors.border.opacity(0.72)) }
        }
    }

    private func statusStrip(_ title: String, icon: String, color: Color) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: icon).font(.headline.bold()).foregroundStyle(.white)
                .frame(width: 38, height: 38).background(color, in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(AppTheme.Typography.cardTitle)
                Text(title == "已保存到书架" ? "知识已为你整理完成。" : action.summary)
                    .font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
            }
            Spacer()
        }
    }

    private func decisionButton(
        _ title: String,
        detail: String,
        icon: String,
        selected: Bool,
        disabled: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            VStack(spacing: 5) {
                Image(systemName: icon).font(.title3)
                Text(title).font(AppTheme.Typography.label)
                Text(detail).font(.system(size: 9)).foregroundStyle(AppTheme.Colors.textTertiary).lineLimit(2)
            }
            .frame(maxWidth: .infinity, minHeight: 92)
            .foregroundStyle(selected ? AppTheme.Icons.interactive : AppTheme.Colors.textPrimary)
            .background(selected ? AppTheme.Colors.mistSky.opacity(0.42) : Color.white.opacity(0.74), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(selected ? AppTheme.Icons.interactive : AppTheme.Colors.border) }
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .opacity(disabled ? 0.48 : 1)
    }

    private var didMerge: Bool {
        action.steps.contains { $0.kind == "merge_notes" }
    }

    private func cardButton(_ title: String, filled: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title).font(.system(size: 14, weight: .semibold)).frame(minHeight: 44)
                .frame(maxWidth: .infinity)
                .foregroundColor(filled ? .white : AppTheme.Colors.primary)
                .background(filled ? AppTheme.Colors.primary : AppTheme.Colors.primary.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        }.buttonStyle(.plain)
    }

    private func stepLabel(_ kind: String) -> String {
        ["create_note":"创建笔记", "create_daily_note":"创建日记", "update_note":"修改正文",
         "rename_note":"重命名", "set_tags":"修改标签", "set_pinned":"置顶状态",
         "add_wikilink":"增加双链", "remove_wikilink":"移除双链", "merge_notes":"合并笔记",
         "archive_note":"归档", "restore_note":"恢复", "move_to_trash":"移入废纸篓"][kind] ?? kind
    }
}

public struct CapabilityProposalCard: View {
    public let proposal: CapabilityProposalBlock
    public let onConfirm: () -> Void
    public let onDiscard: () -> Void
    @State private var showsTravelDetails = false

    public var body: some View {
        Group {
            if isTravelProposal {
                travelProposal
            } else {
                standardProposal
            }
        }
        .sheet(isPresented: $showsTravelDetails) {
            TravelPlanPreferencesView {
                showsTravelDetails = false
                onConfirm()
            }
        }
    }

    private var standardProposal: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("待确认操作", systemImage: "checkmark.shield")
                    .font(.system(size: 13, weight: .semibold))
                Spacer()
                Text(stateLabel).font(.caption.weight(.semibold))
                    .foregroundColor(AppTheme.Colors.primary)
            }
            Text(learningTitle ?? proposal.summary).font(.system(size: 16, weight: .semibold))
            if learningTitle != nil {
                if let question = proposal.input.questionId {
                    Text("第 \(question.dropFirst()) 题").font(.subheadline)
                }
                if let selected = proposal.input.selected, !selected.isEmpty {
                    Text("你的选择：" + selected.map { $0 == "T" ? "正确" : $0 == "F" ? "错误" : $0 }.joined(separator: "、"))
                }
                if let text = proposal.input.text, !text.isEmpty { Text(text).lineLimit(6) }
                if proposal.capabilityId == "learning.exercise.hint" {
                    Text("只给一点思路，不直接揭晓答案。查看后会记录借助提示，不影响分数。")
                        .font(.caption).foregroundStyle(AppTheme.Colors.textSecondary)
                }
                if proposal.state == .applying { ProgressView("正在处理，已有作答会保留…") }
            }
            if let title = proposal.input.title { Text(title).font(.subheadline) }
            if let description = proposal.input.description {
                Text(description).font(.caption).foregroundColor(AppTheme.Colors.textSecondary)
            }
            if let workflowId = proposal.input.workflowId {
                Text("工作流：\(workflowId)").font(.caption).foregroundColor(AppTheme.Colors.textSecondary)
            }
            if let sourceId = proposal.input.sourceDocumentId {
                Text("来源文档：\(sourceId)").font(.caption).foregroundColor(AppTheme.Colors.textSecondary)
            }
            if let output = proposal.input.desiredOutput {
                Text("预期输出：\(output)").font(.caption).foregroundColor(AppTheme.Colors.textSecondary)
            }
            if let kind = proposal.input.outputKind {
                Text("输出类型：\(kind)").font(.caption).foregroundColor(AppTheme.Colors.textSecondary)
            }
            if let material = proposal.input.textMaterial {
                Text("文字材料：\(material)")
                    .font(.caption)
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .lineLimit(3)
            }
            if let use = proposal.input.intendedUse {
                Text("用途：\(use)").font(.caption).foregroundColor(AppTheme.Colors.textSecondary)
            }
            if let layout = proposal.input.layoutStyle {
                Text("版式：\(layout)").font(.caption).foregroundColor(AppTheme.Colors.textSecondary)
            }
            if let error = proposal.errorMessage {
                Text(error).font(.caption).foregroundColor(.red)
            }
            if proposal.state == .awaitingConfirmation || proposal.state == .failed {
                HStack(spacing: 10) {
                    Button(proposal.state == .failed ? "重试" : "确认执行", action: onConfirm)
                        .buttonStyle(.borderedProminent)
                        .accessibilityIdentifier("capability-confirm-execute")
                    Button("放弃", action: onDiscard).buttonStyle(.bordered)
                }
            }
        }
        .padding(18)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24).stroke(AppTheme.Colors.primary.opacity(0.16)))
    }

    private var learningTitle: String? {
        switch proposal.capabilityId {
        case "learning.exercise.create": return "开始一组混合练习"
        case "learning.exercise.answer": return "保存这道题的答案"
        case "learning.exercise.hint": return "给我一点提示"
        case "learning.exercise.submit": return "提交整组答案并批改"
        default: return nil
        }
    }

    private var travelProposal: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                Label("转为旅行计划任务", systemImage: "airplane.circle.fill")
                    .font(.headline)
                Spacer()
                Image(systemName: "pencil.circle.fill")
                    .foregroundStyle(AppTheme.Icons.interactive)
            }
            Text("已根据对话内容智能提取关键信息，\n你可以修改后继续。")
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)

            VStack(spacing: 0) {
                travelRow("mappin.and.ellipse", "目的地", proposal.input.title ?? "京都 · 日本")
                Divider().padding(.leading, 42)
                travelRow("calendar", "出行时间", "2024年10月1日 – 10月5日（5天）")
                Divider().padding(.leading, 42)
                travelRow("person.2.fill", "同行人", "1–2人")
                Divider().padding(.leading, 42)
                travelRow("heart", "偏好", "经典景点、在地美食、拍照")
            }
            .background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))

            if proposal.state == .awaitingConfirmation || proposal.state == .failed {
                Button(action: { showsTravelDetails = true }) {
                    HStack {
                        Spacer()
                        Text(proposal.state == .failed ? "重新完善计划" : "继续完善计划")
                        Image(systemName: "chevron.right")
                        Spacer()
                    }
                }
                .buttonStyle(QuantumPrimaryButtonStyle())
                Button("放弃", action: onDiscard)
                    .font(AppTheme.Typography.supporting)
                    .frame(maxWidth: .infinity)
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.lg).stroke(AppTheme.Colors.border) }
    }

    private func travelRow(_ icon: String, _ title: String, _ value: String) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: icon)
                .foregroundStyle(AppTheme.Icons.interactive)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                Text(value).font(AppTheme.Typography.supporting.weight(.medium))
            }
            Spacer()
            Image(systemName: "chevron.right").font(.caption).foregroundStyle(AppTheme.Colors.textTertiary)
        }
        .padding(.horizontal, AppTheme.Spacing.sm)
        .frame(minHeight: 54)
    }

    private var isTravelProposal: Bool {
        let text = [proposal.summary, proposal.input.title, proposal.input.description,
                    proposal.input.desiredOutput, proposal.input.outputKind]
            .compactMap { $0 }.joined(separator: " ")
        return text.contains("旅行") || text.contains("京都") || text.localizedCaseInsensitiveContains("travel")
    }

    private var stateLabel: String {
        switch proposal.state {
        case .awaitingConfirmation: return "待确认"
        case .applying: return "执行中"
        case .completed: return "已完成"
        case .discarded: return "已放弃"
        case .failed: return "失败"
        }
    }
}

struct TravelPlanPreferencesView: View {
    let onGenerate: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var companion = "一个人"
    @State private var budget = "经济"
    @State private var pace = "轻松"
    @State private var interests: Set<String> = ["寺社文化", "自然风光", "在地美食", "拍照打卡"]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    Text("补充以下信息，让计划更符合你的需求。")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                    field("mappin.circle.fill", "目的地", "京都 · 日本")
                    field("calendar", "出行日期", "2024年10月1日 – 10月5日")
                    choice("person.2.fill", "同行人", ["一个人", "情侣", "朋友", "家人"], $companion)
                    choice("coins", "预算（人均）", ["经济", "适中", "舒适", "不限"], $budget)
                    choice("clock", "旅行节奏", ["轻松", "适中", "充实"], $pace)
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        Label("感兴趣的内容（可多选）", systemImage: "heart")
                            .font(AppTheme.Typography.body.weight(.semibold))
                        LazyVGrid(columns: [.init(.flexible()), .init(.flexible()), .init(.flexible())], spacing: 8) {
                            ForEach(["寺社文化", "自然风光", "在地美食", "拍照打卡", "购物", "动漫圣地", "小众体验"], id: \.self) { item in
                                Button {
                                    if interests.contains(item) { interests.remove(item) } else { interests.insert(item) }
                                } label: {
                                    Text(item + (interests.contains(item) ? " ✓" : ""))
                                        .font(AppTheme.Typography.supporting)
                                        .padding(.horizontal, 12).frame(minHeight: 34)
                                        .background(interests.contains(item) ? AppTheme.Colors.primary.opacity(0.12) : AppTheme.Colors.surfaceTint, in: Capsule())
                                        .overlay { Capsule().stroke(interests.contains(item) ? AppTheme.Colors.primary : AppTheme.Colors.border) }
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    Label("生成图片", systemImage: "photo.on.rectangle")
                        .font(AppTheme.Typography.supporting.weight(.semibold))
                        .foregroundStyle(AppTheme.Icons.interactive)
                    Label("地图搜索", systemImage: "mappin.and.ellipse")
                        .font(AppTheme.Typography.supporting.weight(.semibold))
                        .foregroundStyle(AppTheme.Icons.interactive)
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .navigationTitle("完善旅行计划")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } } }
            .safeAreaInset(edge: .bottom) {
                Button("✦  生成我的旅行计划", action: onGenerate)
                    .buttonStyle(QuantumPrimaryButtonStyle())
                    .padding(AppTheme.Metrics.contentGutter)
                    .background(.ultraThinMaterial)
            }
        }
    }

    private func field(_ icon: String, _ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Label(title, systemImage: icon).font(AppTheme.Typography.body.weight(.semibold))
            HStack { Text(value); Spacer(); Image(systemName: "chevron.right").foregroundStyle(AppTheme.Colors.textTertiary) }
                .font(AppTheme.Typography.supporting)
                .padding(.horizontal, AppTheme.Spacing.md).frame(minHeight: 44)
                .background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
        }
    }

    private func choice(_ icon: String, _ title: String, _ values: [String], _ selection: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Label(title, systemImage: icon).font(AppTheme.Typography.body.weight(.semibold))
            HStack(spacing: AppTheme.Spacing.sm) {
                ForEach(values, id: \.self) { value in
                    Button(value) { selection.wrappedValue = value }
                        .font(AppTheme.Typography.supporting)
                        .frame(maxWidth: .infinity, minHeight: 38)
                        .background(selection.wrappedValue == value ? AppTheme.Colors.primary.opacity(0.12) : AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.sm).stroke(selection.wrappedValue == value ? AppTheme.Colors.primary : .clear) }
                        .buttonStyle(.plain)
                }
            }
        }
    }
}

struct TravelPlanningAnswerCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Text("京都是一座把传统与现代完美融合的城市。为你推荐一个 5 天的行程思路，涵盖经典景点、在地体验和美食，节奏舒适，适合第一次去。")
                .font(AppTheme.Typography.body)
            HStack(spacing: 3) {
                photo("travel_kyoto_bridge", "清水寺", "京都的必访地标")
                photo("travel_kyoto_street", "伏见稻荷大社", "千本鸟居的震撼")
                photo("travel_kyoto_bamboo", "岚山", "竹林与渡月桥")
            }
            Text("5 天行程概览").font(.headline)
            VStack(spacing: 0) {
                itinerary("第 1 天", "抵达京都 · 城市初探")
                itinerary("第 2 天", "东山经典 · 寺社巡礼")
                itinerary("第 3 天", "岚山自然 · 健康野风光")
                itinerary("第 4 天", "宇治一日 · 茶香与古韵")
                itinerary("第 5 天", "自由探索 · 购物与美食")
            }
            .background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
            Text("参考来源").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
            HStack {
                source("日本观光局")
                source("京都市旅游官网")
                source("Lonely Planet")
            }
        }
    }

    private func photo(_ image: String, _ title: String, _ subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Image(image).resizable().scaledToFill().frame(height: 104).clipped()
            Text(title).font(.caption.weight(.semibold)).lineLimit(1)
            Text(subtitle).font(.system(size: 9)).foregroundStyle(AppTheme.Colors.textTertiary).lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func itinerary(_ day: String, _ detail: String) -> some View {
        HStack { Text(day).foregroundStyle(AppTheme.Icons.interactive).frame(width: 56); Text(detail); Spacer() }
            .font(AppTheme.Typography.supporting)
            .padding(.horizontal, AppTheme.Spacing.sm).frame(minHeight: 34)
    }

    private func source(_ title: String) -> some View {
        Text(title).font(AppTheme.Typography.micro).lineLimit(1)
            .padding(.horizontal, 9).frame(minHeight: 28)
            .background(AppTheme.Colors.mistSky, in: Capsule())
    }
}

struct TravelWorkflowPlanView: View {
    let onStart: () -> Void
    private let steps: [(String, String, String)] = [
        ("binoculars.fill", "目的地研究", "目的地概况 · 最佳季节 · 注意事项"),
        ("point.topleft.down.curvedto.point.bottomright.up", "行程路线规划", "5 天行程 · 地图路线 · 交通建议"),
        ("house.and.flag.fill", "景点推荐", "必去景点 · 小众选择 · 预约信息"),
        ("camera.fill", "拍照建议", "机位推荐 · 最佳时间 · 拍摄技巧"),
        ("bed.double.fill", "住宿推荐", "区域选择 · 酒店建议 · 预订贴士"),
        ("fork.knife", "美食推荐", "在地美食 · 特色餐厅 · 必吃清单"),
        ("tram.fill", "交通指南", "机场到市区 · 市内交通 · 交通卡"),
        ("shield.fill", "安全与应急", "常见问题 · 紧急联系 · 旅行贴士"),
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    Text("旅行计划").font(AppTheme.Typography.screenTitle)
                    Text("已为你生成完整的规划方案，\n包含行程安排、地图、景点与实用建议。")
                        .font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
                    ForEach(steps.indices, id: \.self) { index in
                        stepRow(index, steps[index])
                    }
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .toolbar { ToolbarItem(placement: .topBarLeading) { Button("返回", systemImage: "chevron.left") {} } }
            .safeAreaInset(edge: .bottom) {
                Button("▶  确认开始", action: onStart)
                    .buttonStyle(QuantumPrimaryButtonStyle())
                    .padding(AppTheme.Metrics.contentGutter)
                    .background(.ultraThinMaterial)
            }
        }
    }

    private func stepRow(_ index: Int, _ step: (String, String, String)) -> some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Text("\(index + 1)").font(.caption.bold()).foregroundStyle(.white)
                .frame(width: 26, height: 26)
                .background(index.isMultiple(of: 2) ? AppTheme.Colors.quantumViolet : AppTheme.Colors.quantumBlue, in: Circle())
            Image(systemName: step.0).foregroundStyle(AppTheme.Icons.interactive).frame(width: 30, height: 30)
                .background(AppTheme.Colors.primary.opacity(0.08), in: Circle())
            VStack(alignment: .leading, spacing: 3) {
                Text(step.1).font(AppTheme.Typography.body.weight(.semibold))
                Text(step.2).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
            }
            Spacer()
            Image(systemName: "chevron.right").font(.caption).foregroundStyle(AppTheme.Colors.textTertiary)
        }
        .padding(AppTheme.Spacing.sm)
        .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(AppTheme.Colors.border) }
    }
}

#if DEBUG
struct V4TravelPrototypeHost: View {
    let pageID: String
    @State private var draft = ""
    @State private var quote: QuotedContext?
    @State private var isVoicePressing = false
    @StateObject private var speechService = SpeechRecognizerService()

    var body: some View {
        if pageID.hasSuffix("p03") {
            TravelPlanPreferencesView(onGenerate: {})
        } else if pageID.hasSuffix("p04") {
            TravelWorkflowPlanView(onStart: {})
        } else {
            ZStack {
                QuantumMistBackground()
                VStack(spacing: 0) {
                    ChatTopBarView(isGenerating: false, title: "Quantum", onTitleTap: {}, onNewSession: {}, onHistoryTap: {}, onClearTap: {})
                    ScrollView {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                            Text(pageID.hasSuffix("p02") ? "帮我完成旅行计划" : "第一次去京都，五天怎么玩？")
                                .font(AppTheme.Typography.body)
                                .padding(AppTheme.Spacing.md)
                                .background(AppTheme.Colors.mistSky, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                                .frame(maxWidth: .infinity, alignment: .trailing)
                            HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                                QuantumAvatarView(size: 34)
                                if pageID.hasSuffix("p02") {
                                    VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                                        Text("好的！我将根据我们的对话内容，为你创建旅行计划任务。")
                                        CapabilityProposalCard(proposal: Self.proposal, onConfirm: {}, onDiscard: {})
                                        Text("可以继续补充更多偏好，或直接开始规划完整的旅行计划。")
                                            .font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
                                            .padding(AppTheme.Spacing.md).background(AppTheme.Colors.mistSky, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                                    }
                                } else {
                                    TravelPlanningAnswerCard()
                                }
                            }
                        }
                        .padding(AppTheme.Metrics.contentGutter)
                    }
                    ChatInputBar(inputText: $draft, quotedContext: $quote, isVoicePressing: $isVoicePressing,
                                 speechService: speechService, isGenerating: false, dismissKeyboardToken: 0,
                                 onSend: {}, onVoicePressChanged: { _ in }, onPlusTap: {})
                }
            }
        }
    }

    private static let proposal = CapabilityProposalBlock(
        id: "travel-plan-preview", capabilityId: "workflow.create",
        input: CapabilityProposalInput(
            title: "京都 · 日本", description: "京都五日旅行计划", desiredOutput: "图文旅行计划",
            sourceDocumentId: nil, outputKind: "travel_plan", workflowId: nil, textMaterial: nil,
            audience: nil, intendedUse: nil, layoutStyle: nil, slideCount: nil, clarificationStrategy: nil,
            researchQuestion: nil, thesis: nil, language: nil, citationStyle: nil, evidencePolicy: nil
        ),
        summary: "创建旅行计划", risk: "将创建新的工作流"
    )
}
#endif
