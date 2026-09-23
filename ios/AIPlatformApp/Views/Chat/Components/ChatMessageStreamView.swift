//
//  ChatMessageStreamView.swift
//  AIPlatformApp
//
//  ChatGPT / Gemini Style Message Stream (v2 - Butter-Smooth & Zero-Jank)
//  - Native ScrollView + deterministic VStack message canvas
//  - No lazy placement or programmatic scroll transactions competing with gestures
//

import SwiftUI

public struct ChatMessageStreamView: View {
    static let historyPositionAnchor = UnitPoint.top

    @ObservedObject public var coordinator: TenantSessionCoordinator
    public let onBackgroundTap: () -> Void
    public let onStartTopic: ((ChatMessage) -> Void)?
    public let onWelcomeAction: ((ChatHomeAction) -> Void)?
    @State private var visibleMessageID: String?
    @State private var autoLoadOlderArmed = false
    @State private var isAtHistoryBoundary = false
    @State private var readingPositions: [String: String] = [:]
    @State private var readingSessionID: String?
    @State private var userHasTakenScrollControl = false

    public init(
        coordinator: TenantSessionCoordinator,
        onBackgroundTap: @escaping () -> Void = {},
        onStartTopic: ((ChatMessage) -> Void)? = nil,
        onWelcomeAction: ((ChatHomeAction) -> Void)? = nil
    ) {
        self.coordinator = coordinator
        self.onBackgroundTap = onBackgroundTap
        self.onStartTopic = onStartTopic
        self.onWelcomeAction = onWelcomeAction
    }

    public var body: some View {
        ScrollView {
            // iOS 26.1 的 LazyVStack 在“单条超高 Markdown + 尾部新增消息”后向下拖动时，
            // 会持续重算 LazySubviewPlacements 并占满主线程。消息解析已有有界缓存，
            // 因此这里优先采用确定性的 VStack，换取可收敛的滚动内容尺寸。
            VStack(spacing: AppTheme.Spacing.md) {
                if coordinator.hasOlderMessages {
                    historyButton("加载更早消息", systemImage: "clock.arrow.circlepath") {
                        coordinator.loadOlderMessagePage()
                    }
                }

                if coordinator.messages.isEmpty && coordinator.pendingQueue.isEmpty {
                    ChatWelcomeView(onAction: onWelcomeAction)
                        .frame(minHeight: 540)
                        .transition(.opacity)
                }

                ForEach(coordinator.messages) { message in
                    messageRow(message).id(message.id)
                }
                ForEach(Array(coordinator.pendingQueue.enumerated()), id: \.element.id) { index, item in
                    PendingPlaceholderView(
                        position: index + 1,
                        onCancel: { coordinator.cancelQueued(item.id) }
                    ).id("pending_\(item.id)")
                }

                if coordinator.hasNewerMessages {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        historyButton("加载更新消息", systemImage: "arrow.down.circle") {
                            coordinator.loadNewerMessagePage()
                        }
                        historyButton("回到最新", systemImage: "arrow.down.to.line") {
                            coordinator.returnToLatestMessages()
                        }
                    }
                }

                Color.clear.frame(height: 1)
            }
            .scrollTargetLayout()
            .frame(maxWidth: AppTheme.Metrics.readableContentWidth)
            .frame(maxWidth: .infinity)
            .padding(.vertical, AppTheme.Spacing.md)
            .background {
                Color.clear
                    .contentShape(Rectangle())
                    .onTapGesture {
                        coordinator.collapseActiveClarify()
                        onBackgroundTap()
                    }
            }
        }
        .scrollPosition(id: $visibleMessageID, anchor: Self.historyPositionAnchor)
        .observeChatScrollBoundary { isAtHistoryBoundary = $0 }
        .simultaneousGesture(
            DragGesture(minimumDistance: 12)
                .onChanged { value in
                    userHasTakenScrollControl = true
                    guard isAtHistoryBoundary,
                          Self.shouldArmOlderHistoryPull(
                            translationHeight: value.translation.height,
                            isGenerating: coordinator.isGenerating
                          ) else { return }
                    autoLoadOlderArmed = true
                }
                .onEnded { _ in
                    guard Self.shouldAutoLoadOlderPage(
                        visibleMessageID: visibleMessageID,
                        firstMessageID: coordinator.messages.first?.id,
                        hasOlderMessages: coordinator.hasOlderMessages,
                        isGenerating: coordinator.isGenerating,
                        isArmed: autoLoadOlderArmed,
                        isAtHistoryBoundary: isAtHistoryBoundary
                    ) else {
                        autoLoadOlderArmed = false
                        return
                    }
                    autoLoadOlderArmed = false
                    coordinator.loadOlderMessagePage()
                }
        )
        // 仅设置首次进入会话的位置。不能使用无 role 的 defaultScrollAnchor：
        // 超长消息后继续发送时，它会参与内容尺寸变化的锚点平移，并在 iOS 26
        // 触发消息栈的 AttributeGraph 布局循环。
        .initialScrollAnchor(startsAtBottom: coordinator.historyPageStartsAtBottom && !coordinator.messages.isEmpty)
        .scrollDismissesKeyboard(.immediately)
        .onAppear {
            readingSessionID = coordinator.sessionManager.activeSessionID()
        }
        .onChange(of: coordinator.sessionManager.activeSessionId) { _, newSessionID in
            if let oldSessionID = readingSessionID, let visibleMessageID {
                readingPositions[oldSessionID] = visibleMessageID
            }
            let nextSessionID = newSessionID ?? coordinator.sessionManager.activeSessionID()
            autoLoadOlderArmed = false
            userHasTakenScrollControl = false
            readingSessionID = nextSessionID
            visibleMessageID = readingPositions[nextSessionID] ?? coordinator.messages.last?.id
        }
        .onChange(of: coordinator.historyPageIdentity) { _, _ in
            guard let sessionID = readingSessionID,
                  Self.shouldRestoreHistoryPosition(
                    hasStoredPosition: readingPositions[sessionID] != nil,
                    userHasTakenScrollControl: userHasTakenScrollControl
                  ) else { return }
            autoLoadOlderArmed = false
            visibleMessageID = coordinator.historyPageStartsAtBottom
                ? coordinator.messages.last?.id
                : coordinator.messages.first?.id
        }
        .onChange(of: coordinator.isGenerating) { _, isGenerating in
            if isGenerating { autoLoadOlderArmed = false }
        }

    }

    private func historyButton(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.footnote.weight(.medium))
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm)
                .background(.thinMaterial, in: Capsule())
        }
        .buttonStyle(SoftButtonStyle())
        .foregroundStyle(Color.accentColor)
        .disabled(coordinator.isGenerating)
        .opacity(coordinator.isGenerating ? 0.45 : 1)
    }

    @ViewBuilder
    private func messageRow(_ message: ChatMessage) -> some View {
        if message.degraded {
            DegradedCardView(
                message: message.content,
                onRetry: { coordinator.retryMessage(message.id) }
            )
        } else if coordinator.shouldPresentAutomaticRecovery(message) {
            automaticRecoveryRow(message)
        } else if message.usesPendingPlaceholder {
            if let req = coordinator.inflight, req.id == message.id {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    // Reasoning lives inside the single execution card; other
                    // interactive blocks remain visible as soon as they arrive.
                    ForEach(message.blocks) { block in
                        if !block.isReasoning {
                            liveBlockCard(block)
                        }
                    }
                    ChatInFlightPlaceholderView(
                        req: req,
                        coordinator: coordinator,
                        steps: message.reasoningSteps,
                        assistantName: message.executingAgentName
                    )
                }
            } else {
                OrphanPendingCardView(onRetry: { coordinator.retryMessage(message.id) })
            }
        } else if let clarify = message.clarifyBlock,
                  !clarify.isSubmitted,
                  !containsRequirementConfirmation(message) {
            ClarifyCard(
                block: clarify,
                onSubmit: { selection in
                    coordinator.sendClarifySelection(messageId: message.id, selection: selection)
                },
                onRecover: { coordinator.recoverExpiredClarify(messageId: message.id) },
                onDraftChange: { ids, text in
                    coordinator.updateClarifyDraft(messageId: message.id, selectionIDs: ids, customText: text)
                },
                onExpand: { coordinator.setClarifyCollapsed(messageId: message.id, collapsed: false) }
            )
        } else {
            // 提交后（isSubmitted）：降级为完整气泡渲染——思维链胶囊 + 已提交澄清卡 + 正文
            // 实时可见（同 SSE 流事件驱动，绝不因澄清卡独占遮住执行过程）
            MessageBubbleView(
                message: message,
                context: coordinator.makeRenderContext(for: message),
                onQuoteFollowUp: { quoted in coordinator.quotedContext = quoted },
                onRegenerate: { msgId in coordinator.retryMessage(msgId) },
                onStartTopic: { message in
                    if let onStartTopic { onStartTopic(message) }
                    else { coordinator.startTargetedTopic(from: message) }
                }
            )
        }
    }

    private func automaticRecoveryRow(_ message: ChatMessage) -> some View {
        var visible = message
        visible.role = .assistant
        visible.pending = true
        visible.isStreaming = true
        return VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            MessageBubbleView(
                message: visible,
                context: coordinator.makeRenderContext(for: message),
                onQuoteFollowUp: { quoted in coordinator.quotedContext = quoted }
            )
            if message.showsSeparateRecoveryHint {
                BackgroundProcessingCardView(
                    isReconnecting: coordinator.isProcessingExistingRun(message),
                    confirmedRunning: coordinator.confirmedRunningMessageIDs.contains(message.id)
                )
            }
        }
    }

    /// 普通 Clarify 保持卡片独占的轻量形态；最终确认必须同时呈现需求确认单表格。
    private func containsRequirementConfirmation(_ message: ChatMessage) -> Bool {
        if message.content.contains("确认维度") && message.content.contains("已确认需求") {
            return true
        }
        return message.blocks.contains { block in
            if case .table(let table) = block {
                return table.title.contains("需求确认")
            }
            return false
        }
    }

    static func shouldAutoLoadOlderPage(
        visibleMessageID: String?,
        firstMessageID: String?,
        hasOlderMessages: Bool,
        isGenerating: Bool,
        isArmed: Bool,
        isAtHistoryBoundary: Bool
    ) -> Bool {
        isArmed && isAtHistoryBoundary && hasOlderMessages && !isGenerating
            && visibleMessageID != nil && visibleMessageID == firstMessageID
    }

    static func shouldArmOlderHistoryPull(
        translationHeight: CGFloat,
        isGenerating: Bool
    ) -> Bool {
        !isGenerating && translationHeight > 12
    }

    static func shouldRestoreHistoryPosition(
        hasStoredPosition: Bool,
        userHasTakenScrollControl: Bool
    ) -> Bool {
        !hasStoredPosition && !userHasTakenScrollControl
    }

    static func isAtOlderHistoryBoundary(contentOffsetY: CGFloat, topInset: CGFloat) -> Bool {
        contentOffsetY <= -topInset + 2
    }


    /// 流式期间实时揭示的块（仅 reasoning / clarify 有实时价值，其余等待完成态统一渲染）
    @ViewBuilder
    private func liveBlockCard(_ block: MessageBlock) -> some View {
        switch block {
        case .reasoning(let steps):
            ReasoningCard(
                steps: steps,
                isStreaming: true,
                onCancel: { coordinator.cancelInFlight() }
            )
        case .clarify(let clarifyBlock):
            ClarifyCard(
                block: clarifyBlock,
                onSubmit: { selection in
                    if let msg = coordinator.messages.first(where: {
                        if case .clarify(let c) = $0.blocks.first { return c.id == clarifyBlock.id }
                        return false
                    }) {
                        coordinator.sendClarifySelection(messageId: msg.id, selection: selection)
                    }
                },
                onRecover: {
                    if let msg = coordinator.messages.last(where: {
                        $0.clarifyBlock?.id == clarifyBlock.id
                    }) { coordinator.recoverExpiredClarify(messageId: msg.id) }
                }
            )
        default:
            EmptyView()
        }
    }
}

