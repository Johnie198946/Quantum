//
//  ChatTopBarView.swift
//  AIPlatformApp
//
//  Session Header Bar (Quantum Avatar, Status Dot, Title Drawer Trigger & Actions)
//  Extracted from ChatView for minimal footprint.
//

import SwiftUI

public struct ChatTopBarView: View {
    public let isGenerating: Bool
    public let title: String
    public let onWorkbenchTap: (() -> Void)?
    public let onTitleTap: () -> Void
    public let onNewSession: () -> Void
    public let onHistoryTap: () -> Void
    public let onClearTap: () -> Void

    public init(
        isGenerating: Bool,
        title: String,
        onWorkbenchTap: (() -> Void)? = nil,
        onTitleTap: @escaping () -> Void,
        onNewSession: @escaping () -> Void,
        onHistoryTap: @escaping () -> Void,
        onClearTap: @escaping () -> Void
    ) {
        self.isGenerating = isGenerating
        self.title = title
        self.onWorkbenchTap = onWorkbenchTap
        self.onTitleTap = onTitleTap
        self.onNewSession = onNewSession
        self.onHistoryTap = onHistoryTap
        self.onClearTap = onClearTap
    }

    public var body: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            if let onWorkbenchTap {
                Button(action: onWorkbenchTap) {
                    Image(systemName: "chevron.left")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .minimumTouchTarget()
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel("返回学习工作台")
                .accessibilityIdentifier("chat-back-to-workbench")
            } else {
                Color.clear.frame(width: 44, height: 44)
            }

            Button(action: onTitleTap) {
                Text(title.isEmpty ? "新对话" : title)
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundColor(AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(SoftButtonStyle())

            Menu {
                Button(action: onNewSession) {
                    Label("新建会话", systemImage: "square.and.pencil")
                }
                Button(action: onHistoryTap) {
                    Label("会话历史", systemImage: "clock.arrow.circlepath")
                }
                Button(role: .destructive, action: onClearTap) {
                    Label("清空当前对话", systemImage: "trash")
                }
            } label: {
                Image(systemName: "ellipsis")
                    .font(.body.weight(.semibold))
                        .foregroundColor(AppTheme.Icons.secondary)
                    .minimumTouchTarget()
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityLabel("更多会话操作")
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .frame(minHeight: 52)
        .background(Color(hex: "FCFBF7").opacity(0.97))
        .overlay(alignment: .bottom) { Divider().opacity(0.45) }
    }
}
