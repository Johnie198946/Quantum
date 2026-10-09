//
//  PlusMenuSheet.swift
//  AIPlatformApp
//
//  对话页「+」号四入口扩展面板：
//   1. 📸 照片图库（PhotosPicker，保留原图与透明度）
//   2. 📄 文档文件（fileImporter，读取 Data 前 resourceValues(.fileSizeKey) 25 MB 前置预检）
//   3. 💬 微信导入（WeChatLinkValidator 校验 mp.weixin.qq.com 白名单 + 非法 Toast）
//   4. 🧠 引用知识（选取已订阅知识条目）
//

import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

public struct PlusMenuSheet: View {

    public var onPhotoPicked: (Data) -> Void
    public var onDocumentPicked: (URL) -> Void
    public var onWeChatImported: (String) -> Void
    public var onQuanSynImported: (QuanSynTransferDTO) async throws -> Void
    public var onKnowledgeReferenced: (KnowledgeItem) -> Void

    @Environment(\.dismiss) private var dismiss

    @State private var photoItem: PhotosPickerItem? = nil
    @State private var isFileImporterPresented: Bool = false
    @State private var showWeChatImport: Bool = false
    @State private var quanSynItems: [QuanSynTransferDTO] = []
    @State private var quanSynError: String?
    @State private var quanSynBusy = false
    @State private var wechatLink: String = ""
    @State private var showKnowledgePicker: Bool = false
    @State private var toast: ToastState? = nil

    public init(
        onPhotoPicked: @escaping (Data) -> Void,
        onDocumentPicked: @escaping (URL) -> Void,
        onWeChatImported: @escaping (String) -> Void,
        onQuanSynImported: @escaping (QuanSynTransferDTO) async throws -> Void,
        onKnowledgeReferenced: @escaping (KnowledgeItem) -> Void
    ) {
        self.onPhotoPicked = onPhotoPicked
        self.onDocumentPicked = onDocumentPicked
        self.onWeChatImported = onWeChatImported
        self.onQuanSynImported = onQuanSynImported
        self.onKnowledgeReferenced = onKnowledgeReferenced
    }

