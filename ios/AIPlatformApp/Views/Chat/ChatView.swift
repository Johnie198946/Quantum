//
//  ChatView.swift
//  AIPlatformApp
//
//  Microkernel Canvas for iOS Agent Chat (DeepSeek Harness Pattern)
//  Governed footprint (<= 200 lines), zero business clutter, pure declarative UI.
//

import SwiftUI

enum ChatDraftSubmission {
    static func consume(_ draft: inout String) -> String? {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        draft = ""
        return text
    }
}

public struct ChatView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var sessionManager: SessionManager
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var coordinator = TenantSessionCoordinator.shared
    @StateObject private var speechService = SpeechRecognizerService()

    @State private var isShowingClearAlert: Bool = false
    @State private var isVoicePressing: Bool = false
    @State private var voiceInputPrefix: String = ""
    @State private var showingPlusMenu: Bool = false
    @State private var showingAttachmentTray: Bool = false
    @State private var showingSessionDrawer: Bool = false
    @State private var showingAgentPicker: Bool = false
    @State private var showingTopicDiscussion: Bool = false
    @State private var tenantAgents: [TenantAgentDTO] = []
    @State private var dismissKeyboardToken = 0
    // Keep the draft local so every keystroke does not publish through the
    // session coordinator and invalidate the whole message stream.
    @State private var draftText: String = ""

    private let waitingTimer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    public init() {}

    public var body: some View {
        NavigationStack {
            ZStack {
                if coordinator.messages.isEmpty {
                    QuantumMistBackground()
                } else {
                    Color(hex: "FCFBF7").ignoresSafeArea()
                }

                VStack(spacing: 0) {
                    ChatTopBarView(
                        isGenerating: coordinator.isGenerating,
                        title: coordinator.sessionManager.title(for: coordinator.sessionManager.activeSessionID()),
                        onTitleTap: { showingSessionDrawer = true },
                        onNewSession: { coordinator.newSession() },
                        onHistoryTap: { showingSessionDrawer = true },
                        onClearTap: { isShowingClearAlert = true }
                    )
                    if let topic = currentTopic {
                        topicControlBar(topic)
                    }
                    ChatMessageStreamView(
                        coordinator: coordinator,
                        onBackgroundTap: dismissKeyboard,
                        onStartTopic: { message in
                            coordinator.startTargetedTopic(from: message)
                            showingTopicDiscussion = currentTopic != nil
                        },
                        onWelcomePrompt: { coordinator.sendMessage(text: $0) }
                    )
                }

                if isVoicePressing || speechService.state == .recording {
                    ChatVoiceCaptureView(
                        transcript: speechService.transcript.isEmpty ? draftText : speechService.transcript,
                        elapsedSeconds: speechService.elapsedSeconds,
                        onCancel: {
                            speechService.cancel()
                            isVoicePressing = false
                        }
                    )
                    .transition(.opacity)
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                VStack(spacing: 0) {
                    ChatInputBar(
                        inputText: $draftText,
                        quotedContext: $coordinator.quotedContext,
                        isVoicePressing: $isVoicePressing,
                        speechService: speechService,
                        isGenerating: coordinator.isGenerating,
                        dismissKeyboardToken: dismissKeyboardToken,
                        onSend: {
                            guard let text = ChatDraftSubmission.consume(&draftText) else { return }
                            coordinator.sendMessage(text: text)
                            dismissKeyboard()
                        },
                        onVoicePressChanged: handleVoicePressChanged,
                        onPlusTap: {
                            withAnimation(AppTheme.Motion.standard) {
                                showingAttachmentTray.toggle()
                            }
                        }
                    )
                    if showingAttachmentTray {
                        ChatAttachmentTray {
                            showingAttachmentTray = false
                            showingPlusMenu = true
                        }
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                }
            }
            .navigationTitle("")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(.hidden, for: .navigationBar)
            .alert("清空当前对话？", isPresented: $isShowingClearAlert) {
                Button("取消", role: .cancel) {}
                Button("清空", role: .destructive) { coordinator.clearCurrentSession() }
            } message: {
                Text("此操作将清空当前会话所有消息记录。")
            }
            .alert("本地消息保存失败", isPresented: Binding(
                get: { coordinator.persistenceFailureMessage != nil },
                set: { if !$0 { coordinator.acknowledgePersistenceFailure() } }
            )) {
                if coordinator.persistenceFailureCanRetry {
                    Button("重试保存") { coordinator.retryPersistenceFailure() }
                }
                Button("知道了") { coordinator.acknowledgePersistenceFailure() }
            } message: {
                Text(coordinator.persistenceFailureMessage ?? "")
            }
            .confirmationDialog(
                "整理完成后如何处理来源会话？",
                isPresented: Binding(
                    get: { !coordinator.pendingOrganizationDisposition.isEmpty },
                    set: { if !$0 && !coordinator.pendingOrganizationDisposition.isEmpty { coordinator.applyOrganizationDisposition(nil) } }
                ),
                titleVisibility: .visible
            ) {
                Button("归档来源会话（新笔记仍在知识首页）") { coordinator.applyOrganizationDisposition(.archived) }
                Button("保留来源会话") { coordinator.applyOrganizationDisposition(nil) }
                Button("来源会话移入回收站", role: .destructive) { coordinator.applyOrganizationDisposition(.trashed) }
            } message: {
                Text("这里处理的是整理所依据的来源会话，不会归档刚创建的笔记。新笔记仍在知识首页；知识页“归档”仅显示被明确归档的笔记。")
            }
            .overlay(alignment: .bottom) { toastOverlay }
            .animation(.easeInOut(duration: 0.2), value: coordinator.toastMessage)
            .sheet(isPresented: $showingPlusMenu) {
                PlusMenuSheet(
                    onPhotoPicked: { data in coordinator.attachPhoto(data) },
                    onDocumentPicked: { url in coordinator.attachDocument(url) },
                    onWeChatImported: { link in coordinator.importWeChatLink(link) },
                    onKnowledgeReferenced: { item in coordinator.referenceKnowledge(item) }
                )
            }
            .sheet(item: $coordinator.pendingClientAction) { action in
                NativeClientActionHost(action: action) { status, metadata in
                    coordinator.completeClientAction(
                        action, status: status, metadata: metadata
                    )
                }
            }
            .fullScreenCover(isPresented: $showingTopicDiscussion, onDismiss: returnToTopicParent) {
                TargetedTopicDiscussionSheet(coordinator: coordinator)
            }
            .sheet(isPresented: $showingSessionDrawer) {
                SessionDrawerSheet(
                    sessionManager: coordinator.sessionManager,
                    onSelect: { id in
                        if let topic = sessionManager.topicSessions[id], topic.state != .queued {
                            coordinator.openTopic(topic)
                            showingTopicDiscussion = true
                        } else {
                            coordinator.switchSession(to: id)
                            coordinator.reconcileActiveRun()
                        }
                        showingSessionDrawer = false
                    },
                    onNew: {
                        coordinator.newSession()
                        showingSessionDrawer = false
                    },
                    onDelete: { id in coordinator.deleteSession(id) }
                )
            }
            .sheet(isPresented: $showingAgentPicker) {
                ChatAgentPickerSheet(
                    tenantAgents: tenantAgents,
                    selectedAgentId: appState.selectedAgentId,
                    onSelect: { id, name in
                        showingAgentPicker = false
                        appState.openChat(agentId: id, agentName: name)
                        coordinator.handlePendingAgent()
                    }
                )
            }
            .onAppear {
                coordinator.appState = appState
                coordinator.synchronizeLocalAccount()
                coordinator.restoreActiveSession()
                coordinator.refreshQuickCommands()
                coordinator.handlePendingAgent()
                coordinator.prewarmActiveSessionIfNeeded()
                coordinator.handlePendingPrompt()
                handlePendingTopic()
                coordinator.reconcileRestoredClarify()
                coordinator.reconcileActiveRun()
            }
            .task { await refreshAgents() }
            .onReceive(NotificationCenter.default.publisher(for: .tenantAgentsDidUpdate)) { _ in
                Task { await refreshAgents() }
            }
            .onChange(of: appState.pendingChatAgent?.id) { _, _ in
                coordinator.handlePendingAgent()
            }
            .onChange(of: appState.pendingChatPrompt) { _, _ in coordinator.handlePendingPrompt() }
            .onChange(of: appState.pendingTopicSessionId) { _, _ in handlePendingTopic() }
            .onChange(of: appState.currentTenantKey) { _, _ in
                coordinator.synchronizeLocalAccount()
                coordinator.reconcileRestoredClarify()
                coordinator.reconcileActiveRun()
            }
            .onChange(of: appState.currentUserId) { _, _ in
                coordinator.synchronizeLocalAccount()
                coordinator.reconcileRestoredClarify()
                coordinator.reconcileActiveRun()
            }
            .onChange(of: appState.activeTab) { _, tab in
                if tab == 0 {
                    coordinator.reconcileActiveRun()
                } else {
                    // Tab navigation detaches only the iOS transport. Hermes owns
                    // and continues the existing Run; the chat shows background state.
                    coordinator.prepareForBackground()
                }
            }
            .onChange(of: coordinator.inputText) { _, newValue in
                // Session restore, prompts, chips and voice input can update
                // the coordinator outside the TextField.
                if newValue != draftText {
                    draftText = newValue
                }
            }
            .onChange(of: speechService.state) { oldState, newState in
                guard newState == .idle, oldState != .idle else { return }
                let recognized = speechService.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !recognized.isEmpty else { return }
                draftText = joinedVoiceInput(prefix: voiceInputPrefix, transcript: recognized)
                coordinator.inputText = draftText
                isVoicePressing = false
            }
            .onReceive(waitingTimer) { _ in coordinator.tickWaitingTimer() }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active {
                    InboxFileManager.shared.cleanupStaleInboxFiles()
                    coordinator.reconcileRestoredClarify()
                    coordinator.reconcileActiveRun()
                } else if phase == .background {
                    coordinator.prepareForBackground()
                }
            }
            .onDisappear {
                // SwiftUI can remove this tab before the child's activeTab
                // onChange handler runs. Always detach the iOS transport here;
                // Hermes keeps owning and executing the same durable Run.
                coordinator.prepareForBackground()
                isVoicePressing = false
                if speechService.state != .idle {
                    speechService.cancel()
                }
            }
        }
    }

    private var currentTopic: TopicSessionMetadata? {
        let sessionId = sessionManager.activeSessionID()
        guard let topic = sessionManager.topicSessions[sessionId], topic.state != .ended else { return nil }
        return topic
    }

    private func dismissKeyboard() {
        dismissKeyboardToken &+= 1
    }

    @ViewBuilder
    private func topicControlBar(_ topic: TopicSessionMetadata) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "bubble.left.and.bubble.right.fill")
                .foregroundStyle(AppTheme.Icons.intelligence)
            Text(String(topic.sourceText.prefix(52)))
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .lineLimit(1)
            Spacer(minLength: 0)
            if topic.state == .ending {
                Label("等待确认入库", systemImage: "hourglass")
                    .font(AppTheme.Typography.micro.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            } else {
                Button("结束并整理入库") { coordinator.endCurrentTopic() }
                    .font(AppTheme.Typography.micro.weight(.semibold))
                    .buttonStyle(SoftButtonStyle())
            }
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(AppTheme.Colors.surfaceTint)
    }

    @MainActor
    private func handlePendingTopic() {
        guard let id = appState.pendingTopicSessionId,
              let topic = sessionManager.topicSessions[id] else { return }
        appState.pendingTopicSessionId = nil
        coordinator.openTopic(topic)
        showingTopicDiscussion = true
    }

    @MainActor
    private func returnToTopicParent() {
        let sessionId = sessionManager.activeSessionID()
        guard let topic = sessionManager.topicSessions[sessionId] else { return }
        coordinator.switchSession(to: topic.parentSessionId)
    }

    @MainActor
    private func handleVoicePressChanged(_ isPressing: Bool) {
        if isPressing {
            guard speechService.state == .idle else { return }
            voiceInputPrefix = draftText
            Task { @MainActor in
                await speechService.start(autoStopOnSilence: false)
                if !isVoicePressing, speechService.state == .recording {
                    speechService.stop()
                }
            }
        } else if speechService.state == .recording {
            speechService.stop()
        }
    }

    private func joinedVoiceInput(prefix: String, transcript: String) -> String {
        let trimmedPrefix = prefix.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedPrefix.isEmpty else { return transcript }
        return "\(trimmedPrefix) \(transcript)"
    }

    @MainActor
    private func refreshAgents() async {
        do {
            tenantAgents = try await APIClient.shared.fetchTenantAgents().filter(\.isActive)
            let baseline = ["main_agent", "supervision", "coder", "knowledge"]
            if !baseline.contains(appState.selectedAgentId),
               !tenantAgents.contains(where: { $0.id == appState.selectedAgentId }) {
                appState.openChat(agentId: "main_agent", agentName: "Main 智能编排")
                coordinator.handlePendingAgent()
                coordinator.showToast("原 Agent 已停用或不可访问，已切换到 Main Agent")
            }
        } catch {
            coordinator.showToast("Agent 列表加载失败，保留当前会话")
        }
    }

    @ViewBuilder
    private var toastOverlay: some View {
        if let toast = coordinator.toastMessage {
            Text(toast)
                .font(AppTheme.Typography.supporting.weight(.medium))
                .foregroundColor(AppTheme.Colors.onPrimary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, 8)
                .background(AppTheme.Colors.interactiveBlue)
                .clipShape(Capsule())
                .shadow(color: AppTheme.Colors.auroraBlue.opacity(0.22), radius: 12, y: 5)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .padding(.bottom, 90)
        }
    }
}

