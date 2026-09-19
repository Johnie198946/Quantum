//
//  MainTabView.swift
//  AIPlatformApp
//
//  Native iOS Bottom TabBar Navigation Container
//  Standard HIG Navigation Architecture with Smooth State Switching
//  + 开发态「开发模式·免鉴权」Quantum 蓝细 banner（顶部导航栏下）
//

import SwiftUI
#if os(iOS)
import UIKit
#endif

public struct MainTabView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator
    @EnvironmentObject private var sessionManager: SessionManager
    @StateObject private var keyboardObserver = KeyboardObserver()

    public init() {}

    public var body: some View {
        VStack(spacing: 0) {
            TabView(selection: $appState.activeTab) {

                // 首页：Chat Stream & Multiturn Dialogues
                ChatView()
                    .toolbar(.hidden, for: .tabBar)
                    .tabItem {
                        Label("首页", systemImage: "house.fill")
                    }
                    .tag(0)

                // 阅读：笔记、搜索、书架与阅读器共用现有知识链路。
                KnowledgeView()
                    .toolbar(.hidden, for: .tabBar)
                    .tabItem {
                        Label("阅读", systemImage: "book.fill")
                    }
                    .tag(2)

                // 工作流：可执行计划、运行、成果与拓扑。
                WorkflowDashboardView()
                    .toolbar(.hidden, for: .tabBar)
                    .tabItem {
                        Label("工作流", systemImage: "square.stack.3d.up.fill")
                    }
                    .tag(1)

                // 我的：Tenant Profile & Prompt Studio Settings
                SettingsView()
                    .toolbar(.hidden, for: .tabBar)
                    .tabItem {
                        Label("我的", systemImage: "person.fill")
                    }
                    .tag(3)
            }
            .toolbar(.hidden, for: .tabBar)

            if !keyboardObserver.isKeyboardVisible {
                bottomChrome
                    .padding(.top, AppTheme.Spacing.xs)
                    .padding(.bottom, 10)
            }
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            if appState.isDevMode {
                DevModeBanner()
                    .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: appState.isDevMode)
        .task(id: workflowScopeTaskID) {
            // Login/profile hydration and chat-session restoration complete on
            // different async paths. Bind the owner before selecting the
            // conversation so an early session cannot leave Task unscoped.
            let tenantId = appState.currentTenantKey
            let userId = appState.currentUserId
            guard !tenantId.isEmpty, !userId.isEmpty else {
                workflowActivities.deactivate()
                return
            }
            workflowActivities.activate(tenantKey: tenantId, userId: userId)
            workflowActivities.selectClientSession(sessionManager.activeSessionId)
            await workflowActivities.bootstrap()
        }
    }

    @ViewBuilder
    private var bottomChrome: some View {
        VStack(spacing: AppTheme.Spacing.xs) {
            if let activity = workflowActivities.primaryActivity {
                WorkflowActivityMiniBar(
                    activity: activity,
                    count: workflowActivities.visibleActivities.count,
                    onOpen: {
                        appState.openWorkflow(activity.workflow.id)
                    },
                    onDismiss: {
                        workflowActivities.dismiss(activity.workflow.id)
                    }
                )
                .padding(.horizontal, AppTheme.Spacing.lg)
            } else if let activity = workflowActivities.primaryExecutionActivity {
                WorkflowExecutionMiniBar(
                    activity: activity,
                    count: workflowActivities.visibleExecutionActivities.count,
                    onOpen: {
                        appState.openWorkflow(activity.workflow.id)
                    },
                    onDismiss: { workflowActivities.dismiss(activity.workflow.id) }
                )
                .padding(.horizontal, AppTheme.Spacing.lg)
            }
            QuantumFloatingTabBar(selection: $appState.activeTab)
        }
    }

    private var workflowScopeTaskID: String {
        [
            appState.currentTenantKey,
            appState.currentUserId,
            sessionManager.activeSessionId ?? ""
        ].joined(separator: "\u{0}")
    }
}

