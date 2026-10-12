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
                TravelSpaceView()
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
                    .padding(.top, 4)
                    .padding(.bottom, 6)
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

struct QuantumFloatingTabBar: View {
    @Binding var selection: Int
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Namespace private var liquidSelection
    @State private var stretching = false
    private let items: [(tag: Int, title: String, symbol: String)] = [
        (0, "首页", "house"), (2, "阅读", "book"),
        (1, "工作流", "square.3.layers.3d"), (3, "我的", "person")
    ]
    var body: some View {
        HStack(spacing: 6) {
            ForEach(items, id: \.tag) { item in
                Button { choose(item.tag) } label: {
                    HStack(spacing: 9) {
                        Image(systemName: item.symbol)
                            .font(.system(size: 19, weight: .regular))
                        if selection == item.tag {
                            Text(item.title).font(.system(size: 13, weight: .semibold))
                                .transition(.opacity.combined(with: .scale(scale: 0.9)))
                        }
                    }
                    .foregroundStyle(selection == item.tag ? Color(hex: "263D35") : Color(hex: "61726D"))
                    .frame(minWidth: 44, minHeight: 46)
                    .padding(.horizontal, selection == item.tag ? 12 : 0)
                    .background {
                        if selection == item.tag {
                            Capsule().fill(AppTheme.Colors.confirmationGradient)
                                .overlay(Capsule().strokeBorder(.white.opacity(0.8), lineWidth: 1))
                                .scaleEffect(x: stretching && !reduceMotion ? 1.08 : 1,
                                             y: stretching && !reduceMotion ? 0.96 : 1)
                                .matchedGeometryEffect(id: "selected", in: liquidSelection)
                        }
                    }
                    .contentShape(Capsule())
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityIdentifier("main-tab-\(item.tag)")
                .accessibilityLabel(item.title)
                .accessibilityAddTraits(selection == item.tag ? .isSelected : [])
            }
        }
        .padding(6)
        .background(.ultraThinMaterial, in: Capsule())
        .overlay(Capsule().strokeBorder(.white.opacity(0.85), lineWidth: 1))
        .shadow(color: Color(hex: "647F75").opacity(0.13), radius: 22, y: 8)
        .padding(.horizontal, 24)
        .frame(maxWidth: .infinity)
        .gesture(DragGesture(minimumDistance: 20).onEnded { value in
            guard abs(value.translation.width) > abs(value.translation.height),
                  let index = items.firstIndex(where: { $0.tag == selection }) else { return }
            let next = min(items.count - 1, max(0, index + (value.translation.width < 0 ? 1 : -1)))
            choose(items[next].tag)
        })
    }
    private func choose(_ tag: Int) {
        guard selection != tag else { return }
        UISelectionFeedbackGenerator().selectionChanged()
        if reduceMotion { selection = tag; return }
        withAnimation(.spring(response: 0.38, dampingFraction: 0.76)) {
            stretching = true; selection = tag
        }
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(140))
            withAnimation(.spring(response: 0.32, dampingFraction: 0.8)) { stretching = false }
        }
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
