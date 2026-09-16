//
//  AIPlatformApp.swift
//  AIPlatformApp
//
//  Application Main Lifecycle Entry Point & AppRoot Navigation Coordinator
//  Swift 6 / iOS 17+ Standard App Entry
//

import SwiftUI

@main
public struct AIPlatformApp: App {
    @StateObject private var appState: AppState
    @StateObject private var apiClient = APIClient.shared
    @StateObject private var workflowActivities = WorkflowActivityCoordinator.shared
    // Start metadata recovery and legacy JSON migration independently of authentication/chat navigation.
    @StateObject private var sessionManager = SessionManager.shared
    #if DEBUG
    private let showBookshelfPreview: Bool
    private let showKnowledgeHomePreview: Bool
    private let showTabBarPreview: Bool
    private let showBatch4Preview: Bool
    private let showStructuredReviewE2E: Bool
    #endif

    public init() {
        let arguments = ProcessInfo.processInfo.arguments
        let environment = ProcessInfo.processInfo.environment
        #if DEBUG
        if environment["AI_LAB_E2E_DISABLE_ANIMATIONS"] == "1" {
            UIView.setAnimationsEnabled(false)
        }
        #endif
        let hasPersistedSession = !(KeychainStore.load() ?? "").isEmpty
#if DEBUG
        let hasE2EToken = !(environment["AI_LAB_E2E_TOKEN"] ?? "").isEmpty
        showBookshelfPreview = arguments.contains("-bookshelfPreview")
        showKnowledgeHomePreview = arguments.contains("-knowledgeHomePreview")
        showTabBarPreview = arguments.contains("-tabBarPreview")
        showBatch4Preview = arguments.contains("-batch4Preview")
        showStructuredReviewE2E = arguments.contains("-structuredReviewE2E")
#else
        let hasE2EToken = false
#endif
        let initialState = AppState(
            isLoggedIn: arguments.contains("-autoLogin") || hasPersistedSession || hasE2EToken,
            activeTab: arguments.contains("-knowledgeTab") ? 2 : 0
        )
#if DEBUG
        initialState.pendingChatPrompt = ProcessInfo.processInfo.environment["AI_LAB_E2E_PROMPT"]
#endif
        _appState = StateObject(wrappedValue: initialState)
    }

    public var body: some Scene {
        WindowGroup {
            Group {
                #if DEBUG
                if showStructuredReviewE2E {
                    StructuredReviewE2EHost()
                } else if showBatch4Preview {
                    Batch4PreviewHost()
                } else if showBookshelfPreview {
                    BookshelfPreviewHost()
                } else if showKnowledgeHomePreview {
                    KnowledgeView()
                } else if showTabBarPreview {
                    MainTabView()
                } else {
                    AppRootCoordinatorView()
                }
                #else
                AppRootCoordinatorView()
                #endif
            }
                .preferredColorScheme(.light)
                .environmentObject(appState)
                .environmentObject(apiClient)
                .environmentObject(workflowActivities)
                .environmentObject(sessionManager)
                .preferredColorScheme(.light)
        }
    }
}

#if DEBUG
private struct BookshelfPreviewHost: View {
    @State private var showingBookshelf = true
    private let center = ProcessInfo.processInfo.arguments.contains("-bookshelfSourcePreview")
        ? SubscriptionCenterResponse.sourcePreview
        : .bookshelfPreview

    var body: some View {
        if showingBookshelf {
            NavigationStack {
                SubscriptionCenterView(
                    previewCenter: center,
                    onBack: { showingBookshelf = false }
                )
            }
        } else {
            KnowledgeView()
        }
    }
}

private struct Batch4PreviewHost: View {
    @State private var descriptionExpanded = false
    @State private var advancedExpanded = false
    @State private var feedback = ""