public struct ChatAttachmentTray: View {
    public var onSelect: () -> Void

    public init(onSelect: @escaping () -> Void) {
        self.onSelect = onSelect
    }

    private let items = [
        ("camera.fill", "拍照"),
        ("doc.fill", "上传"),
        ("link", "链接"),
        ("folder.fill", "文档"),
    ]

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            ForEach(items, id: \.1) { item in
                Button(action: onSelect) {
                    VStack(spacing: 6) {
                        Image(systemName: item.0)
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(AppTheme.Icons.secondary)
                        Text(item.1)
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                    }
                    .frame(maxWidth: .infinity, minHeight: 58)
                    .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                }
                .buttonStyle(SoftButtonStyle())
            }
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.bottom, AppTheme.Spacing.sm)
        .background(AppTheme.Colors.background.opacity(0.96))
    }
}

public struct ChatVoiceCaptureView: View {
    public let transcript: String
    public let elapsedSeconds: Int
    public let onCancel: () -> Void

    public init(transcript: String, elapsedSeconds: Int, onCancel: @escaping () -> Void) {
        self.transcript = transcript
        self.elapsedSeconds = elapsedSeconds
        self.onCancel = onCancel
    }

    public var body: some View {
        VStack(spacing: 0) {
            Spacer()
            HStack(alignment: .bottom, spacing: AppTheme.Spacing.sm) {
                Text(transcript.isEmpty ? "正在聆听…" : transcript)
                    .font(AppTheme.Typography.body)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "mic.fill")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.white)
                    .frame(width: 48, height: 48)
                    .background(AppTheme.Colors.actionGradient, in: Circle())
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.xl))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.xl)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.75)
            }
            .padding(.horizontal, AppTheme.Spacing.lg)

            TimelineView(.animation(minimumInterval: 0.12)) { context in
                HStack(alignment: .center, spacing: 3) {
                    ForEach(0..<29, id: \.self) { index in
                        let phase = context.date.timeIntervalSinceReferenceDate * 5 + Double(index) * 0.7
                        Capsule()
                            .fill(AppTheme.Colors.interactiveBlue)
                            .frame(width: 2.5, height: 7 + abs(sin(phase)) * 25)
                    }
                }
                .frame(height: 54)
            }
            .padding(.top, AppTheme.Spacing.xl)

            Text(String(format: "0:%02d", elapsedSeconds))
                .font(AppTheme.Typography.body.monospacedDigit())
                .foregroundStyle(AppTheme.Colors.textSecondary)
            Text("松开发送 · 上滑取消")
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textTertiary)
                .padding(.top, AppTheme.Spacing.md)

            Spacer()

            Button(action: onCancel) {
                Image(systemName: "xmark")
                    .font(.body.weight(.medium))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .frame(width: 48, height: 48)
                    .background(AppTheme.Colors.cardBackground, in: Circle())
            }
            .buttonStyle(SoftButtonStyle())
            .padding(.bottom, AppTheme.Spacing.xl)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppTheme.Colors.background.opacity(0.985))
    }
}