extension ChatMessage {
    var usesPendingPlaceholder: Bool {
        pending && role == .assistant
            && content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var reasoningSteps: [ReasoningStep] {
        for block in blocks {
            if case .reasoning(let steps) = block { return steps }
        }
        return []
    }

    var showsSeparateRecoveryHint: Bool { reasoningSteps.isEmpty }
}

private extension MessageBlock {
    var isReasoning: Bool {
        if case .reasoning = self { return true }
        return false
    }
}

private extension View {
    @ViewBuilder
    func observeChatScrollBoundary(_ action: @escaping (Bool) -> Void) -> some View {
        if #available(iOS 18.0, *) {
            onScrollGeometryChange(for: Bool.self) { geometry in
                ChatMessageStreamView.isAtOlderHistoryBoundary(
                    contentOffsetY: geometry.contentOffset.y,
                    topInset: geometry.contentInsets.top
                )
            } action: { _, isAtTop in
                action(isAtTop)
            }
        } else {
            self
        }
    }

    @ViewBuilder
    func initialScrollAnchor(startsAtBottom: Bool) -> some View {
        if #available(iOS 18.0, *), startsAtBottom {
            defaultScrollAnchor(.bottom, for: .initialOffset)
        } else {
            // iOS 17 没有按角色限定锚点的 API；保持原生顶部初始位置，
            // 也不要恢复会影响后续内容尺寸变化的全局底部锚点。
            self
        }
    }
}

public struct ChatHomeAction: Identifiable, Hashable {
    public let id: String
    public let title: String
    public let subtitle: String
    public let prompt: String

    static let all = [
        ChatHomeAction(
            id: "continue-learning",
            title: "继续学",
            subtitle: "接着最近的阅读和问题，快速找回思路",
            prompt: "请结合我最近的学习、阅读和提问记录，帮我从上次停下的位置继续学。先用一句话说明我们学到哪里，再给出最合适的下一步。"
        ),
        ChatHomeAction(
            id: "continue-doing",
            title: "继续做",
            subtitle: "回到未完成的任务",
            prompt: "请找到我最近尚未完成的任务或工作流，概括当前进度，并从下一步继续。"
        ),
        ChatHomeAction(
            id: "help-me-clean",
            title: "帮我清理",
            subtitle: "整理对话、笔记和待办",
            prompt: "请帮我清理最近积累的对话、笔记和待办。先列出建议整理的内容，涉及删除、归档或覆盖时必须先让我确认。"
        ),
    ]

    static let attention = ChatHomeAction(
        id: "attention",
        title: "为你留意",
        subtitle: "来自计划、阅读进度和最近批注",
        prompt: "请结合我的学习计划、阅读进度和最近批注，告诉我今天最值得留意的内容。"
    )
}

private struct ChatWelcomeView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var appeared = false
    let onAction: ((ChatHomeAction) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("下午好，\n今天想从哪里继续？")
                .font(.system(size: 35, weight: .bold, design: .serif))
                .foregroundStyle(HomePalette.ink)
                .lineSpacing(2)
            Text("你的进度和灵感，都在这里等你。")
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(HomePalette.secondary)

            learningHero
            HStack(spacing: 10) {
                compactAction(ChatHomeAction.all[1], tint: HomePalette.mint, icon: "doc.text.fill")
                compactAction(ChatHomeAction.all[2], tint: HomePalette.lilac, icon: "paintbrush.fill")
            }
            attentionSection
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, AppTheme.Metrics.contentGutter)
        .padding(.top, AppTheme.Spacing.lg)
        .padding(.bottom, AppTheme.Spacing.xxl)
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : (reduceMotion ? 0 : 12))
        .onAppear {
            withAnimation(reduceMotion ? nil : AppTheme.Motion.standard) { appeared = true }
        }
        .accessibilityLabel("下午好，今天想从哪里继续？")
    }

    private var learningHero: some View {
        Button { onAction?(ChatHomeAction.all[0]) } label: {
            ZStack(alignment: .leading) {
            Image("home_learning_hero")
                .resizable()
                .scaledToFill()
                .frame(maxWidth: .infinity)
                .frame(height: 228)
                .clipped()
                LinearGradient(colors: [Color.white.opacity(0.96), Color.white.opacity(0.15)], startPoint: .leading, endPoint: .trailing)
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 8) {
                        Text("继续学")
                            .font(.system(size: 30, weight: .bold, design: .serif))
                        Image(systemName: "chevron.right")
                            .font(.headline.weight(.bold))
                            .frame(width: 38, height: 38)
                            .background(Color.white.opacity(0.66), in: Circle())
                    }
                    Text("数学分析 · 第 3 章")
                        .font(.system(size: 17, weight: .semibold))
                    Spacer()
                    Text("上次读到 68%")
                        .font(.subheadline)
                        .foregroundStyle(HomePalette.secondary)
                    HStack(spacing: 10) {
                        ProgressView(value: 0.68).tint(HomePalette.green).frame(width: 128)
                        Text("68%").font(.caption.weight(.semibold)).foregroundStyle(HomePalette.secondary)
                    }
                    HomePrimaryLabel("继续阅读", width: 132)
                }
                .foregroundStyle(HomePalette.ink)
                .padding(20)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .buttonStyle(SoftButtonStyle())
        .frame(height: 228)
        .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .stroke(Color.white.opacity(0.72), lineWidth: 1)
        }
        .shadow(color: HomePalette.shadow, radius: 18, y: 8)
        .accessibilityLabel("继续学，数学分析第三章，上次读到百分之六十八")
    }

    private func compactAction(_ action: ChatHomeAction, tint: Color, icon: String) -> some View {
        Button { onAction?(action) } label: {
            ZStack(alignment: .bottomTrailing) {
                Image(action.id == "continue-doing" ? "home_continue_work_art" : "home_cleanup_art")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 112, height: 112)
                    .offset(x: 26, y: 18)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 8) {
                Image(systemName: icon)
                    .font(.title3)
                    .foregroundStyle(action.id == "help-me-clean" ? Color(hex: "7664E8") : Color(hex: "27B8B2"))
                    .frame(width: 42, height: 42)
                    .background(Color.white.opacity(0.7), in: RoundedRectangle(cornerRadius: 14))
                HStack(spacing: 6) {
                    Text(action.title).font(.system(size: 19, weight: .bold, design: .serif))
                    Image(systemName: "chevron.right").font(.caption.weight(.bold))
                }
                Text(action.id == "continue-doing" ? "毕业论文资料整理" : "12 条待整理内容")
                    .font(.subheadline.weight(.medium))
                Text(action.id == "continue-doing" ? "3 个步骤待完成" : "对话 · 笔记 · 待办")
                    .font(.caption).foregroundStyle(HomePalette.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .foregroundStyle(HomePalette.ink)
            .padding(14)
            .frame(maxWidth: .infinity, minHeight: 136, alignment: .leading)
            .background(tint, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay { RoundedRectangle(cornerRadius: 24).stroke(Color.white, lineWidth: 1) }
        }
        .buttonStyle(SoftButtonStyle())
    }

    private var attentionSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("为你留意").font(.system(size: 22, weight: .bold, design: .serif))
                Spacer()
                Button("更多 ›") { onAction?(.attention) }
                    .font(.subheadline.weight(.medium)).foregroundStyle(HomePalette.secondary)
            }
            attentionRow(icon: "calendar", tint: HomePalette.coral, title: "今天的学习计划", subtitle: "线性代数第 4 章 · 预计 25 分钟", button: "开始") {
                onAction?(.attention)
            }
            attentionRow(icon: "lightbulb.fill", tint: HomePalette.blue, title: "值得回看的灵感", subtitle: "“先别急着问它像不像人，而是问一个更好的问题。”", button: "继续阅读") {
                onAction?(ChatHomeAction.all[0])
            }
        }
    }

    private func attentionRow(icon: String, tint: Color, title: String, subtitle: String, button: String, action: @escaping () -> Void) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon).font(.title3).foregroundStyle(tint)
                .frame(width: 42, height: 42).background(tint.opacity(0.10), in: RoundedRectangle(cornerRadius: 13))
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.subheadline.weight(.bold)).foregroundStyle(HomePalette.ink)
                Text(subtitle).font(.caption).foregroundStyle(HomePalette.secondary).lineLimit(2)
            }
            Spacer(minLength: 4)
            Button(button, action: action).font(.caption.weight(.semibold)).foregroundStyle(tint)
                .padding(.horizontal, 12).frame(height: 34).background(tint.opacity(0.12), in: Capsule())
        }
        .padding(12).background(Color.white.opacity(0.72), in: RoundedRectangle(cornerRadius: 20))
        .overlay { RoundedRectangle(cornerRadius: 20).stroke(Color.white, lineWidth: 1) }
    }
}

private enum HomePalette {
    static let ink = Color(hex: "10213C")
    static let secondary = Color(hex: "71819B")
    static let green = Color(hex: "55C982")
    static let mint = Color(hex: "E4FBF2")
    static let lilac = Color(hex: "F0EEFF")
    static let coral = Color(hex: "FF706F")
    static let blue = Color(hex: "438FF2")
    static let shadow = Color(hex: "526A79").opacity(0.11)
}

private struct HomePrimaryLabel: View {
    let text: String
    let width: CGFloat?
    init(_ text: String, width: CGFloat? = nil) { self.text = text; self.width = width }
    var body: some View {
        HStack(spacing: 8) { Text(text); Image(systemName: "chevron.right").font(.caption.weight(.bold)) }
            .font(.subheadline.weight(.semibold)).foregroundStyle(.white)
            .frame(width: width)
            .frame(maxWidth: width == nil ? .infinity : nil, minHeight: 44)
            .background(HomePalette.ink, in: Capsule())
    }
}

struct LearningPlanItem: Identifiable, Equatable {
    let id = UUID()
    let minutes: Int
    let title: String
    let detail: String
}

struct LearningPlanResponse: Equatable {
    let items: [LearningPlanItem]
    let keyExcerpt: String

    static let fallback = LearningPlanResponse(
        items: [
            .init(minutes: 2, title: "回顾上次重点", detail: "快速过一遍核心概念，建立连贯性。"),
            .init(minutes: 15, title: "继续阅读", detail: "从上次停下的位置继续，逐步理解关键步骤。"),
            .init(minutes: 8, title: "做一道理解题", detail: "巩固所学，检验掌握程度。"),
        ],
        keyExcerpt: ""
    )

    static func parse(_ text: String) -> LearningPlanResponse? {
        var items: [LearningPlanItem] = []
        var key = ""
        for rawLine in text.components(separatedBy: .newlines) {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
                .trimmingCharacters(in: CharacterSet(charactersIn: "-*` "))
            let parts = line.split(separator: "|", maxSplits: 2).map {
                $0.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            if parts.count == 2, parts[0].uppercased() == "KEY" {
                key = parts[1]
            } else if parts.count == 3, let minutes = Int(parts[0]), minutes > 0 {
                items.append(.init(minutes: minutes, title: parts[1], detail: parts[2]))
            }
        }
        guard items.count == 3, items.map(\.minutes).reduce(0, +) == 25 else { return nil }
        return LearningPlanResponse(items: items, keyExcerpt: key)
    }
}

private struct LearningQuestion: Identifiable {
    let id = UUID()
    let title: String
    let excerpt: String
    let question: String
}

struct HomeJourneyView: View {
    @EnvironmentObject private var sessionManager: SessionManager
    @ObservedObject private var noteStore = KnowledgeNoteStore.shared
    @State private var subscription: KnowledgeBookSubscriptionDTO?
    @State private var bookBody: KnowledgeBookBodyDTO?
    @State private var selectedBook: KnowledgeBookDTO?
    @State private var learningQuestion: LearningQuestion?
    @State private var inspectedLearningAnnotation: ReaderAnnotationEntry?
    @State private var learningAnnotationChoices: [ReaderAnnotationEntry] = []
    @State private var showingLearningAnnotationChoices = false
    @State private var showingExercise = false
    @State private var learningPlan = LearningPlanResponse.fallback
    @State private var isResettingPlan = false
    @State private var notes: [CloudKnowledgeNoteDTO] = []
    @State private var selectedCleanupIDs: Set<String> = ["archive-chat", "archive-note", "merge-preview", "selected-4", "selected-5", "selected-6"]
    @State private var cleanupFilter = 0
    @State private var showCleanupConfirmation = false
    @State private var showArchiveConfirmation = false
    @State private var cleanupMessage: String?
    @State private var readerBusy = false
    @State private var hiddenAttentionTitles: Set<String> = []
    @State private var attentionFilter = 0
    @State private var attentionDraft = ""
    @State private var showAttentionManagement = false
    @State private var showClearReadConfirmation = false
    @State private var importantOnly = false
    @State private var learningDraft = ""
    @State private var workDraft = ""
    @State private var cleanupDraft = ""

    let action: ChatHomeAction
    let onBack: () -> Void
    let onPrompt: (String) -> Void

