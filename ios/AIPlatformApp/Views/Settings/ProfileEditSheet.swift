//
//  ProfileEditSheet.swift
//  AIPlatformApp
//
//  个人信息修改 Sheet（⑤）：姓名 TextField + 青年头像素材预设
//  + 租户/角色只读；保存更新 AppState 并 PATCH /api/v1/me（离线自动降级本地 Mock）。
//

import SwiftUI

public struct ProfileEditSheet: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var api: APIClient
    @Environment(\.dismiss) private var dismiss

    @State private var name: String = ""
    @State private var avatarValue: String = "avatar_youth_01"
    @State private var isSaving: Bool = false

    private let avatarOptions = ContentAssetLibrary.avatarNames

    private let columns = [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())]

    public init() {}

    public var body: some View {
        NavigationStack {
            Form {
                Section("头像") {
                    LazyVGrid(columns: columns, spacing: AppTheme.Spacing.md) {
                        ForEach(avatarOptions, id: \.self) { avatar in
                            let selected = avatarValue == avatar
                            Button(action: {
                                #if os(iOS)
                                UIImpactFeedbackGenerator(style: .light).impactOccurred()
                                #endif
                                avatarValue = avatar
                            }) {
                                UserAvatarView(value: avatar, size: 56)
                                    .frame(width: 56, height: 56)
                                    .overlay(
                                        Circle().stroke(
                                            selected ? AppTheme.Colors.primary : AppTheme.Colors.border,
                                            lineWidth: selected ? 3 : 1
                                        )
                                    )
                            }
                            .buttonStyle(SoftButtonStyle())
                        }
                    }
                    .padding(.vertical, AppTheme.Spacing.xs)
                }

                Section("姓名") {
                    TextField("姓名", text: $name)
                        .font(.system(size: 15))
                }

                Section("账号") {
                    LabeledContent("身份", value: "普通用户")
                }
            }
            .navigationTitle("编辑个人信息")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: save) {
                        if isSaving {
                            ProgressView()
                        } else {
                            Text("保存")
                                .font(.system(size: 15, weight: .bold))
                        }
                    }
                    .disabled(isSaving || name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .onAppear {
            name = appState.currentProfile.name
            avatarValue = ContentAssetLibrary.avatarAssetName(for: appState.currentProfile.avatarUrl)
                ?? "avatar_youth_01"
        }
    }

    // MARK: - Actions

    private func save() {
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty else { return }
        isSaving = true
        #if os(iOS)
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        #endif

        // 本地 AppState 即时更新
        appState.currentProfile.name = trimmedName
        appState.currentProfile.avatarUrl = avatarValue

        // 联网同步后端（离线自动降级）
        Task {
            let isSideRoutePreview = ProcessInfo.processInfo.arguments.contains("-assetLibraryPreview")
            if !isSideRoutePreview && !api.isOfflineMode {
                _ = try? await api.patchMe(username: trimmedName, avatarUrl: avatarValue)
            }
            isSaving = false
            dismiss()
        }
    }
}

// MARK: - Xcode #Preview

#Preview("ProfileEditSheet - Light") {
    ProfileEditSheet()
        .environmentObject(AppState())
        .environmentObject(APIClient.shared)
}

#Preview("ProfileEditSheet - Dark") {
    ProfileEditSheet()
        .environmentObject(AppState())
        .environmentObject(APIClient.shared)
}