#if DEBUG
public struct V4ChatPrototypeHost: View {
    public let pageID: String
    @State private var draft = ""
    @State private var quote: QuotedContext?
    @State private var isVoicePressing = false
    @StateObject private var speechService = SpeechRecognizerService()

    public init(pageID: String) {
        self.pageID = pageID
    }

    public var body: some View {
        ZStack {
            QuantumMistBackground()
            VStack(spacing: 0) {
                ChatTopBarView(
                    isGenerating: false,
                    title: "新对话",
                    onTitleTap: {},
                    onNewSession: {},
                    onHistoryTap: {},
                    onClearTap: {}
                )

                if pageID.hasSuffix("p02") {
                    ChatVoiceCaptureView(
                        transcript: "推荐几本适合大学生读的心理学入门书",
                        elapsedSeconds: 4,
                        onCancel: {}
                    )
                } else if pageID.hasSuffix("p03") || pageID.hasSuffix("p04") {
                    ScrollView {
                        LazyVStack(spacing: AppTheme.Spacing.sm) {
                            MessageBubbleView(message: userMessage)
                            MessageBubbleView(
                                message: assistantMessage,
                                reasoningInitiallyExpanded: pageID.hasSuffix("p04"),
                                reasoningSummary: "正在查找路线与天气 · 3步"
                            )
                        }
                        .padding(.vertical, AppTheme.Spacing.md)
                    }
                    ChatInputBar(
                        inputText: $draft,
                        quotedContext: $quote,
                        isVoicePressing: $isVoicePressing,
                        speechService: speechService,
                        isGenerating: false,
                        dismissKeyboardToken: 0,
                        onSend: {},
                        onVoicePressChanged: { _ in },
                        onPlusTap: {}
                    )
                } else {
                    ChatWelcomeView()
                    ChatInputBar(
                        inputText: $draft,
                        quotedContext: $quote,
                        isVoicePressing: $isVoicePressing,
                        speechService: speechService,
                        isGenerating: false,
                        dismissKeyboardToken: 0,
                        onSend: {},
                        onVoicePressChanged: { _ in },
                        onPlusTap: {}
                    )
                    ChatAttachmentTray(onSelect: {})
                }
            }
        }
    }