    var body: some View {
        ZStack {
            QuantumMistBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    header
                    switch action.id {
                    case "continue-learning": learningPage
                    case "continue-doing": workPage
                    case "help-me-clean": cleanupPage
                    default: attentionPage
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 28)
            }
        }
        .toolbar(.hidden, for: .navigationBar)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if action.id == "continue-learning" { learningComposer }
            if action.id == "attention" { attentionComposer }
            if action.id == "continue-doing" { workComposer }
            if action.id == "help-me-clean" { cleanupComposer }
        }
        .task { await loadData() }
        .sheet(item: $learningQuestion) { item in
            ReaderQuestionSheet(
                excerpt: item.excerpt,
                sourceTitle: currentTitle,
                sourceSubtitle: "继续学 · \(item.title)",
                initialQuestion: item.question,
                submitsOnAppear: true,
                automaticallySaveAnswer: true,
                onSaveAnswer: { question, answer in
                    saveLearningAnnotation(item: item, question: question, answer: answer)
                }
            ) { question, sessionID in
                APIClient.shared.chatStream(
                    question: question,
                    sessionId: sessionID,
                    quotedContext: item.excerpt,
                    contextScope: learningContextScope
                )
            }
        }
        .sheet(item: $inspectedLearningAnnotation) { ReaderAnnotationDetailSheet(entry: $0) }
        .confirmationDialog("选择批注", isPresented: $showingLearningAnnotationChoices, titleVisibility: .visible) {
            ForEach(learningAnnotationChoices) { annotation in
                Button("\(annotation.date) · \(annotation.kind)") {
                    inspectedLearningAnnotation = annotation
                }
            }
        }
        .fullScreenCover(isPresented: $showingExercise) {
            LearningExerciseView(
                sourceTitle: currentTitle,
                sourceExcerpt: lastReadingExcerpt,
                contextScope: learningContextScope,
                onSave: { question, answer, feedback in
                    saveLearningAnnotation(
                        item: LearningQuestion(title: "理解题", excerpt: question, question: answer),
                        question: answer,
                        answer: feedback
                    )
                }
            )
        }
        .sheet(isPresented: $showAttentionManagement) { AttentionManagementSheet() }
        .fullScreenCover(item: $selectedBook) { book in
            KnowledgeBookReaderView(
                book: book,
                isSubscribed: true,
                isBusy: readerBusy,
                onToggleSubscription: { Task { await toggleSubscription(book) } },
                onSaveExcerpt: nil,
                startsInReading: true,
                initialSectionID: currentSection?.id,
                onDismiss: { selectedBook = nil }
            )
            .environmentObject(APIClient.shared)
        }
        .fullScreenCover(isPresented: $showArchiveConfirmation) {
            ArchiveConfirmationView(
                sessionIDs: Array(cleanupSessions.prefix(3)),
                onLater: { showArchiveConfirmation = false },
                onContinue: { sessionID in
                    if let sessionID { sessionManager.switchTo(sessionID) }
                    showArchiveConfirmation = false
                    closeJourney()
                },
                onConfirm: { sessionIDs in
                    sessionIDs.forEach { sessionManager.setLifecycle(.archived, for: $0) }
                    showArchiveConfirmation = false
                    cleanupMessage = "已归档 \(sessionIDs.count) 个对话；归档内容仍可在会话历史中恢复。"
                }
            )
        }
        .alert("确认整理所选内容？", isPresented: $showCleanupConfirmation) {
            Button("取消", role: .cancel) {}
            Button("确认归档") { performCleanup() }
        } message: {
            Text("所选对话会移入归档；笔记不会自动删除或覆盖。之后仍可恢复。")
        }
        .alert("整理结果", isPresented: Binding(
            get: { cleanupMessage != nil }, set: { if !$0 { cleanupMessage = nil } }
        )) { Button("知道了") { cleanupMessage = nil } } message: { Text(cleanupMessage ?? "") }
        .alert("清空已读提醒？", isPresented: $showClearReadConfirmation) {
            Button("取消", role: .cancel) {}
            Button("清空", role: .destructive) {
                hiddenAttentionTitles.formUnion(["线性代数第 4 章", "值得回看的灵感", "毕业论文资料整理"])
            }
        } message: { Text("只会清除本页已读提醒，不会删除计划、笔记或批注。") }
    }

    private var header: some View {
        HStack {
            Button(action: closeJourney) {
                Image(systemName: "chevron.left").font(.title3.weight(.semibold)).frame(width: 44, height: 44)
            }
            .accessibilityLabel("返回工作台")
            .accessibilityIdentifier("journey-back-to-workbench")
            Spacer()
            Text(action.title).font(.headline.weight(.bold)).foregroundStyle(HomePalette.ink)
            Spacer()
            if action.id == "attention" {
                Button("管理") { showAttentionManagement = true }
                    .font(.subheadline.weight(.semibold)).frame(width: 44, height: 44)
            } else {
                Color.clear.frame(width: 44, height: 44)
            }
        }
        .foregroundStyle(HomePalette.ink)
        .padding(.top, 4)
    }

    private var currentTitle: String { subscription?.book.title ?? "数学分析 · 第 3 章" }
    private var currentProgress: Double { subscription.map { min(max($0.progress, 0), 1) } ?? 0.68 }

    private var learningPage: some View {
        Group {
            HeroStrip(title: currentTitle, subtitle: subscription == nil ? "上次学习 · 昨天 22:14" : "上次学习 · 已同步", progress: currentProgress)
            PaperCard {
                SectionHeading(icon: "lightbulb.fill", tint: HomePalette.blue, title: "先帮你找回思路", subtitle: "根据你上次的学习内容，整理了这些关键点：")
                learningPoint(number: 1, color: HomePalette.blue, title: "柯西列与收敛", detail: "回顾定义、收敛的充要条件及基本性质。")
                learningPoint(number: 2, color: HomePalette.green, title: "完备性的核心条件", detail: "理解完备空间的定义及其与柯西列的关系。")
                NumberedPoint(
                    number: 3,
                    color: Color(hex: "7367EF"),
                    title: "你停在：\(currentSection?.title ?? "Bolzano–Weierstrass 定理")",
                    detail: "回到上次记录的章节位置继续阅读。",
                    annotationCount: 0,
                    onTap: openCurrentReading,
                    onAnnotationTap: nil
                )
            }
            PaperCard(tint: HomePalette.mint) {
                HStack(alignment: .top) {
                    SectionHeading(icon: "target", tint: Color(hex: "2CC6A5"), title: "接下来 25 分钟", subtitle: "结合记忆、阅读进度和能力为你定制。")
                    Spacer(minLength: 4)
                    Button { Task { await resetLearningPlan() } } label: {
                        Image(systemName: isResettingPlan ? "hourglass" : "arrow.clockwise")
                            .frame(width: 38, height: 38)
                            .background(Color.white.opacity(0.72), in: Circle())
                    }
                    .disabled(isResettingPlan)
                    .accessibilityLabel("重新定制 25 分钟计划")
                }
                ForEach(Array(learningPlan.items.enumerated()), id: \.element.id) { index, item in
                    TimelinePoint(
                        done: index == 0,
                        active: index == 1,
                        isLast: index == learningPlan.items.count - 1,
                        title: "\(item.minutes) 分钟 · \(item.title)",
                        detail: item.detail,
                        onTap: { handlePlanItem(item, index: index) }
                    )
                }
                NotebookExcerptCard(excerpt: lastReadingExcerpt, keyText: learningPlan.keyExcerpt)
            }
        }
    }

    private var workPage: some View {
        Group {
            WorkProjectHero()
            WorkProgressCard()
            WorkSuggestionCard()
            WorkPhasesCard()
            WorkConfirmationCard(
                onConfirm: { onPrompt(action.prompt) },
                onAdjust: { onPrompt("我要调整毕业论文资料整理任务的范围和输出，请先向我确认修改项。") },
                onRange: { onPrompt("请让我重新选择毕业论文资料整理的文献范围。") },
                onOutput: { onPrompt("请让我调整毕业论文资料整理的输出格式。") }
            )
        }
    }

    private var cleanupPage: some View {
        Group {
            CleanupHero(count: 12)
            CleanupFilterBar(selection: $cleanupFilter)
            CleanupArchiveCard(
                chatSelected: selectedCleanupIDs.contains("archive-chat"),
                noteSelected: selectedCleanupIDs.contains("archive-note"),
                onChat: { toggle("archive-chat") },
                onNote: { toggle("archive-note") },
                onArchiveChat: { showArchiveConfirmation = true },
                onArchiveNote: { onPrompt("请先展示毕业论文资料整理阶段记录的归档确认单。") }
            )
            CleanupMergeCard(selected: selectedCleanupIDs.contains("merge-preview")) {
                toggle("merge-preview")
            } onReview: {
                onPrompt("请展示“线性代数复习”和“线性代数重点整理”的合并差异，确认后再合并。")
            }
            CleanupDecisionCard(selected: selectedCleanupIDs.contains("duplicate-task")) {
                toggle("duplicate-task")
            } onReview: {
                onPrompt("请展示 2 条重复待办的内容差异，不要直接删除。")
            }
            CleanupSelectionBar(
                count: selectedCleanupIDs.count,
                onLater: closeJourney,
                onConfirm: { showCleanupConfirmation = true }
            )
        }
    }

    private var attentionPage: some View {
        Group {
            AttentionIntroCard()
            AttentionFilterBar(selection: $attentionFilter)
            AttentionSectionTitle(title: "今天", subtitle: "这些内容值得你今天关注")
            if showsAttention(.study) && !hiddenAttentionTitles.contains("线性代数第 4 章") {
                AttentionFocusCard(
                    icon: "calendar", tint: HomePalette.coral, background: Color(hex: "FFF5F2"),
                    title: "线性代数第 4 章", subtitle: "预计 25 分钟 · 本周计划",
                    reasonIcon: "lightbulb", reasonTitle: "为什么提醒我？", reason: "今天是你设置的学习日",
                    primary: "开始学习", secondary: "今晚提醒", primaryTint: HomePalette.coral, note: nil,
                    action: { onPrompt("开始今天计划中的线性代数第 4 章学习，先告诉我本次目标。") },
                    secondaryAction: { hiddenAttentionTitles.insert("线性代数第 4 章") }
                )
            }
            if showsAttention(.inspiration) && !hiddenAttentionTitles.contains("值得回看的灵感") {
                AttentionFocusCard(
                    icon: "lightbulb.fill", tint: HomePalette.blue, background: Color(hex: "F2F7FF"),
                    title: "值得回看的灵感", subtitle: "“先别急着问它像不像人，\n而是问一个更好的问题。”\n《计算机与智能》· 昨天批注",
                    reasonIcon: "bubble.left", reasonTitle: "为什么提醒我？", reason: "与你最近的 AI 课程问题相关",
                    primary: "继续阅读", secondary: "保存到笔记", primaryTint: HomePalette.blue, note: "好的想法\n总会在合适的时间\n再次发光",
                    action: { onPrompt(action.prompt) },
                    secondaryAction: { onPrompt("把“先别急着问它像不像人，而是问一个更好的问题。”保存到我的笔记，并保留《计算机与智能》的来源。") }
                )
            }
            if showsAttention(.pending) {
                AttentionSectionTitle(title: "稍后处理", subtitle: "这些内容可以之后再处理").padding(.top, 6)
            }
            if showsAttention(.pending) && !hiddenAttentionTitles.contains("毕业论文资料整理") {
                AttentionFocusCard(
                    icon: "doc.text.fill", tint: Color(hex: "22B996"), background: Color(hex: "F1FCF7"),
                    title: "毕业论文资料整理", subtitle: "3 个步骤待完成",
                    reasonIcon: "clock", reasonTitle: "为什么提醒我？", reason: "你已 4 天未继续",
                    primary: "继续做", secondary: "不再提醒", primaryTint: HomePalette.ink, note: "持续一点点\n也会有很大进步",
                    action: { onPrompt(ChatHomeAction.all[1].prompt) },
                    secondaryAction: { hiddenAttentionTitles.insert("毕业论文资料整理") }
                )
            }
            HStack(spacing: 0) {
                AttentionSettingButton(icon: "gearshape", title: "提醒频率：适中") { showAttentionManagement = true }
                Divider().frame(height: 28)
                AttentionSettingButton(icon: importantOnly ? "eye.fill" : "eye.slash", title: "仅显示重要内容") { importantOnly.toggle() }
                Divider().frame(height: 28)
                AttentionSettingButton(icon: "trash", title: "清空已读", tint: HomePalette.coral) { showClearReadConfirmation = true }
            }
            .padding(.vertical, 8).background(Color.white.opacity(0.78), in: RoundedRectangle(cornerRadius: 18))
        }
    }

    private var attentionComposer: some View {
        HStack(spacing: 8) {
            Menu {
                Button("添加学习提醒", systemImage: "calendar.badge.plus") { attentionDraft = "帮我添加一个学习提醒：" }
                Button("记录一条灵感", systemImage: "lightbulb") { attentionDraft = "帮我记录这条灵感：" }
            } label: { Image(systemName: "plus").frame(width: 42, height: 42).background(Color.white.opacity(0.84), in: Circle()) }
            TextField("问问 Quantum…", text: $attentionDraft)
                .submitLabel(.send).onSubmit { submitAttentionDraft() }
            Button { attentionDraft = "请帮我把今天值得关注的内容安排成一个可执行计划。" } label: {
                Image(systemName: "mic.fill").foregroundStyle(HomePalette.secondary).frame(width: 34, height: 42)
            }
            Button(action: submitAttentionDraft) {
                Image(systemName: "sparkles").foregroundStyle(.white).frame(width: 46, height: 46)
                    .background(LinearGradient(colors: [Color(hex: "25C7E8"), Color(hex: "8A5CF5")], startPoint: .bottomLeading, endPoint: .topTrailing), in: Circle())
            }
            .disabled(attentionDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(8).background(.ultraThinMaterial, in: Capsule()).padding(.horizontal, 16).padding(.bottom, 4)
    }

    private var learningComposer: some View {
        HStack(spacing: 8) {
            Button {
                learningDraft = "请围绕当前内容解释："
            } label: {
                Image(systemName: "plus")
                    .frame(width: 42, height: 42)
                    .background(Color.white.opacity(0.84), in: Circle())
            }
            TextField("围绕当前内容提问…", text: $learningDraft)
                .submitLabel(.send)
                .onSubmit { submitLearningDraft() }
            Button {
                learningDraft = "请先问我一个问题，检查我是否理解当前内容。"
            } label: {
                Image(systemName: "mic.fill")
                    .foregroundStyle(HomePalette.secondary)
                    .frame(width: 34, height: 42)
            }
            Button(action: submitLearningDraft) {
                Image(systemName: "sparkles")
                    .foregroundStyle(.white)
                    .frame(width: 46, height: 46)
                    .background(
                        LinearGradient(
                            colors: [Color(hex: "25C7E8"), Color(hex: "8A5CF5")],
                            startPoint: .bottomLeading,
                            endPoint: .topTrailing
                        ),
                        in: Circle()
                    )
            }
            .disabled(learningDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(8)
        .background(.ultraThinMaterial, in: Capsule())
        .padding(.horizontal, 16)
        .padding(.bottom, 4)
    }

    private var cleanupComposer: some View {
        HStack(spacing: 8) {
            Menu {
                Button("说明整理偏好", systemImage: "slider.horizontal.3") { cleanupDraft = "我的整理偏好是：" }
                Button("指定保留内容", systemImage: "bookmark") { cleanupDraft = "这些内容请务必保留：" }
            } label: {
                Image(systemName: "plus").frame(width: 42, height: 42).background(Color.white.opacity(0.84), in: Circle())
            }
            TextField("告诉你的整理偏好…", text: $cleanupDraft)
                .submitLabel(.send).onSubmit { submitCleanupDraft() }
            Button { cleanupDraft = "请先问我几个问题，再帮我确定整理偏好。" } label: {
                Image(systemName: "mic.fill").foregroundStyle(HomePalette.secondary).frame(width: 34, height: 42)
            }
            Button(action: submitCleanupDraft) {
                Image(systemName: "sparkles").foregroundStyle(.white).frame(width: 46, height: 46)
                    .background(LinearGradient(colors: [Color(hex: "25C7E8"), Color(hex: "8A5CF5")], startPoint: .bottomLeading, endPoint: .topTrailing), in: Circle())
            }.disabled(cleanupDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(8).background(.ultraThinMaterial, in: Capsule()).padding(.horizontal, 16).padding(.bottom, 4)
    }

    private var workComposer: some View {
        HStack(spacing: 8) {
            Menu {
                Button("补充文献", systemImage: "doc.badge.plus") { workDraft = "我还要补充这些文献：" }
                Button("修改整理要求", systemImage: "slider.horizontal.3") { workDraft = "请调整整理要求：" }
            } label: { Image(systemName: "plus").frame(width: 42, height: 42).background(Color.white.opacity(0.84), in: Circle()) }
            TextField("补充你的要求…", text: $workDraft)
                .submitLabel(.send).onSubmit { submitWorkDraft() }
            Button { workDraft = "请先向我提问，确认毕业论文资料整理还缺哪些信息。" } label: {
                Image(systemName: "mic.fill").foregroundStyle(HomePalette.secondary).frame(width: 34, height: 42)
            }
            Button(action: submitWorkDraft) {
                Image(systemName: "sparkles").foregroundStyle(.white).frame(width: 46, height: 46)
                    .background(LinearGradient(colors: [Color(hex: "25C7E8"), Color(hex: "8A5CF5")], startPoint: .bottomLeading, endPoint: .topTrailing), in: Circle())
            }.disabled(workDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(8).background(.ultraThinMaterial, in: Capsule()).padding(.horizontal, 16).padding(.bottom, 4)
    }

    private func submitWorkDraft() {
        let prompt = workDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else { return }
        workDraft = ""
        onPrompt(prompt)
    }

    private func submitLearningDraft() {
        let prompt = learningDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else { return }
        learningDraft = ""
        onPrompt(prompt)
    }

    private func closeJourney() {
        onBack()
    }

    private var currentSection: KnowledgeBookSectionDTO? {
        guard let sections = bookBody?.sections, !sections.isEmpty else { return nil }
        let index = min(Int(currentProgress * Double(sections.count)), sections.count - 1)
        return sections[max(index, 0)]
    }

    private var learningContextScope: ChatContextScopeDTO {
        ChatContextScopeDTO(
            mode: .platformOnly,
            selectedBookId: subscription?.book.id,
            selectedBookVersion: bookBody?.contentVersion,
            selectedBookSectionId: currentSection?.id
        )
    }

    private var lastReadingExcerpt: String {
        guard let section = currentSection else {
            return "设 {xₙ} 是实数列，柯西列的定义要求任意 ε > 0 时，序列后部任意两项距离都小于 ε。"
        }
        let blocks = ReadingSectionContent.parse(section.markdown).blocks
        let text = blocks.compactMap { block -> String? in
            switch block {
            case .paragraph(let value), .quote(let value): return value
            case .formula(let value): return MathFormulaPresentation.displayText(value)
            default: return nil
            }
        }.joined(separator: "\n\n")
        return String((text.isEmpty ? section.markdown : text).prefix(700))
    }

    @ViewBuilder
    private func learningPoint(number: Int, color: Color, title: String, detail: String) -> some View {
        let excerpt = "\(title)\n\(detail)"
        let annotations = learningAnnotations(for: excerpt)
        NumberedPoint(
            number: number,
            color: color,
            title: title,
            detail: detail,
            annotationCount: annotations.count,
            onTap: {
                learningQuestion = LearningQuestion(
                    title: title,
                    excerpt: excerpt,
                    question: "请结合我当前阅读位置和已有学习记忆，解释“\(title)”；说明它为什么重要，并给一个能检查我是否理解的例子。"
                )
            },
            onAnnotationTap: annotations.isEmpty ? nil : { openLearningAnnotations(annotations) }
        )
    }

    private func openLearningAnnotations(_ annotations: [ReaderAnnotationEntry]) {
        if annotations.count == 1 { inspectedLearningAnnotation = annotations[0] }
        else {
            learningAnnotationChoices = annotations
            showingLearningAnnotationChoices = true
        }
    }

    private func learningAnnotations(for excerpt: String) -> [ReaderAnnotationEntry] {
        noteStore.notes.compactMap(ReaderAnnotationEntry.init(note:)).filter {
            $0.bookID == (subscription?.book.id ?? "workbench-learning") && $0.quote == excerpt
        }
    }

    private func saveLearningAnnotation(item: LearningQuestion, question: String, answer: String) {
        let section = currentSection
        _ = ReaderAnnotationEntry.save(
            quote: item.excerpt,
            detail: "我的问题\n\(question)\n\nAI 回答摘要\n\(String(answer.prefix(2_000)))",
            bookID: subscription?.book.id ?? "workbench-learning",
            bookTitle: subscription?.book.title ?? currentTitle,
            sectionID: section?.id ?? "learning-workbench",
            sectionTitle: section?.title ?? "继续学",
            citation: bookBody?.citation ?? "quantum://learning-workbench",
            api: APIClient.shared
        )
    }

    private func openCurrentReading() {
        if let book = subscription?.book { selectedBook = book }
        else {
            learningQuestion = LearningQuestion(
                title: "恢复阅读位置",
                excerpt: lastReadingExcerpt,
                question: "请根据这段上次阅读内容，告诉我应该从哪里继续。"
            )
        }
    }

    private func handlePlanItem(_ item: LearningPlanItem, index: Int) {
        if index == 1 {
            openCurrentReading()
        } else if index == 2 {
            showingExercise = true
        } else {
            learningQuestion = LearningQuestion(
                title: item.title,
                excerpt: lastReadingExcerpt,
                question: "请带我完成“\(item.title)”：\(item.detail) 请直接给出适合我当前水平的讲解。"
            )
        }
    }

    @MainActor
    private func resetLearningPlan() async {
        guard !isResettingPlan else { return }
        isResettingPlan = true
        defer { isResettingPlan = false }
        let memories = (try? await APIClient.shared.fetchHermesMemory().items.map(\.content).joined(separator: "\n")) ?? ""
        let prompt = """
        请基于我的长期记忆、兴趣、能力水平和当前阅读位置，定制一个总计 25 分钟的学习计划。第二项必须是继续阅读；第三项必须是理解题。
        只输出四行，不要 Markdown：
        分钟|标题|一句具体说明
        分钟|标题|一句具体说明
        分钟|标题|一句具体说明
        KEY|从引用原文中原样摘取最关键的一句话
        """
        do {
            let stream = APIClient.shared.chatStream(
                question: prompt,
                quotedContext: "长期记忆：\(String(memories.prefix(3_000)))\n\n当前阅读：\(lastReadingExcerpt)",
                contextScope: learningContextScope
            )
            let answer = try await collectChatAnswer(from: stream)
            if let parsed = LearningPlanResponse.parse(answer) { learningPlan = parsed }
        } catch {
            cleanupMessage = "个性化计划暂时无法更新，已保留当前计划。"
        }
    }

    private func submitAttentionDraft() {
        let prompt = attentionDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else { return }
        attentionDraft = ""
        onPrompt(prompt)
    }

    private func submitCleanupDraft() {
        let prompt = cleanupDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else { return }
        cleanupDraft = ""
        onPrompt(prompt)
    }

    private enum AttentionKind { case study, inspiration, pending }
    private func showsAttention(_ kind: AttentionKind) -> Bool {
        attentionFilter == 0 || (attentionFilter == 1 && kind == .study) || (attentionFilter == 2 && kind == .inspiration) || (attentionFilter == 3 && kind == .pending)
    }

    private var cleanupSessions: [String] {
        sessionManager.sortedSessionIDs().filter { $0 != sessionManager.activeSessionId }
    }
    private func toggle(_ id: String) {
        if selectedCleanupIDs.contains(id) { selectedCleanupIDs.remove(id) } else { selectedCleanupIDs.insert(id) }
    }

    private func performCleanup() {
        let sessions = selectedCleanupIDs.intersection(Set(cleanupSessions))
        sessions.forEach { sessionManager.setLifecycle(.archived, for: $0) }
        selectedCleanupIDs.subtract(sessions)
        cleanupMessage = sessions.isEmpty ? "没有直接执行删除或覆盖。合并和待办仍需在确认卡中继续。" : "已归档 \(sessions.count) 个对话；其余建议未改动。"
    }

    @MainActor private func loadData() async {
        async let fetchedSubscriptions = try? APIClient.shared.fetchBookSubscriptions()
        async let fetchedNotes = try? APIClient.shared.fetchKnowledgeNotes(includeArchived: true)
        subscription = await fetchedSubscriptions?.first
        notes = await fetchedNotes?.items ?? []
        if let book = subscription?.book {
            bookBody = try? await APIClient.shared.fetchKnowledgeBookBody(id: book.id)
        }
        if action.id == "continue-learning" { await resetLearningPlan() }
    }

    @MainActor private func toggleSubscription(_ book: KnowledgeBookDTO) async {
        guard !readerBusy else { return }
        readerBusy = true
        defer { readerBusy = false }
        do {
            try await APIClient.shared.unsubscribeBook(id: book.id)
            subscription = nil
            selectedBook = nil
        } catch {
            cleanupMessage = "暂时无法更新书架，请稍后重试。"
        }
    }
}

private func collectChatAnswer(
    from stream: AsyncThrowingStream<APIClient.StreamEvent, Error>
) async throws -> String {
    var answer = ""
    for try await event in stream {
        switch event {
        case .delta(let text): answer += text
        case .answerPage(let page):
            let value = page.blocks.map(\.content).joined(separator: "\n\n")
            if !value.isEmpty { answer = value }
        case .done(_, let finalAnswer):
            if let finalAnswer, !finalAnswer.isEmpty { answer = finalAnswer }
        case .error(_, let message):
            throw NSError(
                domain: "LearningWorkbench",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: message.isEmpty ? "AI 暂时无法完成请求。" : message]
            )
        default: break
        }
    }
    guard !answer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
        throw NSError(domain: "LearningWorkbench", code: 2, userInfo: [NSLocalizedDescriptionKey: "AI 没有返回内容。"])
    }
    return answer
}

private struct LearningExerciseView: View {
    @Environment(\.dismiss) private var dismiss
    let sourceTitle: String
    let sourceExcerpt: String
    let contextScope: ChatContextScopeDTO
    let onSave: (String, String, String) -> Void
    @State private var question = ""
    @State private var answer = ""
    @State private var feedback = ""
    @State private var isLoading = true
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("理解练习").font(.system(size: 30, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink)
                    Text(sourceTitle).font(.subheadline).foregroundStyle(HomePalette.secondary)
                    PaperCard {
                        Label("题目", systemImage: "doc.text").font(.headline).foregroundStyle(HomePalette.blue)
                        if isLoading && question.isEmpty { ProgressView("正在按你的当前水平出题…") }
                        else { MarkdownText(question).font(.body).foregroundStyle(HomePalette.ink) }
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Text("答题区").font(.headline).foregroundStyle(HomePalette.ink)
                        TextEditor(text: $answer)
                            .frame(minHeight: 180)
                            .padding(10)
                            .scrollContentBackground(.hidden)
                            .background(Color.white.opacity(0.82), in: RoundedRectangle(cornerRadius: 18))
                            .overlay { RoundedRectangle(cornerRadius: 18).stroke(Color(hex: "C9D8E8")) }
                    }
                    if !feedback.isEmpty {
                        PaperCard(tint: Color(hex: "F2F7FF")) {
                            Label("AI 批改", systemImage: "checkmark.seal.fill").font(.headline).foregroundStyle(HomePalette.blue)
                            MarkdownText(feedback).font(.body).foregroundStyle(HomePalette.ink)
                        }
                    }
                    if let errorMessage { Text(errorMessage).font(.footnote).foregroundStyle(.red) }
                    Button { Task { await submit() } } label: {
                        Text(feedback.isEmpty ? "提交答案" : "已保存为批注")
                            .font(.headline).foregroundStyle(.white).frame(maxWidth: .infinity, minHeight: 50)
                            .background(HomePalette.ink, in: Capsule())
                    }
                    .disabled(question.isEmpty || answer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isLoading || !feedback.isEmpty)
                }
                .padding(20)
            }
            .background(QuantumMistBackground())
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("关闭") { dismiss() } }
            }
            .task { await loadQuestion() }
        }
    }

    @MainActor
    private func loadQuestion() async {
        isLoading = true
        defer { isLoading = false }
        do {
            question = try await collectChatAnswer(from: APIClient.shared.chatStream(
                question: "请根据引用内容和我的能力水平出一道 8 分钟可完成的理解题。只输出题目、已知条件和作答要求，不要给答案。",
                quotedContext: sourceExcerpt,
                contextScope: contextScope
            ))
        } catch { errorMessage = error.localizedDescription }
    }

    @MainActor
    private func submit() async {
        isLoading = true
        defer { isLoading = false }
        do {
            feedback = try await collectChatAnswer(from: APIClient.shared.chatStream(
                question: "请批改我的答案。先给结论，再指出正确步骤、遗漏和一个最小改进建议。\n\n题目：\(question)\n\n我的答案：\(answer)",
                quotedContext: sourceExcerpt,
                contextScope: contextScope
            ))
            onSave(question, answer, feedback)
        } catch { errorMessage = error.localizedDescription }
    }
}

