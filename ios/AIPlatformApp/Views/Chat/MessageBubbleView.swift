//
//  MessageBubbleView.swift
//  AIPlatformApp
//
//  Markdown Message Bubble with Syntax-Highlighted Code Cards, Math Formulas & Context Menu
//  统一 blocks 数组序渲染 7 类块 + 真实思维链卡片 + 富媒体引用上下文
//  ChatGPT / Claude 规范：思维链胶囊置顶 -> 正文卡片居中 -> 操作条在底部（有正文时才展示）
//

import SwiftUI

enum StreamTextChunker {
    static func chunks(_ text: String, size: Int = 1_600) -> [String] {
        guard !text.isEmpty, size > 0 else { return [] }
        var result: [String] = []
        var start = text.startIndex
        while start < text.endIndex {
            let end = text.index(start, offsetBy: size, limitedBy: text.endIndex)
                ?? text.endIndex
            result.append(String(text[start..<end]))
            start = end
        }
        return result
    }
}

struct BoundedTextPreview: Equatable {
    let content: String
    let omittedPrefix: Bool
}

enum LongMessagePresentation {
    static let longAnswerCharacterThreshold = 4_000
    static let streamingCharacterLimit = 2_400
    static let streamingExpansionStep = 2_400
    static let collapsedCharacterLimit = 640

    static func isLong(_ text: String, limit: Int = longAnswerCharacterThreshold) -> Bool {
        guard limit >= 0 else { return true }
        guard let boundary = text.index(
            text.startIndex,
            offsetBy: limit,
            limitedBy: text.endIndex
        ) else { return false }
        return boundary != text.endIndex
    }

    static func streamingPreview(_ text: String, limit: Int = streamingCharacterLimit) -> BoundedTextPreview {
        guard limit > 0 else {
            return BoundedTextPreview(content: "", omittedPrefix: !text.isEmpty)
        }
        guard isLong(text, limit: limit) else {
            return BoundedTextPreview(content: text, omittedPrefix: false)
        }
        let start = text.index(text.endIndex, offsetBy: -limit)
        return BoundedTextPreview(content: String(text[start...]), omittedPrefix: true)
    }

    static func collapsedPreview(_ text: String, limit: Int = collapsedCharacterLimit) -> String {
        guard limit > 0 else { return "" }
        guard isLong(text, limit: limit) else { return text }
        let boundary = text.index(text.startIndex, offsetBy: limit)
        let rawPrefix = String(text[..<boundary])
        let minimumBoundary = rawPrefix.index(
            rawPrefix.startIndex,
            offsetBy: max(0, limit / 2),
            limitedBy: rawPrefix.endIndex
        ) ?? rawPrefix.startIndex
        if let paragraphBreak = rawPrefix.range(of: "\n\n", options: .backwards),
           paragraphBreak.lowerBound >= minimumBoundary {
            return String(rawPrefix[..<paragraphBreak.lowerBound])
        }
        return rawPrefix
    }

    static func nextStreamingLimit(current: Int, contentCount: Int) -> Int {
        guard current < contentCount else { return max(0, contentCount) }
        return current + min(streamingExpansionStep, contentCount - current)
    }
}

enum ChatStreamingPerformancePolicy {
    static func shouldPublishImmediately(publishedUTF8Count: Int) -> Bool {
        publishedUTF8Count == 0
    }

    static func flushDelayNanoseconds(currentUTF8Count: Int) -> UInt64 {
        switch currentUTF8Count {
        case ..<4_000: return 160_000_000
        case ..<12_000: return 250_000_000
        default: return 400_000_000
        }
    }

    static func typewriterBatchSize(totalCharacterCount: Int) -> Int {
        guard totalCharacterCount > 0 else { return 1 }
        return max(3, (totalCharacterCount + 23) / 24)
    }

    static let typewriterDelayNanoseconds: UInt64 = 50_000_000
}

public struct MessageBubbleView: View {
    public let message: ChatMessage
    public var context: PluginRenderContext? = nil
    public var onQuoteFollowUp: ((QuotedContext) -> Void)? = nil
    public var onRegenerate: ((String) -> Void)? = nil
    public var onStartTopic: ((ChatMessage) -> Void)? = nil
    public var reasoningInitiallyExpanded: Bool = false
    public var reasoningSummary: String? = nil

    @State private var isCopied: Bool = false
    @State private var quoteFragmentDraft = ""
    @State private var isChoosingQuoteFragment = false
    @State private var isShowingFullAnswer = false
    @State private var streamingCharacterLimit = LongMessagePresentation.streamingCharacterLimit

    public init(
        message: ChatMessage,
        context: PluginRenderContext? = nil,
        onQuoteFollowUp: ((QuotedContext) -> Void)? = nil,
        onRegenerate: ((String) -> Void)? = nil,
        onStartTopic: ((ChatMessage) -> Void)? = nil,
        reasoningInitiallyExpanded: Bool = false,
        reasoningSummary: String? = nil
    ) {
        self.message = message
        self.context = context
        self.onQuoteFollowUp = onQuoteFollowUp
        self.onRegenerate = onRegenerate
        self.onStartTopic = onStartTopic
        self.reasoningInitiallyExpanded = reasoningInitiallyExpanded
        self.reasoningSummary = reasoningSummary
    }