    private var userMessage: ChatMessage {
        ChatMessage(role: .user, content: "推荐几本适合大学生读的心理学入门书")
    }

    private var assistantMessage: ChatMessage {
        ChatMessage(
            role: .assistant,
            content: "当然可以！以下是几本适合大学生阅读的心理学入门书，兼顾可读性与专业性，帮助你建立对心理学的整体认识。\n\n**1.《心理学与生活》**\n作者：Richard J. Gerrig 等\n内容全面、语言生动，适合零基础入门。\n\n**2.《蛤蟆先生去看心理医生》**\n作者：罗伯特·戴博德\n用小说的方式讲述心理咨询过程。",
            blocks: [.reasoning(reasoningSteps)],
            reasoningDuration: 12
        )
    }

    private var reasoningSteps: [ReasoningStep] {
        [
            ReasoningStep(type: .thought, title: "理解问题", detail: "分析意图，提取关键信息"),
            ReasoningStep(type: .toolCall, title: "检索资料", detail: "搜索书籍推荐，使用网页与图书"),
            ReasoningStep(type: .thought, title: "整理答案", detail: "筛选与总结，生成回答"),
        ]
    }
}

private struct ChatWelcomeView: View {
    var body: some View {
        VStack(spacing: AppTheme.Spacing.xl) {
            Spacer()
            ZStack {
                Image(systemName: "book.closed.fill")
                    .font(.system(size: 76, weight: .light))
                    .foregroundStyle(AppTheme.Colors.textTertiary.opacity(0.32))
                    .offset(y: 38)
                Image(systemName: "leaf.fill")
                    .font(.system(size: 68, weight: .light))
                    .foregroundStyle(Color(hex: "88A98A").opacity(0.72))
                    .offset(x: -30, y: -18)
                Text("有好问题\n就有新发现")
                    .font(.system(size: 24, weight: .regular, design: .serif))
                    .italic()
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .rotationEffect(.degrees(-7))
                    .offset(x: 64, y: -8)
            }
            .frame(height: 190)

            Text("向我提问，阅读、整理、创作，\n让知识成为你的底气。")
                .font(AppTheme.Typography.body)
                .foregroundStyle(AppTheme.Colors.textTertiary)
                .multilineTextAlignment(.center)
                .lineSpacing(6)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct V3ChatPrototypeHost: View {
    let pageID: String
    @State private var noteText = ""
    @FocusState private var noteFocused: Bool

    var body: some View {
        if pageID.hasPrefix("v3/02-chat-core-") { chatCore }
        else if pageID.hasPrefix("v3/03-compose-import-voice-") { compose }
        else if pageID.hasPrefix("v3/04-clarify-status-cards-") { clarify }
        else { richContent }
    }

    @ViewBuilder private var chatCore: some View {
        switch page {
        case 1:
            ZStack { QuantumMistBackground(); VStack(spacing: 0) { header("Quantum"); VStack(alignment: .leading, spacing: 8) { Text("你好").font(.system(size: 36, weight: .semibold, design: .serif)); Text("有什么想探索的吗？").font(AppTheme.Typography.body); Spacer(); ForEach([("帮我理解一个概念", "用简单的例子说明", "leaf.fill"), ("帮我整理这篇文章", "提炼重点", "doc.text.fill"), ("给我一些学习建议", "提升专注力的方法", "lightbulb.fill")], id: \.0) { item in suggestion(item.0, item.1, item.2) } }.padding(); composerBar("随时提问…") } }
        case 2:
            ZStack { QuantumMistBackground(); VStack(spacing: 0) { header("学习方法"); ScrollView { VStack(spacing: 14) { bubble("如何在大学里保持长期的学习动力？", user: true); bubble("这是一个很棒的问题。保持学习动力需要内在的目标感、合适的方法和可持续的节奏。\n\n1. 找到真正感兴趣的方向\n2. 设定可以达成的小目标\n3. 建立正向反馈", user: false); Label("正在生成回答…", systemImage: "circle.fill").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Icons.interactive) }.padding() }; composerBar("继续提问…") } }
        case 3:
            NavigationStack { ZStack { QuantumMistBackground(); VStack(spacing: 12) { bubble("我可以帮你比较这两种方法，并结合你的情况给出建议。", user: false); HStack { Text("待发送（2）").font(AppTheme.Typography.cardTitle); Spacer(); Button("清空") {} }.padding(.horizontal); queued("也帮我列一个一周的学习计划"); queued("顺便推荐几本相关的书"); Spacer(); composerBar("输入消息…") } }.navigationTitle("对话").navigationBarTitleDisplayMode(.inline) }
        default:
            NavigationStack { ZStack { QuantumMistBackground(); ScrollView { VStack(spacing: 10) { TextField("搜索对话", text: .constant("")).textFieldStyle(.roundedBorder); Picker("", selection: .constant(0)) { Text("最近").tag(0); Text("已归档").tag(1); Text("回收站").tag(2) }.pickerStyle(.segmented); ForEach([("学习方法", "如何在大学里保持长期的学习动力…", "10:24"), ("论文写作", "文献综述的结构建议", "昨天"), ("时间管理", "番茄工作法的实践", "9月10日"), ("专业选择", "如何判断自己适合的方向", "9月8日")], id: \.0) { item in HStack { RoundedRectangle(cornerRadius: 8).fill(AppTheme.Colors.mistSky).frame(width: 54, height: 54).overlay { Image(systemName: "text.bubble.fill").foregroundStyle(AppTheme.Icons.interactive) }; VStack(alignment: .leading) { Text(item.0).font(AppTheme.Typography.label); Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary).lineLimit(1) }; Spacer(); Text(item.2).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary); Image(systemName: "ellipsis") }.padding().quantumCard() }; Label("永久删除此对话？", systemImage: "trash.fill").font(AppTheme.Typography.cardTitle).foregroundStyle(AppTheme.Colors.statusError).padding().frame(maxWidth: .infinity).background(AppTheme.Colors.dangerSurface, in: RoundedRectangle(cornerRadius: 14)); HStack { Button("取消") {}; Spacer(); Button("永久删除", role: .destructive) {} } }.padding() }.navigationTitle("对话管理").navigationBarTitleDisplayMode(.inline) } }
        }
    }