private struct HeroStrip: View {
    let title: String; let subtitle: String; let progress: Double
    var body: some View {
        ZStack(alignment: .leading) {
            Image("home_learning_hero").resizable().scaledToFill().frame(height: 128).clipped()
            LinearGradient(colors: [Color.white.opacity(0.98), Color.white.opacity(0.15)], startPoint: .leading, endPoint: .trailing)
            VStack(alignment: .leading, spacing: 8) {
                Text(title).font(.system(size: 24, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink).lineLimit(2)
                Text(subtitle).font(.subheadline).foregroundStyle(HomePalette.secondary).lineLimit(2)
                HStack { ProgressView(value: progress).tint(HomePalette.green).frame(width: 145); Text("\(Int(progress * 100))%").font(.caption.weight(.semibold)).foregroundStyle(HomePalette.secondary) }
            }.padding(16)
        }
        .frame(height: 128).clipShape(RoundedRectangle(cornerRadius: 24)).overlay { RoundedRectangle(cornerRadius: 24).stroke(Color.white, lineWidth: 1) }
    }
}

private struct PaperCard<Content: View>: View {
    var tint: Color = Color.white.opacity(0.78); @ViewBuilder let content: Content
    init(tint: Color = Color.white.opacity(0.78), @ViewBuilder content: () -> Content) { self.tint = tint; self.content = content() }
    var body: some View { VStack(alignment: .leading, spacing: 12) { content }.padding(16).frame(maxWidth: .infinity, alignment: .leading).background(tint, in: RoundedRectangle(cornerRadius: 24)).overlay { RoundedRectangle(cornerRadius: 24).stroke(Color.white, lineWidth: 1) }.shadow(color: HomePalette.shadow, radius: 14, y: 6) }
}

private struct SectionHeading: View {
    let icon: String; let tint: Color; let title: String; let subtitle: String
    var body: some View { HStack(alignment: .top, spacing: 12) { Image(systemName: icon).font(.title2).foregroundStyle(tint).frame(width: 42, height: 42).background(tint.opacity(0.10), in: RoundedRectangle(cornerRadius: 13)); VStack(alignment: .leading, spacing: 3) { Text(title).font(.system(size: 21, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink); Text(subtitle).font(.subheadline).foregroundStyle(HomePalette.secondary) } } }
}

private struct NumberedPoint: View {
    let number: Int; let color: Color; let title: String; let detail: String
    let annotationCount: Int
    let onTap: () -> Void
    let onAnnotationTap: (() -> Void)?
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Button(action: onTap) {
                HStack(alignment: .top, spacing: 12) {
                    Text("\(number)").font(.headline).foregroundStyle(color).frame(width: 32, height: 32).background(color.opacity(0.12), in: Circle())
                    VStack(alignment: .leading, spacing: 3) {
                        Text(title).font(.subheadline.weight(.bold)).foregroundStyle(HomePalette.ink)
                        Text(detail).font(.caption).foregroundStyle(HomePalette.secondary)
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            if annotationCount > 0, let onAnnotationTap {
                Button(action: onAnnotationTap) {
                    ZStack(alignment: .topTrailing) {
                        Image(systemName: "bubble.left.fill").foregroundStyle(HomePalette.blue)
                        Text("\(annotationCount)").font(.system(size: 8, weight: .bold)).foregroundStyle(.white).offset(x: 2, y: 1)
                    }
                    .frame(width: 32, height: 32)
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel("查看 \(annotationCount) 条批注")
            }
        }
    }
}

private struct TimelinePoint: View {
    let done: Bool; var active = false; var isLast = false; let title: String; let detail: String; let onTap: () -> Void
    var body: some View {
        Button(action: onTap) { HStack(alignment: .top, spacing: 12) {
            ZStack(alignment: .top) {
                if !isLast {
                    Rectangle().fill(done ? HomePalette.green.opacity(0.55) : Color(hex: "D7E2EC"))
                        .frame(width: 2, height: 56).offset(y: 18)
                }
                Image(systemName: done ? "checkmark.circle.fill" : (active ? "circle.circle.fill" : "circle.fill"))
                    .font(.title3).foregroundStyle(done ? HomePalette.green : (active ? HomePalette.blue : Color(hex: "CCD6E2")))
                    .background(Color.white.opacity(0.75), in: Circle())
            }.frame(width: 22)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.subheadline.weight(.bold)).foregroundStyle(HomePalette.ink)
                Text(detail).font(.caption).foregroundStyle(HomePalette.secondary)
            }.padding(.bottom, isLast ? 0 : 10)
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(HomePalette.secondary)
        }.contentShape(Rectangle()) }
        .buttonStyle(.plain)
    }
}

private struct NotebookExcerptCard: View {
    let excerpt: String
    let keyText: String
    var body: some View {
        ZStack(alignment: .topTrailing) {
            VStack(alignment: .leading, spacing: 10) {
                Label("上次阅读的内容", systemImage: "book")
                    .font(.subheadline.weight(.semibold)).foregroundStyle(Color(hex: "E98B57"))
                Text(excerpt)
                    .font(.system(size: 15, weight: .regular, design: .serif))
                    .lineLimit(8)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(14)
                    .background(Color.white.opacity(0.72), in: RoundedRectangle(cornerRadius: 10))
                if !keyText.isEmpty {
                    Text("关键句：\(keyText)").font(.caption.weight(.semibold)).foregroundStyle(Color(hex: "F0715C"))
                }
            }
            .font(.subheadline).foregroundStyle(HomePalette.secondary)
            .padding(.leading, 22).padding(16)
            Text("这里是关键  ↙")
                .font(.system(size: 13, weight: .medium, design: .rounded)).italic()
                .foregroundStyle(Color(hex: "F0715C")).rotationEffect(.degrees(-7))
                .padding(.top, 82).padding(.trailing, 12)
            VStack(spacing: 15) {
                ForEach(0..<6, id: \.self) { _ in Circle().fill(Color(hex: "DCE9E5")).frame(width: 8, height: 8) }
            }.padding(.top, 20).padding(.leading, 8).frame(maxWidth: .infinity, alignment: .leading)
            Rectangle().fill(Color(hex: "F5DAB8").opacity(0.72)).frame(width: 62, height: 20)
                .rotationEffect(.degrees(12)).offset(x: 7, y: -5)
        }
        .background(Color(hex: "FFFDF8"), in: RoundedRectangle(cornerRadius: 16))
        .overlay { RoundedRectangle(cornerRadius: 16).stroke(Color.white, lineWidth: 1) }
    }
}

private struct WorkProjectHero: View {
    var body: some View {
        ZStack(alignment: .leading) {
            Image("home_work_hero").resizable().scaledToFill().frame(height: 116).clipped()
            LinearGradient(colors: [Color.white.opacity(0.98), Color.white.opacity(0.12)], startPoint: .leading, endPoint: .trailing)
            VStack(alignment: .leading, spacing: 6) {
                Text("毕业论文资料整理").font(.system(size: 23, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink)
                Text("环境心理学对大学生专注力的影响").font(.subheadline).foregroundStyle(HomePalette.secondary)
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("已完成 4 / 7").font(.caption).foregroundStyle(HomePalette.secondary)
                        ProgressView(value: 4.0 / 7.0).tint(HomePalette.green).frame(width: 142)
                    }
                    Text("今天 14:32 更新").font(.caption2).foregroundStyle(HomePalette.secondary)
                }.padding(.top, 3)
            }.padding(16)
        }
        .frame(height: 116).clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 22).stroke(Color.white, lineWidth: 1) }
    }
}