    public var body: some View {
        Group {
            if message.role == .user {
                HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                    Spacer(minLength: 44)
                    userBubbleContent
                }
            } else if usesReportPresentation {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        assistantAvatarView
                        Text("Quantum")
                            .font(AppTheme.Typography.label.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                    }
                    assistantBubbleContent
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                    assistantAvatarView
                    assistantBubbleContent
                    Spacer(minLength: 44)
                }
            }
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(message.role == .user ? "selected-book-chat-request" : "selected-book-chat-response")
        .sheet(isPresented: $isChoosingQuoteFragment) {
            QuoteFragmentPicker(sourceText: message.content, text: $quoteFragmentDraft) {
                let fragment = quoteFragmentDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                if !fragment.isEmpty { onQuoteFollowUp?(QuotedContext(text: fragment)) }
                isChoosingQuoteFragment = false
            }
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $isShowingFullAnswer) {
            LongAnswerSheet(
                messageId: message.id, content: message.content,
                serverBlocks: message.answerBlocks,
                availableBlockCount: message.answerAvailableBlockCount,
                hasMore: message.answerHasMore,
                isRunning: message.pending || message.isStreaming,
                fetchFull: context?.onFetchFullAnswer
            )
        }
    }

    // MARK: - User Bubble
    private var userBubbleContent: some View {
        VStack(alignment: .trailing, spacing: AppTheme.Spacing.xs) {
            if let quoted = message.quotedContext {
                quotedHeaderView(quoted)
            }

            if userAttachmentBlocks.isEmpty {
                Text(message.content)
                    .font(AppTheme.Typography.body)
                    .foregroundColor(AppTheme.Colors.onPrimary)
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.vertical, AppTheme.Spacing.sm + 2)
                    .background(AppTheme.Colors.userBubbleGradient)
                    .clipShape(
                        RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    )
                    .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
                    .shadow(color: Color.black.opacity(0.06), radius: 5, x: 0, y: 2)
                    .contextMenu {
                        contextMenuActions
                    }
            } else {
                ForEach(userAttachmentBlocks) { block in
                    blockCard(block)
                }
            }
        }
    }

    private var userAttachmentBlocks: [MessageBlock] {
        message.blocks.filter { if case .attachment = $0 { return true }; return false }
    }

    // MARK: - Assistant Bubble
    private var assistantAvatarView: some View {
        QuantumAvatarView(size: 28)
            .padding(.top, 4)
    }

    private var assistantBubbleContent: some View {
        let trimmed = message.content.trimmingCharacters(in: .whitespacesAndNewlines)
        let assistantName = message.executingAgentName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            if let name = message.executingAgentName,
               message.executingAgentId != "main_agent" {
                HStack(spacing: 5) {
                    Image(systemName: "person.crop.circle.badge.checkmark")
                    Text(message.delegatedBy == nil ? name : "由 \(name) 完成")
                }
                .font(AppTheme.Typography.micro.weight(.semibold))
                .foregroundColor(AppTheme.Colors.quantumBlue)
                .padding(.horizontal, AppTheme.Spacing.sm)
                .padding(.vertical, 4)
                .background(AppTheme.Colors.surfaceTint, in: Capsule())
                .accessibilityLabel("执行 Agent：\(name)")
            }

            // 演示样例标注
            if message.isDemoSample {
                demoSampleBadge
            }

            // 1. 运行中用单一状态卡承载真实过程；完成后恢复紧凑思维胶囊。
            if let reasoningBlock = message.blocks.first(where: { if case .reasoning = $0 { return true }; return false }) {
                if message.isStreaming || message.pending {
                    if assistantName.isEmpty || message.executingAgentId == "main_agent" {
                        Text(assistantName.isEmpty ? ChatRunningPresentation.fallbackAssistantName : assistantName)
                            .font(AppTheme.Typography.micro.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.interactiveViolet)
                    }
                    ChatRunningStatusCard(
                        presentation: ChatRunningPresentation(
                            assistantName: message.executingAgentName,
                            phase: nil,
                            phaseDetail: nil,
                            progress: nil,
                            steps: message.reasoningSteps
                        ),
                        steps: message.reasoningSteps
                    )
                } else {
                    blockCard(reasoningBlock)
                }
            }

            // 2. Markdown 正文卡片（正文非空 或 流式中）
            if !trimmed.isEmpty || message.isStreaming {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    if message.isStreaming, !trimmed.isEmpty {
                        // Stable chunks keep old layout nodes unchanged while only
                        // a bounded tail grows. Keeping the rendered subtree capped
                        // prevents a very long answer from monopolizing layout.
                        if streamingPreview.omittedPrefix {
                            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                                Label("前文已折叠，Hermes 仍在后台生成", systemImage: "text.append")
                                    .font(AppTheme.Typography.supporting.weight(.medium))
                                    .foregroundStyle(AppTheme.Colors.textSecondary)
                                Button {
                                    streamingCharacterLimit = LongMessagePresentation.nextStreamingLimit(
                                        current: streamingCharacterLimit,
                                        contentCount: message.content.count
                                    )
                                } label: {
                                    Label("向前展开一部分", systemImage: "chevron.up")
                                        .font(AppTheme.Typography.supporting.weight(.semibold))
                                }
                                .buttonStyle(SoftButtonStyle())
                                .accessibilityHint("每次多显示一段已收到的内容，不影响 Hermes 继续生成")
                            }
                        }
                        ForEach(Array(streamingTextChunks.enumerated()), id: \.offset) { _, chunk in
                            Text(chunk)
                                .font(AppTheme.Typography.body)
                                .foregroundColor(AppTheme.Colors.textPrimary)
                        }
                    } else if !completedMarkdownBlocks.isEmpty {
                        // MarkdownBlock.id is content-derived; use parse order as
                        // local identity so repeated paragraphs stay distinct.
                        if isLongCompletedAnswer || completedMarkdownBlocks.prefersSectionCards {
                            ReadingCardDeck(blocks: completedMarkdownBlocks)
                        } else {
                            ForEach(Array(completedMarkdownBlocks.enumerated()), id: \.offset) { _, block in
                                MarkdownBlockCard(block: block)
                            }
                        }
                    } else if !trimmed.isEmpty {
                        Text(completedDisplayContent)
                            .font(AppTheme.Typography.body)
                            .foregroundColor(AppTheme.Colors.textPrimary)
                    }

                    if isLongCompletedAnswer || message.answerHasMore {
                        Button {
                            isShowingFullAnswer = true
                        } label: {
                            HStack(spacing: AppTheme.Spacing.xs) {
                                Text(message.answerHasMore ? "查看并加载原文" : "展开全文")
                                Image(systemName: "arrow.up.left.and.arrow.down.right")
                            }
                            .font(AppTheme.Typography.supporting.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .background(AppTheme.Colors.surfaceTint, in: Capsule())
                        }
                        .buttonStyle(SoftButtonStyle())
                        .accessibilityHint("在独立页面中查看完整回答")
                    }

                    if message.isStreaming {
                        streamingCursorView
                    }
                }
                .padding(.horizontal, usesReportPresentation ? 0 : AppTheme.Spacing.md)
                .padding(.vertical, usesReportPresentation ? AppTheme.Spacing.sm : AppTheme.Spacing.md)
                .background(usesReportPresentation ? Color.clear : AppTheme.Colors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: usesReportPresentation ? 0 : AppTheme.Radius.lg, style: .continuous))
                .overlay {
                    if !usesReportPresentation {
                        RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                            .stroke(AppTheme.Colors.assistantBubbleBorder.opacity(0.18), lineWidth: 0.5)
                    }
                }
            }

            // 3. 其他富媒体块（非 reasoning，如表格、图表、代码、澄清卡等）
            ForEach(message.blocks.filter { if case .reasoning = $0 { return false }; return true }) { block in
                blockCard(block)
            }

            // 4. 空气泡兜底（正文为空且非流式非待办且无澄清卡）：显式给出异常提示 + 重新生成（绝不只露底部操作条）
            if message.shouldShowEmptyResponseError {
                HStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.system(size: 14))
                    .foregroundColor(AppTheme.Icons.warning)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("回答为空")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(AppTheme.Colors.textPrimary)
                        Text("任务已结束，但没有返回正文或可显示结果")
                            .font(.system(size: 11))
                            .foregroundColor(AppTheme.Colors.textSecondary)
                    }
                    Spacer()
                    Button(action: { onRegenerate?(message.id) }) {
                        HStack(spacing: 4) {
                            Image(systemName: "arrow.clockwise")
                            Text("重新生成")
                        }
                        .font(.system(size: 12, weight: .semibold))
            .foregroundColor(AppTheme.Icons.interactive)
                        .padding(.horizontal, AppTheme.Spacing.sm + 2)
                        .padding(.vertical, 6)
                        .background(AppTheme.Colors.primary.opacity(0.08))
                        .clipShape(Capsule())
                    }
                    .buttonStyle(SoftButtonStyle())
                }
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm + 2)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                        .stroke(AppTheme.Colors.border, lineWidth: 0.5)
                )
                .pressBorderGlow(cornerRadius: AppTheme.Radius.md)
            }

            // 5. ChatGPT 风格气泡操作条（仅在正文非空且已完成时展示，绝不单独裸露）
            if message.role == .assistant && !trimmed.isEmpty && !message.isStreaming && !message.pending {
                BubbleActionBar(
                    messageId: message.id,
                    content: message.content,
                    onRegenerate: { onRegenerate?(message.id) }
                )
                .padding(.leading, 4)
            }
        }
        .contextMenu {
            contextMenuActions
        }
    }

    /// 流式期不解析 Markdown；完成态短回答解析全文，长回答只解析有界预览。
    private var isLongCompletedAnswer: Bool {
        !message.isStreaming && LongMessagePresentation.isLong(message.content)
    }

    private var usesReportPresentation: Bool {
        !message.isStreaming && (isLongCompletedAnswer || completedMarkdownBlocks.prefersSectionCards)
    }

    private var completedDisplayContent: String {
        isLongCompletedAnswer
            ? LongMessagePresentation.collapsedPreview(message.content)
            : message.content
    }

    private var completedMarkdownBlocks: [MarkdownBlock] {
        guard !message.isStreaming, !message.content.isEmpty else { return [] }
        let suffix = isLongCompletedAnswer
            ? "collapsed_\(completedDisplayContent.hashValue)"
            : "done_\(message.content.hashValue)"
        return MarkdownBlockParser.shared.parse(completedDisplayContent, messageId: "\(message.id)_\(suffix)")
    }

    private var streamingPreview: BoundedTextPreview {
        LongMessagePresentation.streamingPreview(
            message.content,
            limit: streamingCharacterLimit
        )
    }

    private var streamingTextChunks: [String] {
        StreamTextChunker.chunks(streamingPreview.content)
    }

    // MARK: - 演示样例标注
    private var demoSampleBadge: some View {
        HStack(spacing: 4) {
            Image(systemName: "sparkles")
                .font(.system(size: 10, weight: .bold))
            Text("演示样例")
                .font(.system(size: 10, weight: .bold))
        }
            .foregroundColor(AppTheme.Icons.intelligence)
        .padding(.horizontal, AppTheme.Spacing.sm)
        .padding(.vertical, 3)
        .background(AppTheme.Colors.primary.opacity(0.08))
        .clipShape(Capsule())
    }

    // MARK: - 块分发（委托 BlockCardDispatcher 静态分发）
    @ViewBuilder
    private func blockCard(_ block: MessageBlock) -> some View {
        BlockCardDispatcher(
            block: block,
            isStreaming: message.isStreaming,
            reasoningDuration: message.reasoningDuration,
            reasoningInitiallyExpanded: reasoningInitiallyExpanded,
            reasoningSummary: reasoningSummary,
            onClarifySubmit: { selection in
                context?.onClarifySubmit?(selection)
            },
            onNoteDraftAction: { draftId, action in
                context?.onNoteDraftAction?(draftId, action)
            },
            onKnowledgeAction: { actionId, action in
                context?.onKnowledgeAction?(actionId, action)
            },
            onCapabilityProposal: { proposalId, action in
                context?.onCapabilityProposal?(proposalId, action)
            },
            onWorkflowOpen: { workflowId in
                context?.onWorkflowOpen?(workflowId)
            },
            onKnowledgeNavigation: { target in
                context?.onKnowledgeNavigation?(target)
            }
        )
    }

    // MARK: - Subcomponents

    private func quotedHeaderView(_ quote: QuotedContext) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: AppTheme.Spacing.xs) {
                Rectangle()
                    .fill(AppTheme.Colors.accent)
                    .frame(width: 3)

                Text(quote.text)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
                    .lineLimit(2)
            }
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, 4)
            .background(AppTheme.Colors.primary.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xs))
        }
    }

    private var streamingCursorView: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(AppTheme.Colors.quantumCyan)
                .frame(width: 6, height: 6)
                .opacity(0.85)
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private var contextMenuActions: some View {
        Button {
            if message.answerHasMore { isShowingFullAnswer = true }
            else { copyToClipboard() }
        } label: {
            Label(
                message.answerHasMore ? "打开全文后复制" : (isCopied ? "已复制" : "复制全文"),
                systemImage: isCopied ? "checkmark" : "doc.on.doc"
            )
        }

        if let quoteAction = onQuoteFollowUp, !message.content.isEmpty {
            Button(action: {
                quoteAction(QuotedContext(text: message.content))
            }) {
                Label(message.answerHasMore ? "引用已加载内容追问" : "引用全文追问", systemImage: "quote.bubble")
            }
            Button {
                quoteFragmentDraft = ""
                isChoosingQuoteFragment = true
            } label: {
                Label("选择片段引用", systemImage: "selection.pin.in.out")
            }
        }

        if let onStartTopic, !message.content.isEmpty, !message.isStreaming {
            Button(action: { onStartTopic(message) }) {
                Label("开启针对性话题", systemImage: "bubble.left.and.bubble.right")
            }
        }

        if message.role == .assistant, let regenAction = onRegenerate {
            Button(action: { regenAction(message.id) }) {
                Label("重新生成", systemImage: "arrow.clockwise")
            }
        }
    }

    private func copyToClipboard() {
        #if os(iOS)
        UIPasteboard.general.string = message.content
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        #endif
        isCopied = true
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            isCopied = false
        }
    }
}

