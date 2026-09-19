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
    public let onWelcomePrompt: ((String) -> Void)?
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
        onWelcomePrompt: ((String) -> Void)? = nil
    ) {
        self.coordinator = coordinator
        self.onBackgroundTap = onBackgroundTap
        self.onStartTopic = onStartTopic
        self.onWelcomePrompt = onWelcomePrompt
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
                    ChatWelcomeView(onPrompt: onWelcomePrompt)
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

private struct ChatWelcomeView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var appeared = false
    let onPrompt: ((String) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            Text("今天，想把什么变简单？")
                .font(.system(size: 32, weight: .bold, design: .rounded))
                .foregroundStyle(AppTheme.Colors.textPrimary)
            Text("一起读、想、做点新东西。")
                .font(.system(size: 17, weight: .medium, design: .rounded))
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .padding(.top, -AppTheme.Spacing.md)

            knowledgeScene

            VStack(spacing: AppTheme.Spacing.sm) {
                suggestion("帮我理解一个概念", subtitle: "用简单的例子说明", symbol: "leaf.fill", prompt: "帮我用简单的例子理解一个概念。")
                suggestion("帮我整理这篇文章", subtitle: "提炼重点", symbol: "doc.text.fill", prompt: "帮我整理一篇文章并提炼重点。")
                suggestion("给我一些学习建议", subtitle: "提升专注力的方法", symbol: "lightbulb.fill", prompt: "给我一些能提升专注力的学习建议。")
            }
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
        .accessibilityLabel("今天，想把什么变简单？")
    }

    private var knowledgeScene: some View {
        ZStack {
            Image("knowledge_home_hero")
                .resizable()
                .scaledToFill()
                .frame(maxWidth: .infinity)
                .frame(height: 218)
                .clipped()
            LinearGradient(
                colors: [.clear, Color.black.opacity(0.54)],
                startPoint: .top,
                endPoint: .bottom
            )
            VStack(alignment: .leading, spacing: 5) {
                Spacer()
                Text("FOR YOU")
                    .font(.caption2.weight(.bold))
                    .tracking(1.8)
                Text("留一点时间给好奇心")
                    .font(.title3.weight(.semibold))
            }
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(AppTheme.Spacing.lg)
        }
        .frame(height: 218)
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .stroke(Color.white.opacity(0.72), lineWidth: 1)
        }
        .shadow(color: AppTheme.Colors.primary.opacity(0.08), radius: 18, y: 8)
        .accessibilityHidden(true)
    }

    private func suggestion(_ title: String, subtitle: String, symbol _: String, prompt: String) -> some View {
        Button { onPrompt?(prompt) } label: {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(ContentAssetLibrary.contentIconName(for: "\(title) \(subtitle)"))
                    .resizable()
                    .scaledToFit()
                    .padding(4)
                    .frame(width: 38, height: 38)
                    .background(AppTheme.Colors.surfaceTint, in: Circle())
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(AppTheme.Typography.supporting.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text(subtitle)
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .frame(maxWidth: .infinity, minHeight: 54)
            .background(.ultraThinMaterial, in: Capsule())
            .background(Color.white.opacity(0.42), in: Capsule())
            .overlay { Capsule().stroke(Color.white.opacity(0.82), lineWidth: 0.8) }
            .contentShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityHint("发送到对话")
    }
}