private enum WorkStepState { case done, active, pending }

private struct WorkProgressCard: View {
    private let steps: [(String, WorkStepState)] = [
        ("整理研究问题", .done), ("导入 8 篇文献", .done), ("完成初步分类", .done),
        ("提取核心观点", .active), ("撰写分析与讨论", .pending), ("整理参考文献", .pending)
    ]
    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            Image("home_work_books").resizable().scaledToFit().frame(width: 145, height: 128)
                .offset(x: 12, y: 16).opacity(0.92).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("上次做到这里").font(.system(size: 22, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink)
                        Text("你已经完成了以下内容，继续完成剩余部分吧。")
                            .font(.subheadline).foregroundStyle(HomePalette.secondary)
                    }
                    Spacer()
                    Text("已经走了很远\n继续加油！").font(.system(size: 12, weight: .medium, design: .rounded)).italic()
                        .foregroundStyle(Color(hex: "478879")).multilineTextAlignment(.center).rotationEffect(.degrees(-7))
                }
                ForEach(steps.indices, id: \.self) { index in
                    WorkProgressStep(title: steps[index].0, state: steps[index].1, isLast: index == steps.count - 1)
                }
            }.padding(16)
        }
        .background(Color.white.opacity(0.80), in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 24).stroke(Color.white, lineWidth: 1) }
        .shadow(color: HomePalette.shadow, radius: 12, y: 5)
    }
}