enum LongAnswerPresentationState: Equatable {
    case waiting
    case partial
    case completed
    case empty
}

struct LongAnswerSheet: View {
    let messageId: String
    let content: String
    let serverBlocks: [AnswerBlockDTO]
    let availableBlockCount: Int
    let hasMore: Bool
    let isRunning: Bool
    let fetchFull: ((String) async throws -> String)?
    @Environment(\.dismiss) private var dismiss
    @State private var isCopied = false
    @State private var isLoadingFullAnswer = false
    @State private var wantsFullAnswer = false
    @State private var loadError: String?
    @State private var readingBlockIndex: Int?
    @State private var loadTask: Task<Void, Never>?

    private var stableBlocks: [AnswerBlockDTO] {
        Self.coalescedBlocks(content: content, serverBlocks: serverBlocks)
    }

    private var presentationState: LongAnswerPresentationState {
        Self.presentationState(content: content, serverBlocks: serverBlocks, isRunning: isRunning)
    }

    private var hasVisibleContent: Bool {
        presentationState == .partial || presentationState == .completed
    }

    static func presentationState(
        content: String,
        serverBlocks: [AnswerBlockDTO],
        isRunning: Bool
    ) -> LongAnswerPresentationState {
        let hasContent = !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || serverBlocks.contains { !$0.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        if isRunning { return hasContent ? .partial : .waiting }
        return hasContent ? .completed : .empty
    }

    static func coalescedBlocks(
        content: String, serverBlocks: [AnswerBlockDTO]
    ) -> [AnswerBlockDTO] {
        let source = serverBlocks.isEmpty
            ? [.init(blockIndex: 0, kind: "markdown", content: content)]
            : serverBlocks
        return source.reduce(into: [AnswerBlockDTO]()) { result, block in
            if let previous = result.last,
               previous.kind.hasPrefix("table"), block.kind.hasPrefix("table") {
                result[result.count - 1] = .init(
                    blockIndex: previous.blockIndex,
                    kind: "table",
                    content: previous.content + block.content
                )
            } else if let previous = result.last,
                      previous.kind.hasPrefix("markdown"), block.kind.hasPrefix("markdown") {
                result[result.count - 1] = .init(
                    blockIndex: previous.blockIndex,
                    kind: "markdown",
                    content: previous.content + "\n\n" + block.content
                )
            } else {
                result.append(block)
            }
        }
    }

    private var progressText: String {
        max(availableBlockCount, serverBlocks.count) > 0
            ? "已加载 \(serverBlocks.count) / \(max(availableBlockCount, serverBlocks.count)) 个内容块"
            : "已加载 \(serverBlocks.count) 个内容块"
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    if presentationState == .waiting {
                        QuantumReaderWaitingView()
                    } else {
                        ForEach(stableBlocks, id: \.blockIndex) { block in
                            StableAnswerBlockView(messageId: messageId, block: block)
                                .id(block.blockIndex)
                        }
                        readerStatus
                    }
                }
                .scrollTargetLayout()
                .textSelection(.enabled)
                .frame(maxWidth: AppTheme.Metrics.readableContentWidth, alignment: .leading)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(AppTheme.Spacing.md)
            }
            .scrollPosition(id: $readingBlockIndex, anchor: .top)
            .background(Color(hex: "FCFBF7").ignoresSafeArea())
            .navigationTitle("回答详情")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("关闭") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        prepareFullAnswer(share: false)
                    } label: {
                        Label(isCopied ? "已复制" : "复制全文", systemImage: isCopied ? "checkmark" : "doc.on.doc")
                    }
                    .disabled(!hasVisibleContent || hasMore || isRunning || isLoadingFullAnswer)
                    .accessibilityHint(hasMore ? "请先加载完整原文" : "复制完整回答到剪贴板")
                    Button { prepareFullAnswer(share: true) } label: {
                        Label("导出全文", systemImage: "square.and.arrow.up")
                    }
                    .disabled(!hasVisibleContent || hasMore || isRunning || isLoadingFullAnswer)
                }
            }
        }
        .onChange(of: isRunning) { _, running in
            if wantsFullAnswer, !running { startFullLoad() }
        }
        .onChange(of: hasMore) { _, more in
            if wantsFullAnswer, more, !isRunning { startFullLoad() }
        }
        .onDisappear { loadTask?.cancel() }
    }

    @ViewBuilder
    private var readerStatus: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            if availableBlockCount > 0 || !serverBlocks.isEmpty {
                Text(progressText)
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
            if let loadError {
                Label(loadError, systemImage: "exclamationmark.triangle")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Icons.warning)
            }
            if isLoadingFullAnswer {
                HStack {
                    ProgressView()
                    Text("正在读取已存储原文…")
                    Spacer()
                    Button("取消") { cancelFullLoad() }
                        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                }
            } else if presentationState == .partial && wantsFullAnswer {
                HStack {
                    Label("等待回答完成后继续加载", systemImage: "clock")
                    Spacer()
                    Button("取消") { wantsFullAnswer = false }
                        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                }
            } else if presentationState == .partial {
                Label("正在同步后续内容", systemImage: "arrow.triangle.2.circlepath")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .accessibilityLabel("原文正在同步后续内容")
            } else if presentationState == .completed && hasMore {
                Button("加载完整原文") {
                    wantsFullAnswer = true
                    startFullLoad()
                }
                .frame(maxWidth: .infinity, minHeight: 44)
                .accessibilityHint("依次读取全部已存储页面，不会重新生成回答")
            } else if wantsFullAnswer {
                Label("完整原文已加载", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(AppTheme.Icons.success)
            } else if presentationState == .empty {
                Text("暂时没有可显示的原文")
                    .font(AppTheme.Typography.body)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func startFullLoad() {
        guard !isRunning, hasMore, loadTask == nil else { return }
        guard let fetchFull else {
            loadError = "当前回答无法继续加载"
            return
        }
        loadError = nil
        isLoadingFullAnswer = true
        loadTask = Task { @MainActor in
            defer {
                isLoadingFullAnswer = false
                loadTask = nil
            }
            do {
                _ = try await fetchFull(messageId)
            } catch is CancellationError {
                return
            } catch {
                loadError = "加载中断，已保留当前内容，可继续重试"
            }
        }
    }

    private func cancelFullLoad() {
        wantsFullAnswer = false
        loadTask?.cancel()
    }

    private func prepareFullAnswer(share: Bool) {
        guard !hasMore, !isRunning else { return }
        #if os(iOS)
        if share {
            guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first,
                  let presenter = scene.windows.first(where: \.isKeyWindow)?.rootViewController else { return }
            presenter.present(UIActivityViewController(activityItems: [content], applicationActivities: nil), animated: true)
        } else {
            UIPasteboard.general.string = content
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
            isCopied = true
        }
        #endif
    }
}

struct QuantumReaderWaitingView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var rotation = 0.0

    static func shouldAnimate(reduceMotion: Bool) -> Bool { !reduceMotion }

    var body: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            ZStack {
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                AppTheme.Colors.quantumViolet.opacity(0.14),
                                AppTheme.Colors.quantumCyan.opacity(0.05),
                                .clear
                            ],
                            center: .center,
                            startRadius: 2,
                            endRadius: 38
                        )
                    )

                Circle()
                    .trim(from: 0.08, to: 0.68)
                    .stroke(
                        AngularGradient(
                            colors: [AppTheme.Colors.quantumCyan, AppTheme.Colors.quantumViolet],
                            center: .center
                        ),
                        style: StrokeStyle(lineWidth: 2, lineCap: .round)
                    )
                    .padding(5)
                    .rotationEffect(.degrees(rotation))

                QuantumAvatarView(size: 30)
            }
            .frame(width: 72, height: 72)
            .accessibilityHidden(true)

            Text("原文生成中")
                .font(AppTheme.Typography.cardTitle)
                .foregroundStyle(AppTheme.Colors.textPrimary)
            Text("内容到达后会自动显示，你可以先返回聊天")
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, minHeight: 320)
        .padding(AppTheme.Spacing.xl)
        .onAppear {
            guard Self.shouldAnimate(reduceMotion: reduceMotion) else { return }
            withAnimation(.linear(duration: 2.8).repeatForever(autoreverses: false)) {
                rotation = 360
            }
        }
        .onDisappear { rotation = 0 }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("原文生成中，内容到达后会自动显示")
    }
}