    @ViewBuilder private var compose: some View {
        switch page {
        case 1:
            NavigationStack { ZStack { QuantumMistBackground(); VStack(alignment: .leading, spacing: 14) { Text("记录此刻的想法\n让灵感长出枝叶").font(.system(size: 30, weight: .semibold, design: .serif)); HStack { tag("# 学习", AppTheme.Colors.mistSky); tag("# 读书", AppTheme.Colors.mistMint); tag("# 灵感", AppTheme.Colors.mistLilac); Image(systemName: "plus.circle") }; TextEditor(text: $noteText).focused($noteFocused).frame(minHeight: 230).padding(8).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 14)); HStack { ForEach(["photo", "paperclip", "mic", "link"], id: \.self) { Image(systemName: $0).frame(width: 44, height: 44) }; Spacer(); Button("发送", systemImage: "paperplane.fill") {}.labelStyle(.iconOnly).buttonStyle(.borderedProminent) }; Spacer() }.padding() }.navigationTitle("新建笔记").navigationBarTitleDisplayMode(.inline).task { noteText = "写下你的想法…"; noteFocused = true } }
        case 2:
            ZStack { QuantumMistBackground(); VStack(spacing: 14) { Capsule().fill(AppTheme.Colors.border).frame(width: 42, height: 5); Text("添加与导入").font(AppTheme.Typography.sectionTitle).frame(maxWidth: .infinity, alignment: .leading); ForEach([("照片图库", "选择相册中的图片", "photo.on.rectangle"), ("拍摄照片", "即时拍照并添加", "camera"), ("文件", "导入 PDF、文档等", "doc"), ("从微信导入", "导入聊天中的文章或文件", "bubble.left.and.bubble.right.fill"), ("粘贴链接", "导入网页内容", "link")], id: \.0) { item in HStack { Image(systemName: item.2).foregroundStyle(AppTheme.Icons.interactive).frame(width: 48, height: 48).background(AppTheme.Colors.selectionTint, in: RoundedRectangle(cornerRadius: 12)); VStack(alignment: .leading) { Text(item.0).font(AppTheme.Typography.label); Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "chevron.right") }.padding().quantumCard() }; Button("取消") {}.buttonStyle(.bordered).frame(maxWidth: .infinity); Spacer() }.padding() }
        case 3:
            NavigationStack { ZStack { QuantumMistBackground(); ScrollView { VStack(spacing: 16) { HStack { Text("https://sspai.com/post/82836").font(AppTheme.Typography.micro); Spacer(); Button("导入") {}.buttonStyle(.borderedProminent) }.padding().quantumCard(); VStack(alignment: .leading, spacing: 8) { RoundedRectangle(cornerRadius: 12).fill(AppTheme.Colors.mistSky).frame(height: 150).overlay { Image(systemName: "building.2.crop.circle.fill").font(.system(size: 72)).foregroundStyle(AppTheme.Colors.quantumBlue.opacity(0.55)) }; Text("好的学习方法，能让你走得更远").font(AppTheme.Typography.cardTitle); Text("如何在信息过载的时代，建立属于自己的知识体系。本文分享了实用的方法…").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary) }.padding().quantumCard(); status("链接有效", "已解析到 1 篇文章", .success); status("内容已存在", "你已在 2024年9月12日 保存过相似内容", .warning); status("无法解析该链接", "请检查链接是否正确，或尝试在浏览器中打开", .error) }.padding() } }.navigationTitle("导入链接").navigationBarTitleDisplayMode(.inline) }
        default:
            NavigationStack { ZStack { QuantumMistBackground(); VStack(spacing: 26) { Spacer(); HStack(alignment: .center, spacing: 6) { ForEach(0..<20, id: \.self) { i in Capsule().fill(AppTheme.Colors.quantumGradient).frame(width: 5, height: CGFloat(20 + (i * 17) % 74)) } }.frame(height: 120); Label("00:24", systemImage: "record.circle.fill").font(.title2).foregroundStyle(AppTheme.Colors.statusError); Text("正在录音…").foregroundStyle(AppTheme.Colors.textSecondary); Text("好的学习，不只是记住知识，\n更是学会思考和连接。").font(AppTheme.Typography.body).padding().quantumCard(); HStack(spacing: 34) { voiceAction("暂停", "pause.fill"); voiceAction("完成", "stop.fill", destructive: true); voiceAction("取消", "trash") }; Label("需要麦克风权限，用于语音输入和实时转写", systemImage: "mic.fill").font(AppTheme.Typography.micro).padding().background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: 12)); Spacer() }.padding() }.navigationTitle("语音输入").navigationBarTitleDisplayMode(.inline) }
        }
    }

    @ViewBuilder private var clarify: some View {
        if page <= 2 {
            V4ClarifyMergePrototypeHost(pageID: "v4/03-clarify-merge-preview-v4-p0\(page)")
        } else if page == 3 {
            NavigationStack { ZStack { QuantumMistBackground(); VStack(spacing: 20) { HStack { QuantumAvatarView(size: 38); VStack(alignment: .leading) { Text("Quantum 正在为你整理…").font(AppTheme.Typography.cardTitle); Text("大约需要 1–2 分钟").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer() }.padding().quantumCard(); ForEach(Array([("理解需求", "分析你的问题和关注点"), ("检索资料", "来自学术库与优质来源"), ("整理与生成", "提炼要点，组织内容"), ("检查与优化", "确保准确性与可读性")].enumerated()), id: \.offset) { index, item in HStack { Image(systemName: index == 0 ? "checkmark.circle.fill" : (index == 1 ? "circle.inset.filled" : "circle")).foregroundStyle(index < 2 ? AppTheme.Icons.interactive : AppTheme.Icons.tertiary); VStack(alignment: .leading) { Text(item.0).font(AppTheme.Typography.label); Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); if index < 2 { Text(index == 0 ? "00:08" : "00:24").font(AppTheme.Typography.micro) } }.padding() }; VStack(alignment: .leading, spacing: 10) { Label("正在检索相关资料…", systemImage: "waveform").foregroundStyle(AppTheme.Icons.interactive); Text("• 正在搜索：气候变化 大学生 行动建议\n• 已找到 12 篇相关文献\n• 正在筛选高质量内容…").font(AppTheme.Typography.micro).lineSpacing(8) }.padding().quantumCard(); Spacer() }.padding() }.navigationTitle("正在整理").navigationBarTitleDisplayMode(.inline) }
        } else {
            NavigationStack { ZStack { QuantumMistBackground(); VStack(alignment: .leading, spacing: 16) { status("已保存到书架", "知识已为你整理完成。", .success); HStack { RoundedRectangle(cornerRadius: 10).fill(AppTheme.Colors.mistSky).frame(width: 100, height: 132).overlay { Image(systemName: "mountain.2.fill").font(.largeTitle).foregroundStyle(AppTheme.Colors.quantumBlue) }; VStack(alignment: .leading) { Text("气候变化\n与我们的未来").font(AppTheme.Typography.sectionTitle); Text("12 条笔记 · 今天").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary); HStack { tag("气候变化", AppTheme.Colors.mistMint); tag("大学生", AppTheme.Colors.mistLilac) } } }.padding().quantumCard(); HStack { actionTile("保存", "bookmark.fill"); actionTile("合并", "point.3.connected.trianglepath.dotted"); actionTile("丢弃", "trash") }; status("发现相似内容", "书架中已有相似笔记《气候变化概述》", .warning); status("操作已完成", "可在书架中查看", .success); status("同步失败", "网络连接不稳定，请重试。", .error); Spacer() }.padding() }.navigationTitle("整理完成").navigationBarTitleDisplayMode(.inline) }
        }
    }

    @ViewBuilder private var richContent: some View {
        switch page {
        case 1:
            NavigationStack {
                ZStack {
                    QuantumMistBackground()
                    ScrollView {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                            bubble("请解释可再生能源的现状，并给出数据趋势。", user: true)
                            ReadingCardDeck(blocks: [
                                .heading(level: 1, text: "可再生能源：现状与对比"),
                                .paragraph("可再生能源正在加速发展，太阳能与风能成为新增装机的主要来源。"),
                                .quote("理解能源结构变化，关键不是只看总量，还要比较增长速度与稳定性。"),
                                .bulletList(["太阳能：增长快、部署灵活", "风能：规模化成熟", "水能：稳定但地域约束明显"]),
                                .heading(level: 2, text: "趋势观察"),
                                .paragraph("过去四年，清洁能源占比保持上升，结构正在从单一来源转向多能互补。")
                            ])
                            ChartCard(block: ChartBlock(
                                title: "清洁能源占比",
                                chartType: .line,
                                series: [
                                    ChartSeries(name: "太阳能", points: [
                                        .init(label: "2022", value: 18), .init(label: "2023", value: 25), .init(label: "2024", value: 34), .init(label: "2025", value: 46)
                                    ]),
                                    ChartSeries(name: "风能", points: [
                                        .init(label: "2022", value: 22), .init(label: "2023", value: 28), .init(label: "2024", value: 36), .init(label: "2025", value: 41)
                                    ])
                                ],
                                summary: "太阳能增速更快，风能保持稳定扩张。"
                            ))
                        }
                        .padding()
                    }
                }
                .navigationTitle("阅读与图表卡")
                .navigationBarTitleDisplayMode(.inline)
            }
        case 2:
            NavigationStack {
                ZStack {
                    QuantumMistBackground()
                    ScrollView {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                            Text("太阳能电池原理")
                                .font(.system(size: 28, weight: .semibold, design: .serif))
                            Text("输出功率由转换效率、电池面积和太阳辐照度共同决定。")
                                .font(AppTheme.Typography.body)
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                            FormulaCard(formula: "P = η · A · G")
                            CodeBlockCard(snippet: CodeSnippet(
                                language: "python",
                                code: "import numpy as np\n\narea = np.array([10, 50, 100])\nefficiency = 0.2\nannual_energy = efficiency * area * irradiance"
                            ))
                            HighlightCard(text: "η 表示光电转换效率，A 表示电池面积，G 表示太阳辐照度。")
                        }
                        .padding()
                    }
                }
                .navigationTitle("公式、代码与高亮")
                .navigationBarTitleDisplayMode(.inline)
            }
        case 3:
            NavigationStack { ZStack { QuantumMistBackground(); ScrollView { VStack(alignment: .leading, spacing: 14) { RoundedRectangle(cornerRadius: 14).fill(LinearGradient(colors: [AppTheme.Colors.mistSky, AppTheme.Colors.mistMint], startPoint: .top, endPoint: .bottom)).frame(height: 330).overlay { VStack(spacing: 18) { Image(systemName: "doc.richtext.fill").font(.system(size: 64)).foregroundStyle(AppTheme.Colors.statusError); Text("Global Renewable\nEnergy Outlook 2023\nExecutive Summary").font(.title2.bold()).multilineTextAlignment(.center); Image(systemName: "mountain.2.fill").font(.system(size: 68)).foregroundStyle(AppTheme.Colors.quantumBlue) } }; Text("Global Renewable Energy Outlook 2023").font(AppTheme.Typography.sectionTitle); Text("International Energy Agency (IEA)").foregroundStyle(AppTheme.Colors.textSecondary); ForEach([("发布日期", "2023 年 10 月"), ("文件类型", "PDF · 12.3 MB"), ("来源链接", "https://www.iea.org/reports/…")], id: \.0) { item in HStack { Text(item.0).foregroundStyle(AppTheme.Colors.textSecondary); Spacer(); Text(item.1) }.font(AppTheme.Typography.supporting).padding(.vertical, 6); Divider() }; HStack { Button("下载", systemImage: "arrow.down.to.line") {}.buttonStyle(.bordered); Button("在新窗口打开", systemImage: "arrow.up.forward.app") {}.buttonStyle(.borderedProminent) } }.padding() } }.navigationTitle("来源详情").navigationBarTitleDisplayMode(.inline) }
        default:
            NavigationStack { ZStack { QuantumMistBackground(); ScrollView { VStack(alignment: .leading, spacing: 18) { HStack { QuantumAvatarView(size: 44); VStack(alignment: .leading) { Text("可再生能源：现状与对比").font(AppTheme.Typography.cardTitle); Text("今天 09:41").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) } }.padding().quantumCard(); HStack(spacing: 18) { ForEach([("复制", "doc.on.doc"), ("重新生成", "arrow.clockwise"), ("朗读", "speaker.wave.2"), ("有帮助", "hand.thumbsup"), ("没帮助", "hand.thumbsdown")], id: \.0) { item in VStack { Image(systemName: item.1).frame(width: 46, height: 46).background(AppTheme.Colors.surfaceTint, in: Circle()); Text(item.0).font(AppTheme.Typography.micro) } } }; HStack { Label("分享", systemImage: "square.and.arrow.up"); Spacer(); Label("开启新话题", systemImage: "plus") }.padding(.vertical); Divider(); Text("导出到笔记").font(AppTheme.Typography.cardTitle); status("导出失败", "网络连接不稳定，请检查网络后重试。", .error); HStack { Button("重试") {}; Spacer(); Button("切换为本地导出") {}.buttonStyle(.borderedProminent) }; Text("相关提问").font(AppTheme.Typography.cardTitle); ForEach(["中国的可再生能源发展现状如何？", "可再生能源的主要挑战有哪些？", "未来十年的关键技术趋势是什么？"], id: \.self) { Label($0, systemImage: "chevron.right").labelStyle(TrailingIconLabelStyle()).padding().quantumCard() } }.padding() } }.navigationTitle("回答详情").navigationBarTitleDisplayMode(.inline) }
        }
    }

    private var page: Int { Int(pageID.suffix(2)) ?? 1 }
    private func header(_ title: String) -> some View { HStack { Button("返回", systemImage: "chevron.left") {}.labelStyle(.iconOnly); Spacer(); Text(title).font(AppTheme.Typography.cardTitle); Spacer(); Button("更多", systemImage: "ellipsis") {}.labelStyle(.iconOnly) }.padding() }
    private func suggestion(_ title: String, _ subtitle: String, _ icon: String) -> some View { HStack { Image(systemName: icon).foregroundStyle(AppTheme.Icons.interactive).frame(width: 42, height: 42).background(AppTheme.Colors.selectionTint, in: Circle()); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.label); Text(subtitle).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "chevron.right") }.padding().quantumCard() }
    private func bubble(_ text: String, user: Bool) -> some View { HStack { if user { Spacer(minLength: 72) } else { QuantumAvatarView(size: 28) }; Text(text).font(AppTheme.Typography.supporting).padding(13).background(user ? AppTheme.Colors.selectionTint : AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 16)); if !user { Spacer(minLength: 42) } }.frame(maxWidth: .infinity) }
    private func composerBar(_ prompt: String) -> some View { HStack { Image(systemName: "plus"); Text(prompt).foregroundStyle(AppTheme.Colors.textTertiary); Spacer(); Image(systemName: "mic.fill") }.padding().background(.ultraThinMaterial, in: Capsule()).padding() }
    private func queued(_ text: String) -> some View { VStack(spacing: 10) { Text(text).frame(maxWidth: .infinity, alignment: .leading); HStack { Button("现在发送") {}.buttonStyle(.borderedProminent); Spacer(); Button("删除", systemImage: "trash") {} } }.padding().quantumCard().padding(.horizontal) }
    private func tag(_ text: String, _ color: Color) -> some View { Text(text).font(AppTheme.Typography.micro).padding(.horizontal, 10).padding(.vertical, 7).background(color, in: Capsule()) }
    private enum StatusKind { case success, warning, error }
    private func status(_ title: String, _ detail: String, _ kind: StatusKind) -> some View { let color = kind == .success ? AppTheme.Colors.statusCompleted : (kind == .warning ? AppTheme.Colors.statusWarning : AppTheme.Colors.statusError); return HStack(alignment: .top) { Image(systemName: kind == .success ? "checkmark.circle.fill" : "exclamationmark.circle.fill").foregroundStyle(color); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer() }.padding().frame(maxWidth: .infinity, alignment: .leading).background(color.opacity(0.09), in: RoundedRectangle(cornerRadius: 14)) }
    private func voiceAction(_ title: String, _ icon: String, destructive: Bool = false) -> some View { VStack { Image(systemName: icon).font(.title2).frame(width: 66, height: 66).foregroundStyle(destructive ? .white : AppTheme.Colors.textPrimary).background(destructive ? AppTheme.Colors.statusError : AppTheme.Colors.cardBackground, in: Circle()); Text(title).font(AppTheme.Typography.micro) } }
    private func actionTile(_ title: String, _ icon: String) -> some View { VStack { Image(systemName: icon).font(.title3); Text(title).font(AppTheme.Typography.micro) }.frame(maxWidth: .infinity, minHeight: 72).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 12)).overlay { RoundedRectangle(cornerRadius: 12).stroke(AppTheme.Colors.border) } }
}