    public var body: some View {
        NavigationStack {
            ZStack {
                AppTheme.Colors.groupedBackground
                    .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: AppTheme.Spacing.md) {
                        photosEntry
                        #if DEBUG
                        if ProcessInfo.processInfo.arguments.contains("-imageWorkflowAcceptance") {
                            Button("上传验收示例照片") {
                                if let data = UIImage(named: "travel_kyoto_street")?.pngData(),
                                   let original = ImageEditSupport.uploadData(data) {
                                    onPhotoPicked(original)
                                    dismiss()
                                }
                            }.accessibilityIdentifier("image-acceptance-upload")
                        }
                        #endif
                        documentEntry
                        wechatEntry
                        if showWeChatImport {
                            quanSynImportSection
                                .transition(.opacity.combined(with: .move(edge: .top)))
                        }
                        knowledgeEntry
                        if showKnowledgePicker {
                            knowledgePickerSection
                                .transition(.opacity.combined(with: .move(edge: .top)))
                        }
                    }
                    .padding(AppTheme.Spacing.lg)
                }
            }
            .navigationTitle("添加内容")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("完成") { dismiss() }
                        .foregroundColor(AppTheme.Colors.primary)
                }
            }
            .fileImporter(
                isPresented: $isFileImporterPresented,
                allowedContentTypes: [.pdf, .image, .commaSeparatedText, .json, .plainText, UTType(filenameExtension: "md") ?? .plainText, UTType(filenameExtension: "doc") ?? .data, UTType(filenameExtension: "ppt") ?? .data, UTType(filenameExtension: "docx")!, UTType(filenameExtension: "pptx")!],
                allowsMultipleSelection: false,
                onCompletion: handleDocumentImport
            )
            .onChange(of: photoItem) { _, item in
                loadPhoto(item)
            }
            .overlay {
                if let toast = toast {
                    toastView(toast)
                }
            }
        }
    }

    // MARK: - 四入口

    private var photosEntry: some View {
        PhotosPicker(selection: $photoItem, matching: .images, photoLibrary: .shared()) {
            entryRow(
                icon: "photo.on.rectangle.angled",
                title: "照片图库",
                subtitle: "选一张照片，说说你想怎么改",
                tint: AppTheme.Colors.quantumCyan
            )
        }
    }

    private var documentEntry: some View {
        Button {
            isFileImporterPresented = true
        } label: {
            entryRow(
                icon: "doc.fill",
                title: "文档文件",
                subtitle: "25 MB 前置预检拦截",
                tint: AppTheme.Colors.quantumBlue
            )
        }
        .buttonStyle(SoftButtonStyle())
    }

    private var wechatEntry: some View {
        Button {
            showWeChatImport.toggle()
            if showWeChatImport { refreshQuanSyn() }
        } label: {
            entryRow(
                icon: "arrow.triangle.2.circlepath",
                title: "QuanSyn",
                subtitle: "拉取 Web 资料到当前输入框",
                tint: AppTheme.Colors.quantumCyan
            )
        }
        .buttonStyle(SoftButtonStyle())
    }

    private var knowledgeEntry: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.2)) { showKnowledgePicker.toggle() }
        } label: {
            entryRow(
                icon: "brain.head.profile",
                title: "引用知识",
                subtitle: "选取已订阅知识条目",
                tint: AppTheme.Colors.quantumViolet
            )
        }
        .buttonStyle(SoftButtonStyle())
    }

    private func refreshQuanSyn() {
        quanSynBusy = true; quanSynError = nil
        Task {
            defer { quanSynBusy = false }
            do { quanSynItems = try await APIClient.shared.fetchQuanSyn() }
            catch { quanSynError = error.localizedDescription }
        }
    }

    private var quanSynImportSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            if quanSynBusy { ProgressView("正在处理 QuanSyn 资料…") }
            if let quanSynError { Text(quanSynError).foregroundStyle(.red) }
            if !quanSynBusy && quanSynItems.isEmpty { Text("暂无待拉取资料，请先在 QuanSyn Web 发送需求。") }
            ForEach(quanSynItems) { item in
                Button {
                    quanSynBusy = true; quanSynError = nil
                    Task {
                        defer { quanSynBusy = false }
                        do { try await onQuanSynImported(item); dismiss() }
                        catch { quanSynError = error.localizedDescription }
                    }
                } label: {
                    VStack(alignment: .leading) {
                        Text(item.text.isEmpty ? "附件资料" : item.text).lineLimit(3)
                        Text("\(item.files.count) 个附件 · \(item.id)").font(.caption).foregroundStyle(.secondary)
                    }
                }.disabled(quanSynBusy)
            }
            Button("刷新", action: refreshQuanSyn).disabled(quanSynBusy)
        }.padding().background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - 微信导入子面板

    private var wechatImportSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Text("粘贴微信公众号文章链接")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(AppTheme.Colors.textSecondary)

            HStack(spacing: AppTheme.Spacing.sm) {
                TextField("https://mp.weixin.qq.com/s/...", text: $wechatLink)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .font(.system(size: 13))
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, 10)
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))

                Button("校验导入") { validateWeChatLink() }
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(AppTheme.Colors.onPrimary)
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.vertical, 10)
                    .background(AppTheme.Colors.primary)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                    .buttonStyle(SoftButtonStyle())
            }

            Text("文章内容抓取由后端引擎承接（后续轮次）；本轮仅做域名白名单校验。")
                .font(.system(size: 11))
                .foregroundColor(AppTheme.Colors.textTertiary)
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    // MARK: - 引用知识子面板

    private var subscribedKnowledgeItems: [KnowledgeItem] {
        let subscribed = MockData.knowledgeItems.filter { $0.isSubscribed }
        return subscribed.isEmpty ? Array(MockData.knowledgeItems) : subscribed
    }

    private var knowledgePickerSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            ForEach(subscribedKnowledgeItems) { item in
                Button {
                    onKnowledgeReferenced(item)
                    showToast("已引用知识条目", isError: false)
                    dismiss()
                } label: {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Image(systemName: item.securityLevel.iconName)
                            .font(.system(size: 14))
                            .foregroundColor(item.securityLevel.color)
                            .frame(width: 20)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.title)
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(AppTheme.Colors.textPrimary)
                                .lineLimit(1)
                            Text(item.domain)
                                .font(.system(size: 11))
                                .foregroundColor(AppTheme.Colors.textTertiary)
                        }

                        Spacer()

                        Image(systemName: "quote.bubble")
                            .font(.system(size: 14))
                            .foregroundColor(AppTheme.Icons.tertiary)
                    }
                    .padding(AppTheme.Spacing.sm)
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
                }
                .buttonStyle(SoftButtonStyle())
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    // MARK: - 入口行

    private func entryRow(icon: String, title: String, subtitle: String, tint: Color) -> some View {
        HStack(spacing: AppTheme.Spacing.md) {
            ZStack {
                RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                    .fill(tint.opacity(0.14))
                    .frame(width: 44, height: 44)
                Image(systemName: icon)
                    .font(.system(size: 19, weight: .semibold))
                    .foregroundColor(tint)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(AppTheme.Colors.textPrimary)
                Text(subtitle)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textTertiary)
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(AppTheme.Icons.tertiary)
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    // MARK: - Toast

    private struct ToastState {
        let message: String
        let isError: Bool
    }

    private func toastView(_ toast: ToastState) -> some View {
        VStack {
            Spacer()
            Text(toast.message)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(AppTheme.Colors.onPrimary)
                .padding(.horizontal, AppTheme.Spacing.lg)
                .padding(.vertical, AppTheme.Spacing.sm + 2)
                .background(toast.isError ? AppTheme.Colors.securityRed : AppTheme.Colors.quantumBlue)
                .clipShape(Capsule())
                .shadow(color: Color.black.opacity(0.2), radius: 8, y: 3)
                .padding(.bottom, AppTheme.Spacing.xl)
        }
        .allowsHitTesting(false)
    }

    private func showToast(_ message: String, isError: Bool) {
        withAnimation(.easeInOut(duration: 0.15)) {
            toast = ToastState(message: message, isError: isError)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            withAnimation(.easeInOut(duration: 0.15)) {
                toast = nil
            }
        }
    }

    // MARK: - Actions

    private func loadPhoto(_ item: PhotosPickerItem?) {
        guard let item = item else { return }
        photoItem = nil // 复位，允许再次选择同一张

        Task {
            guard let data = try? await item.loadTransferable(type: Data.self) else {
                showToast("照片加载失败", isError: true)
                return
            }
            guard let original = ImageEditSupport.uploadData(data) else {
                showToast("请选择 12 MB、2400 万像素以内的静态图片", isError: true)
                return
            }
            onPhotoPicked(original)
            showToast("正在上传图片", isError: false)
            dismiss()
        }
    }

    private func handleDocumentImport(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            // 前置预检：读取 Data 前通过 resourceValues(.fileSizeKey) 拦截超限
            if let size = InboxFileManager.shared.fileSizeBytes(at: url),
               size > InboxFileManager.maxFileSizeBytes {
                showToast("文件超过 25 MB，已拦截", isError: true)
                return
            }
            onDocumentPicked(url)
            showToast("正在安全上传文档", isError: false)
            dismiss()
        case .failure:
            showToast("文档读取失败", isError: true)
        }
    }

    private func validateWeChatLink() {
        let result = WeChatLinkValidator.validate(wechatLink)
        if result.isValid {
            onWeChatImported(wechatLink.trimmingCharacters(in: .whitespacesAndNewlines))
            showToast(result.reason, isError: false)
            withAnimation(.easeInOut(duration: 0.2)) { showWeChatImport = false }
        } else {
            showToast(result.reason, isError: true)
        }
    }
}

// MARK: - Xcode #Preview

#Preview("PlusMenuSheet - Light") {
    PlusMenuSheet(
        onPhotoPicked: { _ in },
        onDocumentPicked: { _ in },
        onWeChatImported: { _ in },
        onQuanSynImported: { _ in throw APIError.network("预览不执行导入") },
        onKnowledgeReferenced: { _ in }
    )
}

#Preview("PlusMenuSheet - Dark") {
    PlusMenuSheet(
        onPhotoPicked: { _ in },
        onDocumentPicked: { _ in },
        onWeChatImported: { _ in },
        onQuanSynImported: { _ in throw APIError.network("预览不执行导入") },
        onKnowledgeReferenced: { _ in }
    )
}