struct StableAnswerBlockView: View {
    let messageId: String
    let block: AnswerBlockDTO

    var body: some View {
        if block.kind.hasPrefix("table") {
            ForEach(MarkdownBlockParser.shared.parse(
                block.content, messageId: "\(messageId)_table_\(block.blockIndex)"
            )) { parsed in
                MarkdownBlockCard(block: parsed)
            }
        } else if block.kind.hasPrefix("code") {
            StructuredAnswerBlockView(kind: block.kind, content: block.content)
        } else {
            ReadingCardDeck(blocks: MarkdownBlockParser.shared.parse(
                block.content, messageId: "\(messageId)_block_\(block.blockIndex)"
            ))
        }
    }
}

private struct StructuredAnswerBlockView: View {
    let kind: String
    let content: String

    var body: some View {
        ScrollView(.horizontal) {
            Text(content)
                .font(.system(.footnote, design: .monospaced))
                .textSelection(.enabled)
        }
        .padding(AppTheme.Spacing.sm)
        .background(AppTheme.Colors.surfaceTint)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
        .accessibilityLabel(kind.hasPrefix("table") ? "表格分段" : "代码分段")
    }
}

private struct QuoteFragmentPicker: View {
    let sourceText: String
    @Binding var text: String
    let onConfirm: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                Text("原文（长按选择并复制需要的词、句或段落）")
                    .font(.footnote)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                ScrollView {
                    Text(sourceText)
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 210)
                .padding(AppTheme.Spacing.sm)
                .background(AppTheme.Colors.surfaceTint)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))

                Text("引用内容")
                    .font(.footnote.weight(.semibold))
                TextEditor(text: $text)
                    .font(AppTheme.Typography.body)
                    .frame(minHeight: 80, maxHeight: 150)
                    .overlay(alignment: .topLeading) {
                        if text.isEmpty {
                            Text("粘贴或输入要引用的片段")
                                .foregroundStyle(AppTheme.Colors.textTertiary)
                                .padding(.horizontal, 5)
                                .padding(.vertical, 8)
                                .allowsHitTesting(false)
                        }
                    }
                    .padding(AppTheme.Spacing.sm)
                    .background(AppTheme.Colors.surfaceTint)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            }
            .padding(AppTheme.Spacing.md)
            .navigationTitle("选择引用片段")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("引用") { onConfirm() }
                        .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }
}