private struct WorkProgressStep: View {
    let title: String; let state: WorkStepState; let isLast: Bool
    var body: some View {
        HStack(spacing: 10) {
            ZStack(alignment: .top) {
                if !isLast {
                    Rectangle().fill(state == .done ? HomePalette.green.opacity(0.60) : Color(hex: "D4DEE9"))
                        .frame(width: 2, height: 30).offset(y: 17)
                }
                Image(systemName: state == .done ? "checkmark.circle.fill" : (state == .active ? "circle.circle.fill" : "circle.fill"))
                    .foregroundStyle(state == .done ? HomePalette.green : (state == .active ? HomePalette.blue : Color(hex: "C8D2DE")))
                    .font(.title3).background(Color.white, in: Circle())
            }.frame(width: 24)
            Text(title).font(.subheadline.weight(state == .active ? .bold : .medium))
                .foregroundStyle(state == .pending ? HomePalette.secondary : HomePalette.ink)
            Spacer()
        }
        .padding(.horizontal, state == .active ? 8 : 0).frame(minHeight: 34)
        .background(state == .active ? HomePalette.blue.opacity(0.09) : Color.clear, in: Capsule())
    }
}

private struct WorkSuggestionCard: View {
    var body: some View {
        ZStack(alignment: .trailing) {
            LinearGradient(colors: [Color(hex: "EDFFF8"), Color(hex: "F7FFF9")], startPoint: .leading, endPoint: .trailing)
            Image("home_continue_work_art").resizable().scaledToFit().frame(width: 132, height: 132).offset(x: 18, y: 18)
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "doc.text.fill").font(.title2).foregroundStyle(Color(hex: "25B9BC"))
                    .frame(width: 46, height: 46).background(Color.white.opacity(0.75), in: RoundedRectangle(cornerRadius: 14))
                VStack(alignment: .leading, spacing: 4) {
                    Text("建议你现在继续").font(.subheadline.weight(.semibold)).foregroundStyle(HomePalette.ink)
                    Text("整理 8 篇文献的核心观点").font(.system(size: 20, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink)
                    Text("预计 12 分钟 · 不会修改原文件").font(.caption).foregroundStyle(HomePalette.secondary)
                    HStack(spacing: 6) { TagChip("按主题归类"); TagChip("保留来源"); TagChip("生成摘要") }
                }
                Spacer(minLength: 70)
            }.padding(14)
        }
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 22).stroke(Color.white, lineWidth: 1) }
    }
}

private struct WorkPhasesCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("接下来的步骤").font(.system(size: 20, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink)
                Spacer()
                Text("清晰的步骤\n让复杂的任务变简单").font(.system(size: 11, design: .rounded)).italic()
                    .foregroundStyle(Color(hex: "478879")).multilineTextAlignment(.center).rotationEffect(.degrees(-6))
            }
            HStack(spacing: 0) {
                WorkPhase(number: "1", title: "确认整理范围", detail: "核对文献与输出要求", active: true)
                Rectangle().fill(HomePalette.blue.opacity(0.35)).frame(height: 2).offset(y: -18)
                WorkPhase(number: "2", title: "Quantum 整理并生成", detail: "基于你的要求处理内容")
                Rectangle().fill(Color(hex: "D4DEE9")).frame(height: 2).offset(y: -18)
                WorkPhase(number: "3", title: "你检查后保存", detail: "支持继续修改和完善")
            }
        }
        .padding(14).background(Color(hex: "F2F5FF").opacity(0.88), in: RoundedRectangle(cornerRadius: 22))
        .overlay { RoundedRectangle(cornerRadius: 22).stroke(Color.white, lineWidth: 1) }
    }
}

private struct WorkPhase: View {
    let number: String; let title: String; let detail: String; var active = false
    var body: some View {
        VStack(spacing: 4) {
            Text(number).font(.caption.weight(.bold)).foregroundStyle(active ? .white : HomePalette.ink)
                .frame(width: 30, height: 30).background(active ? HomePalette.blue : Color.white.opacity(0.86), in: Circle())
                .overlay { Circle().stroke(active ? HomePalette.blue : Color(hex: "D7E0EA"), lineWidth: 2) }
            Text(title).font(.caption.weight(.semibold)).foregroundStyle(HomePalette.ink).lineLimit(1).minimumScaleFactor(0.72)
            Text(detail).font(.caption2).foregroundStyle(HomePalette.secondary).lineLimit(2).multilineTextAlignment(.center)
        }.frame(maxWidth: .infinity)
    }
}

private struct WorkConfirmationCard: View {
    let onConfirm: () -> Void; let onAdjust: () -> Void; let onRange: () -> Void; let onOutput: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "doc.fill").foregroundStyle(Color(hex: "FF765E"))
                    .frame(width: 42, height: 42).background(Color(hex: "FFE6DE"), in: RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 2) {
                    Text("开始前确认").font(.system(size: 20, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink)
                    Text("请确认以下内容，或根据需要进行调整。 ").font(.caption).foregroundStyle(HomePalette.secondary)
                }
            }
            Button(action: onRange) { WorkConfirmationRow(label: "范围", value: "已导入的 8 篇文献") }.buttonStyle(.plain)
            Button(action: onOutput) { WorkConfirmationRow(label: "输出", value: "结构化笔记") }.buttonStyle(.plain)
            HStack(spacing: 8) {
                Button(action: onConfirm) { HomePrimaryLabel("确认并继续") }.buttonStyle(SoftButtonStyle())
                Button("调整要求", action: onAdjust).font(.subheadline.weight(.semibold)).foregroundStyle(HomePalette.ink)
                    .frame(maxWidth: .infinity, minHeight: 44).background(Color.white.opacity(0.72), in: Capsule())
            }
        }
        .padding(14).background(Color(hex: "FFF8F4").opacity(0.90), in: RoundedRectangle(cornerRadius: 22))
        .overlay { RoundedRectangle(cornerRadius: 22).stroke(Color.white, lineWidth: 1) }
    }
}

private struct WorkConfirmationRow: View {
    let label: String; let value: String
    var body: some View {
        HStack {
            Text(label).font(.subheadline.weight(.semibold)).foregroundStyle(HomePalette.ink).frame(width: 54, alignment: .leading)
            Text(value).font(.subheadline).foregroundStyle(HomePalette.ink)
            Spacer(); Image(systemName: "chevron.right").font(.caption).foregroundStyle(HomePalette.secondary)
        }.padding(.horizontal, 10).frame(minHeight: 40).background(Color.white.opacity(0.65), in: RoundedRectangle(cornerRadius: 11))
    }
}

private struct TagChip: View { let text: String; init(_ text: String) { self.text = text }; var body: some View { Text(text).font(.caption).foregroundStyle(HomePalette.secondary).padding(.horizontal, 10).padding(.vertical, 6).background(Color.white.opacity(0.7), in: Capsule()) } }

private struct CleanupHero: View {
    let count: Int
    var body: some View {
        ZStack(alignment: .leading) {
            VStack(alignment: .leading, spacing: 7) {
                Text("让知识空间轻一点")
                    .font(.system(size: 30, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink)
                Text("我找到了 \(count) 条可以整理的内容，\n任何删除或覆盖都会先问你。")
                    .font(.system(size: 15)).foregroundStyle(HomePalette.secondary).lineSpacing(5)
            }.frame(maxWidth: .infinity, alignment: .leading)
            Image("home_cleanup_art").resizable().scaledToFit().frame(width: 158, height: 138)
                .frame(maxWidth: .infinity, alignment: .trailing).offset(x: 15, y: 12).accessibilityHidden(true)
            Text("整理\n让学习更轻松\n♡").font(.system(size: 10, weight: .medium, design: .rounded)).italic()
                .multilineTextAlignment(.center).foregroundStyle(Color(hex: "43515D"))
                .rotationEffect(.degrees(-6)).frame(width: 76, height: 62)
                .background(Color(hex: "FFE8A4").opacity(0.92))
                .frame(maxWidth: .infinity, alignment: .trailing).padding(.trailing, 4).offset(y: -28)
        }.frame(height: 145)
    }
}

private struct CleanupFilterBar: View {
    @Binding var selection: Int
    private let items = ["全部  12", "对话  4", "笔记  5", "待办  3"]
    var body: some View {
        HStack(spacing: 4) {
            ForEach(items.indices, id: \.self) { index in
                Button { selection = index } label: {
                    Text(items[index]).font(.subheadline.weight(selection == index ? .semibold : .regular))
                        .foregroundStyle(selection == index ? HomePalette.ink : HomePalette.secondary)
                        .frame(maxWidth: .infinity, minHeight: 42)
                        .background(selection == index ? HomePalette.mint : Color.clear, in: Capsule())
                }.buttonStyle(.plain)
            }
        }.padding(4).background(Color.white.opacity(0.72), in: Capsule())
            .overlay { Capsule().stroke(Color.white, lineWidth: 1) }
    }
}

private struct CleanupSectionHeader: View {
    let icon: String; let tint: Color; let title: String; let subtitle: String
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon).font(.title2).foregroundStyle(tint)
                .frame(width: 50, height: 50).background(tint.opacity(0.10), in: RoundedRectangle(cornerRadius: 14))
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.system(size: 20, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink)
                Text(subtitle).font(.subheadline).foregroundStyle(HomePalette.secondary)
            }
        }
    }
}

private struct CleanupArchiveCard: View {
    let chatSelected: Bool; let noteSelected: Bool
    let onChat: () -> Void; let onNote: () -> Void; let onArchiveChat: () -> Void; let onArchiveNote: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            CleanupSectionHeader(icon: "folder.fill", tint: Color(hex: "2FC393"), title: "建议归档", subtitle: "这些内容仍有参考价值，建议归档保存。")
            CleanupArchiveRow(selected: chatSelected, icon: "bubble.left.and.bubble.right.fill", title: "3 个已完成的学习对话", detail: "原因：话题已完成，且超过 30 天未继续讨论，\n建议归档以保持对话列表整洁。", date: "2024 年 5 月 12 日", onToggle: onChat, onArchive: onArchiveChat)
            CleanupArchiveRow(selected: noteSelected, icon: "doc.text.fill", title: "毕业论文资料整理 · 阶段记录", detail: "原因：已完成该阶段的资料收集，建议归档\n便于后续查阅。", date: "2024 年 6 月 3 日", onToggle: onNote, onArchive: onArchiveNote)
        }.padding(12).background(Color(hex: "F2FCF8").opacity(0.86), in: RoundedRectangle(cornerRadius: 22))
            .overlay { RoundedRectangle(cornerRadius: 22).stroke(Color.white, lineWidth: 1) }
    }
}

private struct CleanupArchiveRow: View {
    let selected: Bool; let icon: String; let title: String; let detail: String; let date: String
    let onToggle: () -> Void; let onArchive: () -> Void
    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            Button(action: onToggle) { Image(systemName: selected ? "checkmark.square.fill" : "square").font(.title3).foregroundStyle(selected ? HomePalette.blue : HomePalette.secondary) }.buttonStyle(.plain).padding(.top, 8)
            Image(systemName: icon).foregroundStyle(HomePalette.blue).frame(width: 42, height: 42).background(HomePalette.blue.opacity(0.10), in: RoundedRectangle(cornerRadius: 12))
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.subheadline.weight(.bold)).foregroundStyle(HomePalette.ink)
                Text(detail).font(.caption).foregroundStyle(HomePalette.secondary).lineSpacing(2)
                Text(date).font(.caption2).foregroundStyle(HomePalette.secondary)
            }
            Spacer(minLength: 2)
            Button("归档", action: onArchive).font(.caption.weight(.semibold)).foregroundStyle(HomePalette.blue)
                .padding(.horizontal, 15).frame(height: 36).background(HomePalette.blue.opacity(0.10), in: Capsule())
        }.padding(10).background(Color.white.opacity(0.72), in: RoundedRectangle(cornerRadius: 17))
    }
}