private final class KeyboardObserver: ObservableObject {
    @Published private(set) var isKeyboardVisible = false
    private let notificationCenter: NotificationCenter
    private var observers: [NSObjectProtocol] = []

    init(notificationCenter: NotificationCenter = .default) {
        self.notificationCenter = notificationCenter
        observers = [
            notificationCenter.addObserver(
                forName: UIResponder.keyboardWillShowNotification,
                object: nil,
                queue: .main
            ) { [weak self] _ in
                self?.isKeyboardVisible = true
            },
            notificationCenter.addObserver(
                forName: UIResponder.keyboardWillHideNotification,
                object: nil,
                queue: .main
            ) { [weak self] _ in
                self?.isKeyboardVisible = false
            }
        ]
    }

    deinit {
        observers.forEach(notificationCenter.removeObserver)
    }
}

private struct WorkflowExecutionMiniBar: View {
    let activity: WorkflowActivityCoordinator.ExecutionActivity
    let count: Int
    let onOpen: () -> Void
    let onDismiss: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var running: Bool { ["queued", "running"].contains(activity.execution.status) }
    private var statusText: String {
        switch activity.execution.status {
        case "queued": return "云端排队中"
        case "running": return "云端执行中 · \(activity.execution.progress)% · \(activity.execution.tokenUsed) tokens"
        case "awaiting_review": return "执行完成，待复核"
        case "failed": return "执行失败，点击查看或重试"
        default: return activity.execution.status
        }
    }

    var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Button(action: onOpen) {
                HStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: running ? "gearshape.2.fill" : "checkmark.doc")
                        .foregroundStyle(AppTheme.Colors.quantumBlue)
                        .symbolEffect(.pulse, isActive: running && !reduceMotion)
                        .frame(width: 36, height: 36)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(count > 1 ? "\(activity.workflow.title) · 另有 \(count - 1) 项" : activity.workflow.title)
                            .font(AppTheme.Typography.supporting.weight(.semibold)).lineLimit(1)
                        Text(statusText).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary).lineLimit(1)
                    }
                    Spacer(minLength: 0)
                    if running { ProgressView().controlSize(.small) }
                    else { Image(systemName: "chevron.right").font(.caption.weight(.semibold)) }
                }
                .frame(maxWidth: .infinity, minHeight: 48)
                .contentShape(Rectangle())
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityLabel("\(activity.workflow.title)，\(statusText)")
            if !running {
                Button(action: onDismiss) { Image(systemName: "xmark").frame(width: 44, height: 44) }
                    .buttonStyle(SoftButtonStyle())
                    .accessibilityLabel("关闭任务状态")
            }
        }
        .padding(.horizontal, AppTheme.Spacing.sm)
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
    }
}

private struct WorkflowActivityMiniBar: View {
    let activity: WorkflowActivityCoordinator.Activity
    let count: Int
    let onOpen: () -> Void
    let onDismiss: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var isRunning: Bool {
        ["clarifying_pending", "planning", "building_agent"].contains(activity.model.phase)
    }

    private var statusText: String {
        if activity.model.phase == "clarifying" { return "等待确认需求" }
        if activity.model.phase == "clarifying_pending" { return "正在阅读文档并收敛需求" }
        if activity.model.phase == "awaiting_approval" { return "方案可审阅" }
        if activity.model.phase == "needs_attention" { return "规划需要处理" }
        if let message = activity.model.events.last?.message { return message }
        return activity.model.optimisticPlanningMessage ?? "云端正在准备规划"
    }