// MARK: - Syntax-Highlighted Code Block Card
public struct CodeBlockCard: View {
    public let snippet: CodeSnippet
    @State private var isCopied: Bool = false

    public init(snippet: CodeSnippet) {
        self.snippet = snippet
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "chevron.left.forwardslash.chevron.right")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(AppTheme.Colors.quantumViolet)
                    .frame(width: 32, height: 32)
                    .background(AppTheme.Colors.mistLilac, in: Circle())
                VStack(alignment: .leading, spacing: 2) {
                    Text("代码片段")
                        .font(AppTheme.Typography.label)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text(snippet.language.uppercased())
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }

                Spacer()

                Button(action: copyCode) {
                    HStack(spacing: 4) {
                        Image(systemName: isCopied ? "checkmark" : "doc.on.doc")
                            .font(.system(size: 11, weight: .semibold))
                        Text(isCopied ? "已复制" : "复制")
                            .font(.system(size: 11, weight: .medium))
                    }
                    .foregroundStyle(isCopied ? AppTheme.Icons.success : AppTheme.Colors.textSecondary)
                    .padding(.horizontal, 10)
                    .frame(minHeight: 32)
                    .background(AppTheme.Colors.secondaryBackground, in: Capsule())
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityHint("复制完整代码")
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(AppTheme.Colors.cardBackground)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                    let lines = snippet.code.components(separatedBy: "\n")
                    VStack(alignment: .trailing, spacing: 3) {
                        ForEach(0..<lines.count, id: \.self) { idx in
                            Text("\(idx + 1)")
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(Color.white.opacity(0.36))
                        }
                    }

                    VStack(alignment: .leading, spacing: 3) {
                        ForEach(0..<lines.count, id: \.self) { idx in
                            Text(lines[idx])
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(AppTheme.Colors.codeSyntaxForeground)
                        }
                    }
                }
                .padding(AppTheme.Spacing.md)
            }
            .background(Color(hex: "223237"))
        }
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(Color.white.opacity(0.8), lineWidth: 0.75)
        }
        .shadow(color: AppTheme.Colors.primary.opacity(0.09), radius: 14, y: 6)
    }

    private func copyCode() {
        #if os(iOS)
        UIPasteboard.general.string = snippet.code
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif
        isCopied = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            isCopied = false
        }
    }
}