private struct TrailingIconLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View { HStack { configuration.title; Spacer(); configuration.icon } }
}
#endif

private struct TargetedTopicDiscussionSheet: View {
    @ObservedObject var coordinator: TenantSessionCoordinator
    @Environment(\.dismiss) private var dismiss
    @StateObject private var speechService = SpeechRecognizerService()
    @State private var draft = ""
    @State private var isVoicePressing = false
    @State private var dismissKeyboardToken = 0

    private var topic: TopicSessionMetadata? {
        coordinator.sessionManager.topicSessions[coordinator.sessionManager.activeSessionID()]
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if let topic {
                    HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                        Image(systemName: "quote.opening")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                            .frame(width: 28, height: 28)
                            .background(AppTheme.Colors.surfaceTint)
                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                        VStack(alignment: .leading, spacing: 3) {
                            Text("源自原对话")
                                .font(AppTheme.Typography.micro.weight(.semibold))
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                            Text(String(topic.sourceText.prefix(120)))
                                .font(AppTheme.Typography.supporting)
                                .foregroundStyle(AppTheme.Colors.textPrimary)
                                .lineLimit(3)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.vertical, AppTheme.Spacing.sm)
                    .background(AppTheme.Colors.surfaceTint.opacity(0.72))
                }

                ChatMessageStreamView(coordinator: coordinator) {
                    dismissKeyboardToken &+= 1
                }

                ChatInputBar(
                    inputText: $draft,
                    quotedContext: $coordinator.quotedContext,
                    isVoicePressing: $isVoicePressing,
                    speechService: speechService,
                    isGenerating: coordinator.isGenerating,
                    dismissKeyboardToken: dismissKeyboardToken,
                    onSend: {
                        guard let text = ChatDraftSubmission.consume(&draft) else { return }
                        coordinator.sendMessage(text: text)
                        dismissKeyboardToken &+= 1
                    },
                    onVoicePressChanged: { _ in },
                    onPlusTap: {}
                )
            }
            .background(AppTheme.Colors.background)
            .navigationTitle("针对性话题")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("返回") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("整理入库") { coordinator.endCurrentTopic() }
                        .font(.subheadline.weight(.semibold))
                }
            }
        }
    }
}