    var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Button(action: onOpen) {
                HStack(spacing: AppTheme.Spacing.sm) {
                    ZStack {
                        Circle()
                            .fill(AppTheme.Colors.selectionTint)
                            .frame(width: 36, height: 36)
                        Image(systemName: isRunning ? "sparkles" : "doc.text.magnifyingglass")
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                            .symbolEffect(.pulse, isActive: isRunning && !reduceMotion)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(count > 1 ? "\(activity.workflow.title) · 另有 \(count - 1) 项" : activity.workflow.title)
                            .font(AppTheme.Typography.supporting.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .lineLimit(1)
                        Text(statusText)
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                    if isRunning {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.textTertiary)
                    }
                }
                .contentShape(Rectangle())
                .frame(maxWidth: .infinity, minHeight: 48)
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityLabel("\(activity.workflow.title)，\(statusText)")
            .accessibilityHint("返回任务查看规划进度")

            if !isRunning {
                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.semibold))
                        .frame(width: 44, height: 44)
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel("关闭任务状态")
            }
        }
        .padding(.horizontal, AppTheme.Spacing.sm)
        .background(.ultraThinMaterial)
        .background(AppTheme.Colors.surfaceElevated.opacity(0.94))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.9), lineWidth: 0.75)
        }
        .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
        .shadow(color: Color.black.opacity(0.08), radius: 14, y: 6)
        .transition(reduceMotion ? .opacity : .move(edge: .bottom).combined(with: .opacity))
    }
}

private struct QuantumFloatingTabBar: View {
    @Binding var selection: Int
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private let items: [(tag: Int, title: String, symbol: String, selectedSymbol: String)] = [
        (0, "首页", "house", "house.fill"),
        (2, "阅读", "book", "book.fill"),
        (1, "工作流", "square.stack.3d.up", "square.stack.3d.up.fill"),
        (3, "我的", "person", "person.fill")
    ]

    var body: some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            ForEach(items, id: \.tag) { item in
                Button {
                    guard selection != item.tag else { return }
                    #if os(iOS)
                    UISelectionFeedbackGenerator().selectionChanged()
                    #endif
                    if reduceMotion {
                        selection = item.tag
                    } else {
                        withAnimation(AppTheme.Motion.spring) { selection = item.tag }
                    }
                } label: {
                    VStack(spacing: 3) {
                        Image(systemName: selection == item.tag ? item.selectedSymbol : item.symbol)
                            .font(.system(size: 18, weight: .semibold))
                            .frame(height: 22)
                        Text(item.title)
                            .font(.caption2.weight(selection == item.tag ? .bold : .medium))
                    }
                    .foregroundStyle(selection == item.tag ? AppTheme.Colors.primary : AppTheme.Icons.navigationInactive)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(selection == item.tag ? Color.white.opacity(0.70) : Color.clear, in: Capsule())
                    .contentShape(Capsule())
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityIdentifier("main-tab-\(item.tag)")
                .accessibilityLabel(item.title)
                .accessibilityAddTraits(selection == item.tag ? .isSelected : [])
            }
        }
        .padding(6)
        .frame(height: 68)
        .background(.ultraThinMaterial)
        .background(Color.white.opacity(0.42))
        .clipShape(Capsule())
        .overlay { Capsule().stroke(Color.white.opacity(0.82), lineWidth: 0.8) }
        .shadow(color: Color(hex: "385A58").opacity(0.13), radius: 18, y: 7)
        .padding(.horizontal, AppTheme.Spacing.lg)
    }
}

// MARK: - 开发模式·免鉴权 提示 banner（Quantum 蓝细窄条 · 小号白字）

public struct DevModeBanner: View {
    public init() {}

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            Image(systemName: "shield.lefthalf.filled.badge.checkmark")
                .font(.caption2.weight(.semibold))
            Text("开发模式·免鉴权")
                .font(AppTheme.Typography.micro)
        }
        .foregroundColor(AppTheme.Icons.onAccent)
        .frame(maxWidth: .infinity)
        .padding(.vertical, 5)
        .background(AppTheme.Colors.quantumGradient)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Xcode #Preview

#Preview("MainTabView - Light") {
    MainTabView()
        .environmentObject(AppState())
}

#Preview("MainTabView - Dark") {
    MainTabView()
        .environmentObject(AppState())
}