// MARK: - Mathematical Formula Card
enum MathFormulaPresentation {
    private static let commands: [(String, String)] = [
        ("\\varepsilon", "ϵ"), ("\\rightarrow", "→"), ("\\leftarrow", "←"),
        ("\\operatorname", ""), ("\\mathrm", ""), ("\\mathbf", ""),
        ("\\alpha", "α"), ("\\beta", "β"), ("\\gamma", "γ"),
        ("\\delta", "δ"), ("\\epsilon", "ε"), ("\\eta", "η"),
        ("\\theta", "θ"), ("\\lambda", "λ"), ("\\mu", "μ"),
        ("\\rho", "ρ"), ("\\sigma", "σ"), ("\\tau", "τ"),
        ("\\phi", "φ"), ("\\omega", "ω"), ("\\pi", "π"),
        ("\\infty", "∞"), ("\\approx", "≈"), ("\\notin", "∉"),
        ("\\times", "×"), ("\\cdot", "·"), ("\\sum", "∑"),
        ("\\prod", "∏"), ("\\int", "∫"), ("\\neq", "≠"),
        ("\\leq", "≤"), ("\\geq", "≥"), ("\\le", "≤"),
        ("\\ge", "≥"), ("\\pm", "±"), ("\\to", "→"),
        ("\\in", "∈"), ("\\left", ""), ("\\right", ""),
        ("\\text", ""), ("\\,", " "), ("\\;", " "), ("\\!", "")
    ]

