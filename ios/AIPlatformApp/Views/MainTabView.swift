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
                QuantumFloatingTabBar(selection: $appState.activeTab)
                    .padding(.top, appState.activeTab == 2 ? 0 : AppTheme.Spacing.xs)
                    .padding(.bottom, appState.activeTab == 2 ? 0 : 10)
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
                    .background(selection == item.tag && selection != 2 ? Color.white.opacity(0.70) : Color.clear, in: Capsule())
                    .contentShape(Capsule())
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityIdentifier("main-tab-\(item.tag)")
                .accessibilityLabel(item.title)
                .accessibilityAddTraits(selection == item.tag ? .isSelected : [])
            }
        }
        .padding(6)
        .frame(height: selection == 2 ? 64 : 68)
        .background {
            if selection == 2 { AppTheme.Reading.paper }
            else { Capsule().fill(.ultraThinMaterial).background(Capsule().fill(.white.opacity(0.42))) }
        }
        .overlay {
            if selection == 2 {
                Rectangle().fill(AppTheme.Reading.border).frame(height: 0.5).frame(maxHeight: .infinity, alignment: .top)
            } else { Capsule().stroke(Color.white.opacity(0.82), lineWidth: 0.8) }
        }
        .shadow(color: selection == 2 ? .clear : Color(hex: "385A58").opacity(0.13), radius: 18, y: 7)
        .padding(.horizontal, selection == 2 ? 0 : AppTheme.Spacing.lg)
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