    private let description = AgentDescriptionPresentation(
        function: "检索、整理、入库并追溯授权知识",
        suitable: "笔记查询、资料归纳与可追溯知识任务",
        boundary: "仅访问当前账号范围；未核实内容会标注"
    )

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    Label("界面验收样例，不会发起任务", systemImage: "hammer")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                    AgentDescriptionText(
                        text: description.full,
                        name: "知识助手",
                        isExpanded: $descriptionExpanded
                    )
                    .padding(AppTheme.Spacing.md)
                    .quantumCard()
                    WorkflowFailureCard(failure: .init(
                        cause: "网络连接中断，已完成步骤和输入均已保留。",
                        action: "从失败步骤继续同一任务"
                    ))
                    Button("从失败处重试", systemImage: "arrow.clockwise") {
                        feedback = "已请求重试同一任务"
                    }
                    .buttonStyle(.borderedProminent)
                    .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                    .accessibilityIdentifier("workflow-retry-action")
                    Button {
                        advancedExpanded.toggle()
                    } label: {
                        HStack {
                            Text("高级选项")
                            Spacer()
                            Image(systemName: advancedExpanded ? "chevron.up" : "chevron.down")
                        }
                        .contentShape(Rectangle())
                    }
                    .accessibilityIdentifier("workflow-advanced-options")
                    .accessibilityValue(advancedExpanded ? "已展开" : "已折叠")
                    if advancedExpanded {
                        Text("仅在需要调整执行细节时打开")
                            .accessibilityIdentifier("batch4-advanced-content")
                    }
                    ClarifyCard(
                        block: ClarifyBlock(
                            question: "当前一步：补充演示用途",
                            choices: [],
                            multiSelect: false,
                            submitLabel: "确认并继续"
                        ),
                        onSubmit: { _ in feedback = "已确认并进入下一步" }
                    )
                    if !feedback.isEmpty {
                        Text(feedback).accessibilityIdentifier("batch4-feedback")
                    }
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("小白体验验收")
        }
    }
}

private struct StructuredReviewE2EHost: View {
    private let workflowID = ProcessInfo.processInfo.environment["AI_LAB_E2E_WORKFLOW_ID"] ?? ""
    private let reviewKey = ProcessInfo.processInfo.environment["AI_LAB_E2E_REVIEW_KEY"] ?? "final-draft"