    private static let subscriptCharacters: [Character: Character] = [
        "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
        "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
        "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
        "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ",
        "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ",
        "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ",
        "v": "ᵥ", "x": "ₓ", "β": "ᵦ", "γ": "ᵧ", "ρ": "ᵨ",
        "φ": "ᵩ", "χ": "ᵪ"
    ]

    private static let superscriptCharacters: [Character: Character] = [
        "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
        "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
        "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
        "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ",
        "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ", "j": "ʲ",
        "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ",
        "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ",
        "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ"
    ]

    static func displayText(_ source: String) -> String {
        var value = source.trimmingCharacters(in: .whitespacesAndNewlines)
        value = value
            .replacingOccurrences(of: "\\begin{aligned}", with: "")
            .replacingOccurrences(of: "\\end{aligned}", with: "")
            .replacingOccurrences(of: "\\begin{equation}", with: "")
            .replacingOccurrences(of: "\\end{equation}", with: "")
            .replacingOccurrences(of: "\\\\", with: "\n")
            .replacingOccurrences(of: "&", with: "")
        value = replacingPattern(#"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}"#, in: value) { captures in
            "\(captures[0])⁄\(captures[1])"
        }
        value = replacingPattern(#"\\sqrt\s*\{([^{}]+)\}"#, in: value) { captures in
            "√(\(captures[0]))"
        }
        for (command, glyph) in commands {
            value = value.replacingOccurrences(of: command, with: glyph)
        }
        value = replacingScripts(in: value)
        // ponytail: this native formatter covers common school/report maths;
        // add a real TeX engine only when matrix/layout notation is required.
        value = value.replacingOccurrences(
            of: #"\\[A-Za-z]+"#, with: "", options: .regularExpression
        )
        value = value
            .replacingOccurrences(of: "{", with: "")
            .replacingOccurrences(of: "}", with: "")
            .replacingOccurrences(of: "$", with: "")
        return value.split(separator: "\n", omittingEmptySubsequences: false)
            .map { line in
                String(line).replacingOccurrences(
                    of: #"[ \t]+"#, with: " ", options: .regularExpression
                ).trimmingCharacters(in: .whitespaces)
            }
            .joined(separator: "\n")
    }