private struct ChatAgentPickerSheet: View {
    let tenantAgents: [TenantAgentDTO]
    let selectedAgentId: String
    let onSelect: (String, String) -> Void
    @Environment(\.dismiss) private var dismiss

    private let baseline: [(String, String)] = [
        ("main_agent", "Main 智能编排"),
        ("supervision", "Supervision 架构审查"),
        ("coder", "Coder 独立开发"),
        ("knowledge", "知识星海"),
    ]

    var body: some View {
        NavigationStack {
            List {
                Section("平台 Agent") {
                    ForEach(baseline, id: \.0) { item in
                        agentRow(id: item.0, name: item.1, detail: "平台基线 Agent")
                    }
                }
                if !tenantAgents.isEmpty {
                    Section("我的专属 Agent") {
                        ForEach(tenantAgents) { agent in
                            agentRow(
                                id: agent.id,
                                name: agent.customName ?? "专属 Agent",
                                detail: agent.visibility == "private" ? "仅自己可见" : "租户可见"
                            )
                        }
                    }
                }
            }
            .navigationTitle("选择 Agent")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
            }
        }
    }

    private func agentRow(id: String, name: String, detail: String) -> some View {
        Button {
            onSelect(id, name)
        } label: {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: id == "main_agent" ? "sparkles" : "person.crop.circle.badge.checkmark")
                    .foregroundColor(AppTheme.Colors.quantumBlue)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).foregroundColor(AppTheme.Colors.textPrimary)
                    Text(detail)
                        .font(AppTheme.Typography.micro)
                        .foregroundColor(AppTheme.Colors.textSecondary)
                }
                Spacer()
                if id == selectedAgentId {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(AppTheme.Colors.quantumBlue)
                }
            }
        }
    }
}