    var body: some View {
        NavigationStack {
            StructuredReviewView(
                workflowId: workflowID,
                reviewKey: reviewKey,
                initialDocument: .init(
                    title: "可编辑全稿预览",
                    fields: [
                        .init(id: "title", label: "标题", type: .text, required: true, options: nil),
                        .init(id: "summary", label: "摘要", type: .textarea, required: true, options: nil),
                    ],
                    values: ["title": .string("伊斯坦布尔"), "summary": .string("初稿")]
                )
            )
            .navigationTitle("全稿预览")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
#endif

// MARK: - App Root Coordinator
public struct AppRootCoordinatorView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var apiClient: APIClient
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator
    @Environment(\.scenePhase) private var scenePhase
    @State private var agreement: AgreementDTO?
    @State private var agreementError: String?
    @State private var isAgreementLoading = false
    @State private var showingAgreement = false
    @State private var isAgreementAccepting = false
    @State private var agreementAcceptanceKey = UUID().uuidString

    public var body: some View {
        Group {
            if appState.isLoggedIn {
                MainTabView()
                    .transition(.opacity.combined(with: .scale(scale: 0.98)))
            } else {
                LoginView()
                    .transition(.opacity)
            }
        }
        // 统一覆盖未声明局部样式的 Button / NavigationLink / Toolbar 入口。
        .buttonStyle(SoftButtonStyle())
        .animation(.easeInOut(duration: 0.3), value: appState.isLoggedIn)
        .overlay {
            if showingAgreement {
                AppTheme.Colors.scrim
                    .ignoresSafeArea()
                    .contentShape(Rectangle())
                    .onTapGesture {}
                    .accessibilityHidden(true)
            }
        }
        .onChange(of: apiClient.needsReauth) { _, needs in
            if needs {
                apiClient.needsReauth = false
                if !appState.isGuestMode {
                    // 真实登录态的 401 才代表凭证失效。游客访问受保护能力时应由
                    // 当前页面展示受限/演示状态，不能把游客模式误踢回登录页。
                    apiClient.clearToken()
                    appState.logout()
                }
            }
        }
        .onChange(of: apiClient.requiredAgreementVersion) { _, version in
            guard version != nil else { return }
            agreement = nil
            agreementAcceptanceKey = UUID().uuidString
            showingAgreement = true
            Task { await loadRequiredAgreement() }
        }
        .sheet(isPresented: $showingAgreement, onDismiss: {
            if apiClient.requiredAgreementVersion != nil {
                apiClient.resolveAgreementRequirement(accepted: false)
            }
        }) {
            AgreementSheet(
                agreement: agreement,
                isLoading: isAgreementLoading,
                isAccepting: isAgreementAccepting,
                errorMessage: agreementError,
                onRetry: { Task { await loadRequiredAgreement() } },
                onAccept: { Task { await acceptRequiredAgreement() } }
            )
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
            .presentationBackground(AppTheme.Colors.cardBackground)
            .presentationBackgroundInteraction(.disabled)
        }
        .task(id: appState.isLoggedIn) {
            if appState.isLoggedIn {
                await restorePersistedSession()
                if appState.isLoggedIn,
                   !appState.currentTenantKey.isEmpty,
                   !appState.currentUserId.isEmpty {
                    workflowActivities.activate(
                        tenantKey: appState.currentTenantKey,
                        userId: appState.currentUserId
                    )
                    await workflowActivities.bootstrap()
                }
            } else {
                workflowActivities.deactivate()
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active {
                Task { await workflowActivities.resumeFromForeground() }
            } else if phase == .background {
                workflowActivities.pauseForBackground()
            }
        }
    }

    /// Keychain 是进程重启后的登录态真值；`/me` 继续沿用现有 Bearer JWT
    /// 契约恢复租户资料。瞬时网络失败不清除本地会话，401 则由统一重登链路处理。
    @MainActor
    private func restorePersistedSession() async {
        guard let token = apiClient.currentToken(), !token.isEmpty else { return }
        do {
            let profile = try await apiClient.fetchMe()
            let displayName = profile.username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? CuteDisplayNames.name(for: profile.userId)
                : profile.username
            appState.currentTenantKey = profile.tenantKey
            appState.currentUserId = profile.userId
            appState.currentProfile = TenantProfile(
                id: profile.userId,
                name: displayName,
                tenantId: profile.tenantKey,
                role: .tenantMember,
                avatarUrl: profile.avatarUrl,
                concurrencyLimit: 5,
                tokenQuotaUsage: 0,
                isVipLane: false
            )
            appState.isGuestMode = false
            KnowledgeNoteStore.shared.activate(
                tenantKey: profile.tenantKey,
                userId: profile.userId
            )
            await KnowledgeNoteStore.shared.restoreFromCloud()
        } catch {
            // APIClient 会把真实 401 汇入 needsReauth；离线/超时保留 Keychain 登录态。
        }
    }

    @MainActor
    private func loadRequiredAgreement() async {
        guard !isAgreementLoading else { return }
        isAgreementLoading = true
        agreementError = nil
        defer { isAgreementLoading = false }
        do {
            let loaded = try await apiClient.fetchAgreement()
            guard loaded.version == apiClient.requiredAgreementVersion else {
                throw APIError.authenticationRejected("协议版本已更新，请重新加载。")
            }
            agreement = loaded
        } catch {
            agreement = nil
            agreementError = "协议暂时无法加载，请检查网络后重试。"
        }
    }

    @MainActor
    private func acceptRequiredAgreement() async {
        guard !isAgreementAccepting, let agreement,
              agreement.version == apiClient.requiredAgreementVersion else { return }
        isAgreementAccepting = true
        defer { isAgreementAccepting = false }
        do {
            _ = try await apiClient.acceptAgreement(
                version: agreement.version, idempotencyKey: agreementAcceptanceKey
            )
            apiClient.resolveAgreementRequirement(accepted: true)
            showingAgreement = false
        } catch {
            agreementError = "协议确认未完成，请重试。"
        }
    }
}

// MARK: - Xcode #Preview

#Preview("AppRoot - Logged Out") {
    AppRootCoordinatorView()
        .environmentObject(AppState(isLoggedIn: false))
        .environmentObject(APIClient.shared)
}

#Preview("AppRoot - Logged In") {
    AppRootCoordinatorView()
        .environmentObject(AppState(isLoggedIn: true))
        .environmentObject(APIClient.shared)
}