private struct CleanupMergeCard: View {
    let selected: Bool; let onToggle: () -> Void; let onReview: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            CleanupSectionHeader(icon: "arrow.triangle.merge", tint: Color(hex: "7569EA"), title: "建议合并", subtitle: "这些内容主题相近，合并后更清晰。")
            HStack(alignment: .top, spacing: 9) {
                Button(action: onToggle) { Image(systemName: selected ? "checkmark.square.fill" : "square").font(.title3).foregroundStyle(selected ? HomePalette.blue : HomePalette.secondary) }.buttonStyle(.plain).padding(.top, 7)
                Image(systemName: "doc.text.fill").foregroundStyle(HomePalette.blue).frame(width: 42, height: 42).background(HomePalette.blue.opacity(0.10), in: RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 5) {
                    HStack { Text("线性代数复习").font(.subheadline.weight(.bold)); Spacer(); Button("合并为 1 条", action: onReview).font(.caption.weight(.semibold)).foregroundStyle(Color(hex: "6757E8")).padding(.horizontal, 10).frame(height: 30).background(HomePalette.lilac, in: Capsule()); Image(systemName: "chevron.right").font(.caption).foregroundStyle(HomePalette.secondary) }
                    Text("线性代数重点整理").font(.caption).foregroundStyle(HomePalette.secondary)
                    HStack(spacing: 7) {
                        CleanupPreview(title: "线性代数复习", lines: "· 向量空间的定义…\n· 矩阵的特征值…")
                        Image(systemName: "arrow.left.arrow.right").foregroundStyle(HomePalette.secondary)
                        CleanupPreview(title: "线性代数重点整理", lines: "· 特征值与特征向量…\n· 相似矩阵的性质…")
                    }
                    Text("2024 年 5 月 28 日").font(.caption2).foregroundStyle(HomePalette.secondary)
                }.foregroundStyle(HomePalette.ink)
            }.padding(10).background(Color.white.opacity(0.72), in: RoundedRectangle(cornerRadius: 17))
        }.padding(12).background(Color(hex: "F4F5FF").opacity(0.88), in: RoundedRectangle(cornerRadius: 22))
            .overlay { RoundedRectangle(cornerRadius: 22).stroke(Color.white, lineWidth: 1) }
    }
}

private struct CleanupPreview: View {
    let title: String; let lines: String
    var body: some View { VStack(alignment: .leading, spacing: 2) { Text(title).font(.caption2.weight(.medium)); Text(lines).font(.system(size: 9)).foregroundStyle(HomePalette.secondary).lineLimit(2) }.padding(7).frame(maxWidth: .infinity, alignment: .leading).background(Color(hex: "EEF4FF"), in: RoundedRectangle(cornerRadius: 8)) }
}

private struct CleanupDecisionCard: View {
    let selected: Bool; let onToggle: () -> Void; let onReview: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            CleanupSectionHeader(icon: "exclamationmark", tint: HomePalette.coral, title: "需要你决定", subtitle: "这些内容可能不再需要，请确认后再处理。")
            HStack(alignment: .top, spacing: 9) {
                Button(action: onToggle) { Image(systemName: selected ? "checkmark.square.fill" : "square").font(.title3).foregroundStyle(selected ? HomePalette.blue : HomePalette.secondary) }.buttonStyle(.plain).padding(.top, 8)
                Image(systemName: "calendar.badge.exclamationmark").foregroundStyle(HomePalette.coral).frame(width: 42, height: 42).background(HomePalette.coral.opacity(0.10), in: RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 3) { HStack(spacing: 6) { Text("2 条重复待办").font(.subheadline.weight(.bold)); Text("可能删除").font(.caption2).foregroundStyle(HomePalette.coral).padding(.horizontal, 7).padding(.vertical, 3).background(HomePalette.coral.opacity(0.1), in: Capsule()) }; Text("原因：内容高度相似，可能是重复创建。").font(.caption).foregroundStyle(HomePalette.secondary); Text("2024 年 6 月 1 日").font(.caption2).foregroundStyle(HomePalette.secondary) }
                Spacer(minLength: 2)
                Button(action: onReview) { HStack(spacing: 6) { Text("查看内容"); Image(systemName: "chevron.right").font(.caption) } }.font(.caption.weight(.semibold)).foregroundStyle(HomePalette.ink).padding(.horizontal, 12).frame(height: 36).background(Color.white.opacity(0.80), in: Capsule())
            }.padding(10).background(Color.white.opacity(0.72), in: RoundedRectangle(cornerRadius: 17))
        }.padding(12).background(Color(hex: "FFF4F2").opacity(0.88), in: RoundedRectangle(cornerRadius: 22))
            .overlay { RoundedRectangle(cornerRadius: 22).stroke(Color.white, lineWidth: 1) }
    }
}

private struct CleanupSelectionBar: View {
    let count: Int; let onLater: () -> Void; let onConfirm: () -> Void
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "checkmark.circle.fill").font(.title2).foregroundStyle(HomePalette.green)
            VStack(alignment: .leading, spacing: 2) { Text("下一步仍可逐项取消").font(.caption).foregroundStyle(HomePalette.secondary); Text("已选择 \(count) 条").font(.headline).foregroundStyle(HomePalette.ink); Text("不会自动删除或覆盖，请先确认。").font(.caption2).foregroundStyle(HomePalette.secondary) }
            Spacer(minLength: 0)
            Button("稍后处理", action: onLater).font(.caption.weight(.semibold)).foregroundStyle(HomePalette.ink).padding(.horizontal, 14).frame(height: 40).background(Color.white.opacity(0.78), in: Capsule())
            Button("查看确认单", action: onConfirm).font(.caption.weight(.semibold)).foregroundStyle(.white).padding(.horizontal, 14).frame(height: 40).background(HomePalette.ink, in: Capsule()).disabled(count == 0)
        }.padding(12).background(HomePalette.mint.opacity(0.90), in: RoundedRectangle(cornerRadius: 20))
            .overlay(alignment: .topTrailing) { Image("home_attention_botanical").resizable().scaledToFit().frame(width: 130, height: 52).opacity(0.55).offset(y: -8).allowsHitTesting(false) }
    }
}

private struct ArchiveConfirmationView: View {
    let sessionIDs: [String]
    let onLater: () -> Void
    let onContinue: (String?) -> Void
    let onConfirm: ([String]) -> Void

    @State private var selected: Set<Int>
    @State private var expanded: Set<Int> = []
    @State private var isAdjusting = false

    init(
        sessionIDs: [String],
        onLater: @escaping () -> Void,
        onContinue: @escaping (String?) -> Void,
        onConfirm: @escaping ([String]) -> Void
    ) {
        self.sessionIDs = sessionIDs
        self.onLater = onLater
        self.onContinue = onContinue
        self.onConfirm = onConfirm
        _selected = State(initialValue: [0, 1])
    }

    var body: some View {
        ZStack {
            QuantumMistBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    header
                    hero
                    summary
                    sectionTitle("建议归档", subtitle: "已完成且证据完整的学习对话")
                    archiveCard(index: 0)
                    archiveCard(index: 1)
                    sectionTitle("暂不归档", subtitle: "仍在进行中的内容")
                    pendingCard
                    reassurance
                }
                .padding(.horizontal, 18)
                .padding(.bottom, 20)
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { actionBar }
        .toolbar(.hidden, for: .navigationBar)
    }

    private var header: some View {
        HStack {
            Button(action: onLater) {
                Image(systemName: "chevron.left")
                    .font(.title3.weight(.semibold))
                    .frame(width: 44, height: 44)
            }
            Spacer()
            Text("归档确认")
                .font(.headline.weight(.bold))
            Spacer()
            Button(selected.isEmpty ? "全选" : "全不选") {
                selected = selected.isEmpty ? [0, 1] : []
            }
            .font(.subheadline.weight(.semibold))
            .frame(width: 58, height: 44)
        }
        .foregroundStyle(HomePalette.ink)
        .padding(.top, 4)
    }