    private static func replacingPattern(
        _ pattern: String,
        in source: String,
        transform: ([String]) -> String
    ) -> String {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return source }
        var value = source
        while true {
            let nsValue = value as NSString
            guard let match = regex.firstMatch(
                in: value, range: NSRange(location: 0, length: nsValue.length)
            ) else { break }
            let captures = (1..<match.numberOfRanges).map { nsValue.substring(with: match.range(at: $0)) }
            value = nsValue.replacingCharacters(in: match.range, with: transform(captures))
        }
        return value
    }

    private static func replacingScripts(in source: String) -> String {
        let characters = Array(source)
        var output = ""
        var index = 0
        while index < characters.count {
            let marker = characters[index]
            guard (marker == "_" || marker == "^"), index + 1 < characters.count else {
                output.append(marker)
                index += 1
                continue
            }
            let start = index + 1
            let content: [Character]
            if characters[start] == "{",
               let end = characters[(start + 1)...].firstIndex(of: "}") {
                content = Array(characters[(start + 1)..<end])
                index = end + 1
            } else {
                content = [characters[start]]
                index = start + 1
            }
            let table = marker == "_" ? subscriptCharacters : superscriptCharacters
            if content.allSatisfy({ table[$0] != nil }) {
                output += String(content.compactMap { table[$0] })
            } else {
                output += marker == "_" ? "₍\(String(content))₎" : "⁽\(String(content))⁾"
            }
        }
        return output
    }
}

public struct FormulaCard: View {
    public let formula: String
    @State private var isCopied = false

    public init(formula: String) {
        self.formula = formula
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                Label("数学公式", systemImage: "function")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.Colors.quantumViolet)
                Spacer()
                Button {
                    #if os(iOS)
                    UIPasteboard.general.string = formula
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                    #endif
                    isCopied = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { isCopied = false }
                } label: {
                    Label(isCopied ? "已复制" : "复制", systemImage: isCopied ? "checkmark" : "doc.on.doc")
                        .font(AppTheme.Typography.micro.weight(.semibold))
                }
                .buttonStyle(SoftButtonStyle())
            }

            ScrollView(.horizontal, showsIndicators: false) {
                Text(MathFormulaPresentation.displayText(formula))
                    .font(.system(size: 28, weight: .regular, design: .serif))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .textSelection(.enabled)
                    .padding(.vertical, AppTheme.Spacing.md)
            }
        }
        .padding(AppTheme.Spacing.lg)
        .background(AppTheme.Colors.mistMint.opacity(0.34))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay(alignment: .leading) {
            Rectangle()
                .fill(AppTheme.Colors.quantumBlue)
                .frame(width: 3)
                .padding(.vertical, AppTheme.Spacing.sm)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("数学公式，\(MathFormulaPresentation.displayText(formula))")
    }
}

private extension Array where Element == MarkdownBlock {
    var prefersSectionCards: Bool {
        (contains { if case .heading = $0 { true } else { false } } && count > 1)
            || contains { block in
                switch block {
                case .formula, .codeBlock, .table, .chart, .callout: true
                default: false
                }
            }
    }
}
