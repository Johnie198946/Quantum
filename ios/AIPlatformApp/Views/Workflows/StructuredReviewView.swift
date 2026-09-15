import SwiftUI

@MainActor
final class StructuredReviewViewModel: ObservableObject {
    @Published var document: StructuredReviewDocumentDTO
    @Published private(set) var revision: StructuredReviewRevisionDTO?
    @Published private(set) var conflict: StructuredReviewConflictDTO?
    @Published private(set) var isLoading = false
    @Published private(set) var isSaving = false
    @Published var errorMessage: String?

    let workflowId: String
    let reviewKey: String
    let schemaId: String
    private let initialDocument: StructuredReviewDocumentDTO
    private let apiClient: APIClient
    private var etag: String?

    init(
        workflowId: String,
        reviewKey: String,
        schemaId: String,
        initialDocument: StructuredReviewDocumentDTO,
        apiClient: APIClient
    ) {
        self.workflowId = workflowId
        self.reviewKey = reviewKey
        self.schemaId = schemaId
        self.initialDocument = initialDocument
        self.document = initialDocument
        self.apiClient = apiClient
    }

    var completedFieldCount: Int {
        document.fields.filter { field in
            guard let value = document.values[field.id] else { return false }
            if case .null = value { return false }
            if case .string(let text) = value { return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            return true
        }.count
    }

    var progress: Double {
        document.fields.isEmpty ? 0 : Double(completedFieldCount) / Double(document.fields.count)
    }

    func load() async {
        guard revision == nil, !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            try apply(try await apiClient.fetchStructuredReview(workflowId: workflowId, reviewKey: reviewKey))
        } catch APIError.server(404, _) {
            await createAfterNotFound()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func save() async {
        guard !isSaving else { return }
        guard missingRequiredFields.isEmpty else {
            errorMessage = "请先填写：\(missingRequiredFields.joined(separator: "、"))"
            return
        }
        guard let etag else {
            errorMessage = "审核版本缺少 ETag，请重新加载"
            return
        }
        isSaving = true
        defer { isSaving = false }
        do {
            try apply(try await apiClient.saveStructuredReview(
                workflowId: workflowId,
                reviewKey: reviewKey,
                schemaId: revision?.schemaId ?? schemaId,
                document: document,
                etag: etag
            ))
        } catch let error as StructuredReviewConflictError {
            conflict = error.payload
            errorMessage = error.payload.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func undo() async {
        guard !isSaving, let etag else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            try apply(try await apiClient.undoStructuredReview(
                workflowId: workflowId,
                reviewKey: reviewKey,
                etag: etag
            ))
        } catch let error as StructuredReviewConflictError {
            conflict = error.payload
            errorMessage = error.payload.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadRemoteConflict() async {
        guard conflict != nil else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            try apply(try await apiClient.fetchStructuredReview(workflowId: workflowId, reviewKey: reviewKey))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func mergeLocalChangesOverRemote() {
        guard let conflict else { return }
        guard conflict.remoteEtag.first == "\"", conflict.remoteEtag.last == "\"" else {
            errorMessage = "冲突响应缺少带引号的远端 ETag"
            return
        }
        let local = document
        var merged = conflict.remote.document
        merged.title = local.title
        for field in merged.fields where local.values[field.id] != nil {
            merged.values[field.id] = local.values[field.id]
        }
        revision = conflict.remote
        document = merged
        etag = conflict.remoteEtag
        self.conflict = nil
        errorMessage = nil
    }

    private var missingRequiredFields: [String] {
        document.fields.filter { field in
            guard field.required, let value = document.values[field.id] else { return field.required }
            if case .null = value { return true }
            if case .string(let text) = value { return text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            return false
        }.map(\.label)
    }

    private func createAfterNotFound() async {
        do {
            try apply(try await apiClient.createStructuredReview(
                workflowId: workflowId,
                reviewKey: reviewKey,
                schemaId: schemaId,
                document: initialDocument
            ))
        } catch APIError.server(409, _) {
            do {
                try apply(try await apiClient.fetchStructuredReview(workflowId: workflowId, reviewKey: reviewKey))
            } catch {
                errorMessage = error.localizedDescription
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func apply(_ response: APIResponse<StructuredReviewRevisionDTO>) throws {
        guard let etag = response.etag, etag.first == "\"", etag.last == "\"" else {
            throw APIError.decoding("结构化审核响应缺少带引号的 ETag")
        }
        revision = response.value
        document = response.value.document
        self.etag = etag
        conflict = nil
        errorMessage = nil
    }
}

public struct StructuredReviewView: View {
    @StateObject private var model: StructuredReviewViewModel

    @MainActor public init(
        workflowId: String,
        reviewKey: String,
        schemaId: String = "workflow.structured-review.v1",
        initialDocument: StructuredReviewDocumentDTO
    ) {
        _model = StateObject(wrappedValue: StructuredReviewViewModel(
            workflowId: workflowId,
            reviewKey: reviewKey,
            schemaId: schemaId,
            initialDocument: initialDocument,
            apiClient: .shared
        ))
    }

    @MainActor init(model: StructuredReviewViewModel) {
        _model = StateObject(wrappedValue: model)
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            header
            if model.isLoading && model.revision == nil {
                ProgressView("正在读取结构化审核…")
                    .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
            } else if model.revision != nil {
                fields
                actions
            }
            if let conflict = model.conflict { conflictView(conflict) }
            if let error = model.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.statusError)
                    .accessibilityLabel("结构化审核错误：\(error)")
            }
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous)
                .stroke(AppTheme.Colors.border, lineWidth: 1)
        }
        .task { await model.load() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack {
                Label("结构化审核", systemImage: "checklist")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.Icons.intelligence)
                Spacer()
                if let revision = model.revision {
                    Text("版本 \(revision.version)")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
            }
            Text(model.document.title)
                .font(AppTheme.Typography.sectionTitle)
                .foregroundStyle(AppTheme.Colors.textPrimary)
            ProgressView(value: model.progress)
                .tint(AppTheme.Colors.quantumBlue)
                .accessibilityLabel("审核进度")
                .accessibilityValue("已填写 \(model.completedFieldCount) 项，共 \(model.document.fields.count) 项")
            Text("已填写 \(model.completedFieldCount)/\(model.document.fields.count) 项")
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textSecondary)
        }
    }

    private var fields: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            ForEach(model.document.fields) { field in
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    Text(field.label + (field.required ? " *" : ""))
                        .font(AppTheme.Typography.label)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    fieldControl(field)
                }
            }
        }
    }

    @ViewBuilder
    private func fieldControl(_ field: StructuredReviewFieldDTO) -> some View {
        switch field.type {
        case .text:
            TextField(field.label, text: stringBinding(field.id))
                .textFieldStyle(.roundedBorder)
                .frame(minHeight: AppTheme.Metrics.inputHeight)
                .accessibilityLabel(field.label)
        case .textarea:
            TextField(field.label, text: stringBinding(field.id), axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(3...8)
                .frame(minHeight: 96)
                .accessibilityLabel(field.label)
        case .choice:
            Picker(field.label, selection: stringBinding(field.id)) {
                Text("请选择").tag("")
                ForEach(field.options ?? [], id: \.self) { Text($0).tag($0) }
            }
            .pickerStyle(.menu)
            .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.inputHeight, alignment: .leading)
            .accessibilityLabel(field.label)
        case .number:
            TextField(field.label, text: numberBinding(field.id))
                .keyboardType(.decimalPad)
                .textFieldStyle(.roundedBorder)
                .frame(minHeight: AppTheme.Metrics.inputHeight)
                .accessibilityLabel(field.label)
        case .toggle:
            Toggle(field.label, isOn: boolBinding(field.id))
                .labelsHidden()
                .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget, alignment: .leading)
                .accessibilityLabel(field.label)
        }
    }

    private var actions: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Button("撤销", systemImage: "arrow.uturn.backward") { Task { await model.undo() } }
                .buttonStyle(.bordered)
                .disabled(model.isSaving || (model.revision?.version ?? 0) < 2)
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            Button("保存审核", systemImage: "checkmark") { Task { await model.save() } }
                .buttonStyle(.borderedProminent)
                .disabled(model.isSaving)
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            if model.isSaving { ProgressView().accessibilityLabel("正在保存审核") }
        }
        .controlSize(.large)
    }

    private func conflictView(_ conflict: StructuredReviewConflictDTO) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Label("发现版本冲突", systemImage: "arrow.triangle.2.circlepath")
                .font(AppTheme.Typography.cardTitle)
                .foregroundStyle(AppTheme.Colors.statusWarning)
            Text(conflict.message)
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            ForEach(model.document.fields) { field in
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text(field.label).font(AppTheme.Typography.label)
                    Text("本地：\(display(model.document.values[field.id]))")
                    Text("服务端：\(display(conflict.remote.document.values[field.id]))")
                }
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textPrimary)
            }
            HStack(spacing: AppTheme.Spacing.md) {
                Button("保留本地修改", systemImage: "arrow.triangle.merge") {
                    model.mergeLocalChangesOverRemote()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                .accessibilityHint("以服务端最新版本为基础保留本地同名字段，随后可再次保存")

                Button("载入服务端版本", systemImage: "arrow.clockwise") {
                    Task { await model.loadRemoteConflict() }
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                .accessibilityHint("放弃本地修改并载入服务端最新版本")
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.warningSurface)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private func stringBinding(_ id: String) -> Binding<String> {
        Binding(
            get: { if case .string(let value) = model.document.values[id] { return value }; return "" },
            set: { model.document.values[id] = $0.isEmpty ? .null : .string($0) }
        )
    }

    private func numberBinding(_ id: String) -> Binding<String> {
        Binding(
            get: {
                switch model.document.values[id] {
                case .integer(let value): return String(value)
                case .number(let value): return String(value)
                default: return ""
                }
            },
            set: { model.document.values[id] = Double($0.replacingOccurrences(of: ",", with: ".")).map(JSONScalar.number) ?? .null }
        )
    }

    private func boolBinding(_ id: String) -> Binding<Bool> {
        Binding(
            get: { if case .bool(let value) = model.document.values[id] { return value }; return false },
            set: { model.document.values[id] = .bool($0) }
        )
    }

    private func display(_ value: JSONScalar?) -> String {
        switch value {
        case .string(let value): return value
        case .integer(let value): return value.formatted()
        case .number(let value): return value.formatted()
        case .bool(let value): return value ? "是" : "否"
        case .null, nil: return "未填写"
        }
    }
}