    private var hero: some View {
        ZStack(alignment: .leading) {
            LinearGradient(
                colors: [Color.white.opacity(0.96), HomePalette.mint.opacity(0.88)],
                startPoint: .leading,
                endPoint: .trailing
            )
            Image("home_attention_botanical")
                .resizable().scaledToFit()
                .frame(width: 210, height: 132)
                .frame(maxWidth: .infinity, alignment: .trailing)
                .offset(x: 36, y: 5)
                .accessibilityHidden(true)
            Image("home_cleanup_art")
                .resizable().scaledToFit()
                .frame(width: 92, height: 92)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                .offset(x: 6, y: 14)
                .opacity(0.88)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 7) {
                Image(systemName: "folder.badge.checkmark")
                    .font(.system(size: 23, weight: .semibold))
                    .foregroundStyle(Color(hex: "27B98C"))
                    .frame(width: 46, height: 46)
                    .background(Color.white.opacity(0.78), in: RoundedRectangle(cornerRadius: 14))
                Text("整理前，再确认一次")
                    .font(.system(size: 23, weight: .bold, design: .serif))
                    .foregroundStyle(HomePalette.ink)
                Text("已找到 2 条可以安全归档的学习对话")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Color(hex: "56718D"))
                Label("归档后仍可恢复，不会删除内容。", systemImage: "arrow.uturn.backward.circle")
                    .font(.caption)
                    .foregroundStyle(HomePalette.secondary)
            }
            .padding(18)
        }
        .frame(height: 192)
        .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 26).stroke(Color.white, lineWidth: 1) }
        .shadow(color: HomePalette.shadow, radius: 16, y: 7)
    }

    private var summary: some View {
        HStack(spacing: 8) {
            ArchiveSummaryPill(title: "待归档", value: "\(selected.count)", tint: Color(hex: "36C69C"))
            ArchiveSummaryPill(title: "暂不处理", value: "1", tint: HomePalette.coral)
            ArchiveSummaryPill(title: "可恢复", value: "", tint: HomePalette.blue, icon: "arrow.uturn.backward")
        }
    }

    private func sectionTitle(_ title: String, subtitle: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(.system(size: 22, weight: .bold, design: .serif))
                .foregroundStyle(HomePalette.ink)
            Spacer()
            Text(subtitle)
                .font(.caption)
                .foregroundStyle(HomePalette.secondary)
        }
        .padding(.top, 2)
    }

    private func archiveCard(index: Int) -> some View {
        let content = ArchiveConfirmationContent.archive[index]
        return VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 11) {
                Button { toggle(index) } label: {
                    Image(systemName: selected.contains(index) ? "checkmark.square.fill" : "square")
                        .font(.title2)
                        .foregroundStyle(selected.contains(index) ? HomePalette.blue : Color(hex: "A9B8C8"))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(selected.contains(index) ? "取消选择" : "选择归档")
                Image(systemName: "bubble.left.and.bubble.right.fill")
                    .foregroundStyle(HomePalette.blue)
                    .frame(width: 44, height: 44)
                    .background(HomePalette.blue.opacity(0.10), in: RoundedRectangle(cornerRadius: 13))
                VStack(alignment: .leading, spacing: 4) {
                    Text(content.title)
                        .font(.system(size: 17, weight: .bold))
                        .foregroundStyle(HomePalette.ink)
                    Text(content.purpose)
                        .font(.subheadline)
                        .foregroundStyle(HomePalette.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            HStack(spacing: 7) {
                ArchiveTag("已完成", color: Color(hex: "29B889"))
                ArchiveTag(index == 0 ? "证据完整" : "可随时恢复", color: HomePalette.blue)
                if index == 0 { ArchiveTag("可信度 96%", color: Color(hex: "7B68E8")) }
                Spacer(minLength: 0)
            }
            if expanded.contains(index) {
                VStack(alignment: .leading, spacing: 6) {
                    Label("学习目标与对话结果一致", systemImage: "checkmark.seal.fill")
                    Label(index == 0 ? "关键结论已有来源记录" : "已完成复核且无待执行步骤", systemImage: "doc.text.magnifyingglass")
                    Label("归档不会移除笔记或学习记录", systemImage: "lock.open")
                }
                .font(.caption)
                .foregroundStyle(Color(hex: "58708A"))
                .padding(11)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(hex: "F1F8FF"), in: RoundedRectangle(cornerRadius: 13))
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
            HStack {
                Label(index == 0 ? "5 月 12 日" : "6 月 3 日", systemImage: "calendar")
                Text(index == 0 ? "4 轮对话" : "2 轮对话")
                Spacer()
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        if expanded.contains(index) { expanded.remove(index) } else { expanded.insert(index) }
                    }
                } label: {
                    HStack(spacing: 5) {
                        Text(expanded.contains(index) ? "收起依据" : "查看依据")
                        Image(systemName: expanded.contains(index) ? "chevron.up" : "chevron.right")
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(HomePalette.blue)
                    .padding(.horizontal, 13)
                    .frame(height: 34)
                    .background(HomePalette.blue.opacity(0.10), in: Capsule())
                }
                .buttonStyle(.plain)
            }
            .font(.caption)
            .foregroundStyle(HomePalette.secondary)
        }
        .padding(15)
        .background(
            selected.contains(index) ? Color(hex: "F3FAFF").opacity(0.95) : Color.white.opacity(0.78),
            in: RoundedRectangle(cornerRadius: 22)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 22)
                .stroke(selected.contains(index) ? HomePalette.blue.opacity(0.38) : Color.white, lineWidth: 1)
        }
        .shadow(color: HomePalette.shadow, radius: 13, y: 5)
    }

    private var pendingCard: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "hourglass")
                .font(.title3.weight(.semibold))
                .foregroundStyle(HomePalette.coral)
                .frame(width: 44, height: 44)
                .background(HomePalette.coral.opacity(0.10), in: RoundedRectangle(cornerRadius: 13))
            VStack(alignment: .leading, spacing: 4) {
                Text("第三个学习对话仍未完成")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundStyle(HomePalette.ink)
                Text("还有待核验内容，暂不生成归档确认单。")
                    .font(.subheadline)
                    .foregroundStyle(HomePalette.secondary)
                ArchiveTag("暂不归档", color: HomePalette.coral)
            }
            Spacer(minLength: 4)
            Button("继续学习") { onContinue(sessionIDs.indices.contains(2) ? sessionIDs[2] : nil) }
                .font(.caption.weight(.semibold))
                .foregroundStyle(HomePalette.ink)
                .padding(.horizontal, 13)
                .frame(height: 36)
                .background(Color.white.opacity(0.86), in: Capsule())
                .buttonStyle(.plain)
        }
        .padding(15)
        .background(Color(hex: "FFF4F1").opacity(0.92), in: RoundedRectangle(cornerRadius: 22))
        .overlay { RoundedRectangle(cornerRadius: 22).stroke(Color.white, lineWidth: 1) }
    }

    private var reassurance: some View {
        HStack(spacing: 12) {
            Image(systemName: "checkmark.shield.fill")
                .font(.title2)
                .foregroundStyle(Color(hex: "2DBE91"))
            VStack(alignment: .leading, spacing: 2) {
                Text("这次操作不会删除任何内容")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(HomePalette.ink)
                Text("归档后可在会话历史中恢复。")
                    .font(.caption)
                    .foregroundStyle(HomePalette.secondary)
            }
            Spacer()
            Image("home_attention_botanical")
                .resizable().scaledToFit().frame(width: 92, height: 54).opacity(0.65)
                .accessibilityHidden(true)
        }
        .padding(14)
        .background(HomePalette.mint.opacity(0.88), in: RoundedRectangle(cornerRadius: 20))
    }

    private var actionBar: some View {
        VStack(spacing: 8) {
            if isAdjusting {
                Text("点选卡片左上角，可逐项保留或取消归档。")
                    .font(.caption)
                    .foregroundStyle(HomePalette.secondary)
                    .transition(.opacity)
            }
            HStack(spacing: 10) {
                Button("稍后处理", action: onLater)
                    .foregroundStyle(HomePalette.ink)
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .background(Color.white.opacity(0.82), in: Capsule())
                Button { onConfirm(selected.compactMap { sessionIDs.indices.contains($0) ? sessionIDs[$0] : nil }) } label: {
                    Text("确认归档 \(selected.count) 条")
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(HomePalette.ink, in: Capsule())
                }
                .disabled(selected.isEmpty)
                .opacity(selected.isEmpty ? 0.45 : 1)
            }
            .font(.subheadline.weight(.semibold))
            Button(isAdjusting ? "完成调整" : "逐项调整") {
                withAnimation(.easeInOut(duration: 0.2)) { isAdjusting.toggle() }
            }
            .font(.caption.weight(.semibold))
            .foregroundStyle(HomePalette.blue)
        }
        .padding(.horizontal, 18)
        .padding(.top, 12)
        .padding(.bottom, 6)
        .background(.ultraThinMaterial)
    }

    private func toggle(_ index: Int) {
        if selected.contains(index) { selected.remove(index) } else { selected.insert(index) }
    }
}

private enum ArchiveConfirmationContent {
    static let archive = [
        (title: "人工智能输出核验必要性", purpose: "理解为什么需要核验 AI 输出"),
        (title: "AI 说完成了，为什么你还要看收据", purpose: "训练证据意识与结果复核")
    ]
}

private struct ArchiveSummaryPill: View {
    let title: String
    let value: String
    let tint: Color
    var icon: String? = nil
    var body: some View {
        HStack(spacing: 5) {
            if let icon { Image(systemName: icon).font(.caption.weight(.bold)) }
            Text(title).font(.caption)
            if !value.isEmpty { Text(value).font(.caption.weight(.bold)) }
        }
        .foregroundStyle(tint)
        .frame(maxWidth: .infinity, minHeight: 38)
        .background(tint.opacity(0.09), in: Capsule())
        .overlay { Capsule().stroke(Color.white, lineWidth: 1) }
    }
}

private struct ArchiveTag: View {
    let text: String
    let color: Color
    init(_ text: String, color: Color) { self.text = text; self.color = color }
    var body: some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(color.opacity(0.09), in: Capsule())
    }
}

private struct AttentionFilterBar: View {
    @Binding var selection: Int
    private let items = ["全部  3", "学习提醒  1", "灵感  1", "待处理  1"]
    var body: some View {
        HStack(spacing: 4) {
            ForEach(items.indices, id: \.self) { index in
                Button { selection = index } label: {
                    Text(items[index]).font(.caption.weight(selection == index ? .semibold : .regular))
                        .foregroundStyle(selection == index ? HomePalette.ink : HomePalette.secondary)
                        .frame(maxWidth: .infinity, minHeight: 42)
                        .background(selection == index ? HomePalette.mint : Color.white.opacity(0.45), in: Capsule())
                }.buttonStyle(.plain)
            }
        }
        .padding(4).background(Color.white.opacity(0.68), in: Capsule())
        .overlay { Capsule().stroke(Color.white, lineWidth: 1) }
    }
}

private struct AttentionIntroCard: View {
    var body: some View {
        ZStack(alignment: .leading) {
            LinearGradient(colors: [Color.white.opacity(0.94), HomePalette.mint.opacity(0.72)], startPoint: .leading, endPoint: .trailing)
            Image("home_attention_botanical").resizable().scaledToFit()
                .frame(width: 205, height: 116).frame(maxWidth: .infinity, alignment: .trailing)
                .offset(x: 22).accessibilityHidden(true)
            Text("这些内容来自你的计划、阅读进度和\n最近批注。你可以调整偏好，不喜欢\n的内容随时隐藏。")
                .font(.system(size: 15, weight: .medium)).foregroundStyle(Color(hex: "536D8B"))
                .lineSpacing(5).padding(.leading, 16)
            Text("让每一次努力\n都更有方向\n♡").font(.system(size: 10, weight: .medium, design: .rounded)).italic()
                .multilineTextAlignment(.center).foregroundStyle(Color(hex: "43515D"))
                .rotationEffect(.degrees(-5)).frame(width: 76, height: 62)
                .background(Color(hex: "FFE8A4").opacity(0.92))
                .frame(maxWidth: .infinity, alignment: .trailing).padding(.trailing, 12).offset(y: -6)
        }
        .frame(height: 112).clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 22).stroke(Color.white, lineWidth: 1) }
    }
}

private struct AttentionSectionTitle: View {
    let title: String; let subtitle: String
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(.system(size: 24, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink)
            Spacer()
            Rectangle().fill(Color(hex: "B6C4D4")).frame(width: 18, height: 1)
            Text(subtitle).font(.caption).foregroundStyle(HomePalette.secondary)
        }
    }
}

private struct AttentionFocusCard: View {
    let icon: String; let tint: Color; let background: Color
    let title: String; let subtitle: String
    let reasonIcon: String; let reasonTitle: String; let reason: String
    let primary: String; let secondary: String; let primaryTint: Color; let note: String?
    let action: () -> Void; let secondaryAction: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: icon).font(.title2).foregroundStyle(tint)
                    .frame(width: 48, height: 48).background(tint.opacity(0.10), in: RoundedRectangle(cornerRadius: 14))
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).font(.system(size: 20, weight: .bold, design: .serif)).foregroundStyle(HomePalette.ink)
                    Text(subtitle).font(.subheadline).foregroundStyle(HomePalette.secondary).lineSpacing(2)
                }
                Spacer(minLength: 0)
                if let note {
                    Text(note).font(.system(size: 12, weight: .medium, design: .rounded)).italic()
                        .foregroundStyle(Color(hex: "478879")).multilineTextAlignment(.center)
                        .rotationEffect(.degrees(-7)).frame(width: 112).padding(.top, 4)
                } else {
                    Image("home_attention_botanical").resizable().scaledToFit().frame(width: 105, height: 64).offset(x: 16, y: -10)
                }
            }
            HStack(spacing: 10) {
                Image(systemName: reasonIcon).foregroundStyle(tint).frame(width: 34, height: 34).background(tint.opacity(0.10), in: Circle())
                VStack(alignment: .leading, spacing: 1) {
                    Text(reasonTitle).font(.caption.weight(.semibold)).foregroundStyle(HomePalette.ink)
                    Text(reason).font(.caption).foregroundStyle(HomePalette.secondary)
                }
            }
            .padding(.horizontal, 10).frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
            .background(Color.white.opacity(0.48), in: RoundedRectangle(cornerRadius: 13))
            HStack(spacing: 8) {
                Button(primary, action: action).font(.subheadline.weight(.semibold)).foregroundStyle(.white)
                    .frame(maxWidth: .infinity, minHeight: 42).background(primaryTint, in: Capsule())
                Button(secondary, action: secondaryAction).font(.subheadline.weight(.semibold)).foregroundStyle(HomePalette.ink)
                    .frame(maxWidth: .infinity, minHeight: 42).background(Color.white.opacity(0.72), in: Capsule())
                Menu {
                    Button("在对话中继续", action: action)
                    Button("本页暂时隐藏", action: secondaryAction)
                } label: { Image(systemName: "ellipsis").foregroundStyle(HomePalette.ink).frame(width: 42, height: 42).background(Color.white.opacity(0.72), in: Circle()) }
            }
        }
        .padding(14).background(background, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 22).stroke(Color.white, lineWidth: 1) }
        .shadow(color: HomePalette.shadow, radius: 12, y: 5)
    }
}

private struct AttentionSettingButton: View {
    let icon: String; let title: String; var tint = HomePalette.secondary; let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: icon).foregroundStyle(tint)
                Text(title).foregroundStyle(tint).lineLimit(1).minimumScaleFactor(0.72)
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(HomePalette.secondary)
            }.font(.caption).frame(maxWidth: .infinity, minHeight: 34)
        }.buttonStyle(.plain)
    }
}

private struct AttentionManagementSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var frequency = 1
    @State private var learning = true
    @State private var inspiration = true
    @State private var pending = true

    var body: some View {
        NavigationStack {
            Form {
                Section("提醒频率") {
                    Picker("频率", selection: $frequency) {
                        Text("少").tag(0); Text("适中").tag(1); Text("多").tag(2)
                    }.pickerStyle(.segmented)
                }
                Section("显示内容") {
                    Toggle("学习提醒", isOn: $learning)
                    Toggle("值得回看的灵感", isOn: $inspiration)
                    Toggle("稍后处理", isOn: $pending)
                }
            }
            .navigationTitle("管理为你留意")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } } }
        }
    }
}
