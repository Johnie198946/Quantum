import SwiftUI

enum StructuredReviewValueRestorer {
    static func value(fieldID: String, from document: StructuredReviewDocumentDTO) -> JSONScalar? {
        document.values[fieldID]
    }
}

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
    private var savedDocument: StructuredReviewDocumentDTO
    private let apiClient: APIClient
    private let scope: WorkflowActivityCoordinator.Scope?
    private let isScopeCurrent: (WorkflowActivityCoordinator.Scope) -> Bool
    private var etag: String?

    init(
        workflowId: String,
        reviewKey: String,
        schemaId: String,
        initialDocument: StructuredReviewDocumentDTO,
        apiClient: APIClient,
        scope: WorkflowActivityCoordinator.Scope? = nil,
        isScopeCurrent: @escaping (WorkflowActivityCoordinator.Scope) -> Bool = { _ in true }
    ) {
        self.workflowId = workflowId
        self.reviewKey = reviewKey
        self.schemaId = schemaId
        self.initialDocument = initialDocument
        self.savedDocument = initialDocument
        self.document = initialDocument
        self.apiClient = apiClient
        self.scope = scope
        self.isScopeCurrent = isScopeCurrent
    }

    private var scopeIsCurrent: Bool { scope.map(isScopeCurrent) ?? true }

    var completedFieldCount: Int {
        document.fields.filter { field in
            hasValue(document.values[field.id], for: field.type)
        }.count
    }

    var progress: Double {
        document.fields.isEmpty ? 0 : Double(completedFieldCount) / Double(document.fields.count)
    }

    func load() async {
        guard scopeIsCurrent, revision == nil, !isLoading else { return }
        isLoading = true
        defer { if scopeIsCurrent { isLoading = false } }
        do {
            let response = try await apiClient.fetchStructuredReview(workflowId: workflowId, reviewKey: reviewKey)
            guard scopeIsCurrent else { return }
            try apply(response)
        } catch APIError.server(404, _) {
            guard scopeIsCurrent else { return }
            await createAfterNotFound()
        } catch {
            guard scopeIsCurrent else { return }
            errorMessage = error.localizedDescription
        }
    }

    func save() async {
        guard scopeIsCurrent, !isSaving else { return }
        guard missingRequiredFields.isEmpty else {
            errorMessage = "请先填写：\(missingRequiredFields.joined(separator: "、"))"
            return
        }
        guard let etag else {
            errorMessage = "审核版本缺少 ETag，请重新加载"
            return
        }
        isSaving = true
        defer { if scopeIsCurrent { isSaving = false } }
        do {
            let response = try await apiClient.saveStructuredReview(
                workflowId: workflowId,
                reviewKey: reviewKey,
                schemaId: revision?.schemaId ?? schemaId,
                document: document,
                etag: etag
            )
            guard scopeIsCurrent else { return }
            try apply(response)
        } catch let error as StructuredReviewConflictError {
            guard scopeIsCurrent else { return }
            conflict = error.payload
            errorMessage = error.payload.message
        } catch {
            guard scopeIsCurrent else { return }
            errorMessage = error.localizedDescription
        }
    }

    func undo() async {
        guard scopeIsCurrent, !isSaving, let etag else { return }
        isSaving = true
        defer { if scopeIsCurrent { isSaving = false } }
        do {
            let response = try await apiClient.undoStructuredReview(
                workflowId: workflowId,
                reviewKey: reviewKey,
                etag: etag
            )
            guard scopeIsCurrent else { return }
            try apply(response)
        } catch let error as StructuredReviewConflictError {
            guard scopeIsCurrent else { return }
            conflict = error.payload
            errorMessage = error.payload.message
        } catch {
            guard scopeIsCurrent else { return }
            errorMessage = error.localizedDescription
        }
    }

    func loadRemoteConflict() async {
        guard scopeIsCurrent, conflict != nil else { return }
        isLoading = true
        defer { if scopeIsCurrent { isLoading = false } }
        do {
            let response = try await apiClient.fetchStructuredReview(workflowId: workflowId, reviewKey: reviewKey)
            guard scopeIsCurrent else { return }
            try apply(response)
        } catch {
            guard scopeIsCurrent else { return }
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

    func restoreSavedValue(fieldID: String) {
        if let savedValue = StructuredReviewValueRestorer.value(fieldID: fieldID, from: savedDocument) {
            document.values[fieldID] = savedValue
        } else {
            document.values.removeValue(forKey: fieldID)
        }
        errorMessage = nil
    }

    private var missingRequiredFields: [String] {
        document.fields.filter { field in
            field.required && !hasValue(document.values[field.id], for: field.type)
        }.map(\.label)
    }

    private func hasValue(_ value: JSONScalar?, for type: StructuredReviewFieldType) -> Bool {
        guard let value else { return false }
        switch value {
        case .null:
            return false
        case .string(let text):
            return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .array(let items):
            guard !items.isEmpty else { return false }
            if type == .list {
                return items.contains {
                    if case .string(let text) = $0 {
                        return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    }
                    return false
                }
            }
            return true
        case .object(let object):
            if type == .asset {
                guard case .string(let name) = object["name"],
                      case .string(let url) = object["url"] else { return false }
                return !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    && !url.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            }
            return !object.isEmpty
        default:
            return true
        }
    }

    private func createAfterNotFound() async {
        guard scopeIsCurrent else { return }
        do {
            let response = try await apiClient.createStructuredReview(
                workflowId: workflowId,
                reviewKey: reviewKey,
                schemaId: schemaId,
                document: initialDocument
            )
            guard scopeIsCurrent else { return }
            try apply(response)
        } catch APIError.server(409, _) {
            guard scopeIsCurrent else { return }
            do {
                let response = try await apiClient.fetchStructuredReview(workflowId: workflowId, reviewKey: reviewKey)
                guard scopeIsCurrent else { return }
                try apply(response)
            } catch {
                guard scopeIsCurrent else { return }
                errorMessage = error.localizedDescription
            }
        } catch {
            guard scopeIsCurrent else { return }
            errorMessage = error.localizedDescription
        }
    }

    private func apply(_ response: APIResponse<StructuredReviewRevisionDTO>) throws {
        guard let etag = response.etag, etag.first == "\"", etag.last == "\"" else {
            throw APIError.decoding("结构化审核响应缺少带引号的 ETag")
        }
        revision = response.value
        document = response.value.document
        savedDocument = response.value.document
        self.etag = etag
        conflict = nil
        errorMessage = nil
    }
}

public struct StructuredReviewView: View {
    @StateObject private var model: StructuredReviewViewModel
    @FocusState private var focusedFieldID: String?

    @MainActor public init(
        workflowId: String,
        reviewKey: String,
        schemaId: String = "workflow.structured-review.v2",
        initialDocument: StructuredReviewDocumentDTO,
        scope: WorkflowActivityCoordinator.Scope? = nil
    ) {
        _model = StateObject(wrappedValue: StructuredReviewViewModel(
            workflowId: workflowId,
            reviewKey: reviewKey,
            schemaId: schemaId,
            initialDocument: initialDocument,
            apiClient: .shared,
            scope: scope,
            isScopeCurrent: { WorkflowActivityCoordinator.shared.isCurrent($0) }
        ))
    }

    @MainActor init(model: StructuredReviewViewModel) {
        _model = StateObject(wrappedValue: model)
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            header
            if model.isLoading && model.revision == nil {
                ProgressView("正在读取结构化审核…")
                    .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
            } else if model.revision != nil {
                Divider()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        fields
                        if let conflict = model.conflict { conflictView(conflict) }
                        if let error = model.errorMessage {
                            Label(error, systemImage: "exclamationmark.triangle.fill")
                                .font(AppTheme.Typography.supporting)
                                .foregroundStyle(AppTheme.Colors.statusError)
                                .accessibilityLabel("结构化审核错误：\(error)")
                        }
                    }
                    .padding(.vertical, AppTheme.Spacing.sm)
                }
                .scrollDismissesKeyboard(.interactively)
                .accessibilityIdentifier("structured-review-fields-scroll")
            }
            if model.revision != nil {
                Divider()
                actions
            }
        }
        .padding(AppTheme.Spacing.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(AppTheme.Colors.cardBackground)
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("完成") { focusedFieldID = nil }
            }
        }
        .task { await model.load() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack {
                Label("结构化审核", systemImage: "checklist")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.Icons.intelligence)
                    .accessibilityIdentifier("structured-review-container")
                Spacer()
                if let revision = model.revision {
                    Text("版本 \(revision.version)")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .accessibilityIdentifier("structured-review-version")
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
                .focused($focusedFieldID, equals: field.id)
                .accessibilityLabel(field.label)
                .accessibilityIdentifier("structured-review-field-\(field.id)")
        case .textarea:
            TextField(field.label, text: stringBinding(field.id), axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(3...8)
                .frame(minHeight: 96)
                .focused($focusedFieldID, equals: field.id)
                .accessibilityLabel(field.label)
                .accessibilityIdentifier("structured-review-field-\(field.id)")
        case .choice:
            Picker(field.label, selection: stringBinding(field.id)) {
                Text("请选择").tag("")
                ForEach(field.options ?? [], id: \.self) { Text($0).tag($0) }
            }
            .pickerStyle(.menu)
            .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.inputHeight, alignment: .leading)
            .accessibilityLabel(field.label)
            .accessibilityIdentifier("structured-review-field-\(field.id)")
        case .number:
            TextField(field.label, text: numberBinding(field.id))
                .keyboardType(.decimalPad)
                .textFieldStyle(.roundedBorder)
                .frame(minHeight: AppTheme.Metrics.inputHeight)
                .focused($focusedFieldID, equals: field.id)
                .accessibilityLabel(field.label)
                .accessibilityIdentifier("structured-review-field-\(field.id)")
        case .toggle:
            Toggle(field.label, isOn: boolBinding(field.id))
                .labelsHidden()
                .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget, alignment: .leading)
                .accessibilityLabel(field.label)
                .accessibilityIdentifier("structured-review-field-\(field.id)")
        case .list:
            listEditor(field)
        case .pageStructure:
            pageStructureEditor(field)
        case .asset:
            assetEditor(field)
        }
    }

    private func listEditor(_ field: StructuredReviewFieldDTO) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            ForEach(Array(arrayValue(field.id).indices), id: \.self) { index in
                HStack(spacing: AppTheme.Spacing.sm) {
                    TextField("第 \(index + 1) 项", text: arrayStringBinding(field.id, index: index))
                        .textFieldStyle(.roundedBorder)
                        .frame(minHeight: AppTheme.Metrics.inputHeight)
                        .accessibilityIdentifier("structured-review-field-\(field.id)-item-\(index)")
                    Button("删除", systemImage: "minus.circle", role: .destructive) {
                        removeArrayItem(field.id, index: index)
                    }
                    .labelStyle(.iconOnly)
                    .frame(minWidth: AppTheme.Metrics.minimumTouchTarget, minHeight: AppTheme.Metrics.minimumTouchTarget)
                    .accessibilityLabel("删除\(field.label)第 \(index + 1) 项")
                }
            }
            Button("添加一项", systemImage: "plus") {
                appendArrayItem(field.id, value: .string(""))
            }
            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            .accessibilityIdentifier("structured-review-field-\(field.id)-add")
        }
    }

    private func pageStructureEditor(_ field: StructuredReviewFieldDTO) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            ForEach(Array(arrayValue(field.id).indices), id: \.self) { index in
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    HStack {
                        Text("第 \(index + 1) 页").font(AppTheme.Typography.supporting)
                        Spacer()
                        Button("上移", systemImage: "arrow.up") { moveArrayItem(field.id, from: index, offset: -1) }
                            .labelStyle(.iconOnly)
                            .disabled(index == 0)
                        Button("下移", systemImage: "arrow.down") { moveArrayItem(field.id, from: index, offset: 1) }
                            .labelStyle(.iconOnly)
                            .disabled(index == arrayValue(field.id).count - 1)
                        Button("删除", systemImage: "trash", role: .destructive) { removeArrayItem(field.id, index: index) }
                            .labelStyle(.iconOnly)
                    }
                    .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                    TextField("页面标题", text: pageStringBinding(field.id, index: index, key: "title"))
                        .textFieldStyle(.roundedBorder)
                        .accessibilityIdentifier("structured-review-field-\(field.id)-page-\(index)-title")
                    TextField("页面摘要", text: pageStringBinding(field.id, index: index, key: "summary"), axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .lineLimit(2...5)
                        .accessibilityIdentifier("structured-review-field-\(field.id)-page-\(index)-summary")
                }
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.Colors.surfaceTint)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            }
            Button("添加页面", systemImage: "plus") {
                appendArrayItem(field.id, value: .object([
                    "id": .string("page-\(UUID().uuidString.lowercased())"),
                    "title": .string("新页面"),
                    "summary": .string(""),
                ]))
            }
            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            .accessibilityIdentifier("structured-review-field-\(field.id)-add")
        }
    }

    private func assetEditor(_ field: StructuredReviewFieldDTO) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            TextField("素材名称", text: objectStringBinding(field.id, key: "name"))
                .textFieldStyle(.roundedBorder)
                .accessibilityIdentifier("structured-review-field-\(field.id)-name")
            TextField("素材 URL", text: objectStringBinding(field.id, key: "url"))
                .textFieldStyle(.roundedBorder)
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
                .accessibilityIdentifier("structured-review-field-\(field.id)-url")
            TextField("来源 URL", text: objectStringBinding(field.id, key: "source_url"))
                .textFieldStyle(.roundedBorder)
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
                .accessibilityIdentifier("structured-review-field-\(field.id)-source-url")
            HStack(spacing: AppTheme.Spacing.md) {
                if let url = assetURL(field.id) {
                    Link("预览素材", destination: url)
                        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                        .accessibilityIdentifier("structured-review-field-\(field.id)-preview")
                }
                Button("恢复已保存素材", systemImage: "arrow.uturn.backward") {
                    focusedFieldID = nil
                    model.restoreSavedValue(fieldID: field.id)
                }
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                .accessibilityIdentifier("structured-review-field-\(field.id)-restore")
            }
            Text("替换后仍需服务端校验 MIME、哈希和许可记录。")
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textSecondary)
        }
    }

    private var actions: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Button("撤销", systemImage: "arrow.uturn.backward") {
                focusedFieldID = nil
                Task { await model.undo() }
            }
                .buttonStyle(.bordered)
                .disabled(model.isSaving || (model.revision?.version ?? 0) < 2)
                .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
            Button("保存审核", systemImage: "checkmark") {
                focusedFieldID = nil
                Task { await model.save() }
            }
                .buttonStyle(.borderedProminent)
                .disabled(model.isSaving)
                .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                .accessibilityIdentifier("structured-review-save")
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

    private func arrayValue(_ id: String) -> [JSONScalar] {
        if case .array(let value) = model.document.values[id] { return value }
        return []
    }

    private func arrayStringBinding(_ id: String, index: Int) -> Binding<String> {
        Binding(
            get: {
                let values = arrayValue(id)
                guard values.indices.contains(index), case .string(let value) = values[index] else { return "" }
                return value
            },
            set: { value in
                var values = arrayValue(id)
                guard values.indices.contains(index) else { return }
                values[index] = .string(value)
                model.document.values[id] = .array(values)
            }
        )
    }

    private func pageStringBinding(_ id: String, index: Int, key: String) -> Binding<String> {
        Binding(
            get: {
                let values = arrayValue(id)
                guard values.indices.contains(index),
                      case .object(let page) = values[index],
                      case .string(let value) = page[key] else { return "" }
                return value
            },
            set: { value in
                var values = arrayValue(id)
                guard values.indices.contains(index), case .object(var page) = values[index] else { return }
                page[key] = .string(value)
                values[index] = .object(page)
                model.document.values[id] = .array(values)
            }
        )
    }

    private func objectStringValue(_ id: String, key: String) -> String {
        guard case .object(let object) = model.document.values[id],
              case .string(let value) = object[key] else { return "" }
        return value
    }

    private func assetURL(_ id: String) -> URL? {
        guard let url = URL(string: objectStringValue(id, key: "url")),
              let scheme = url.scheme?.lowercased(),
              scheme == "https" || scheme == "http" else { return nil }
        return url
    }

    private func objectStringBinding(_ id: String, key: String) -> Binding<String> {
        Binding(
            get: {
                objectStringValue(id, key: key)
            },
            set: { value in
                var object: [String: JSONScalar]
                if case .object(let current) = model.document.values[id] {
                    object = current
                } else {
                    object = ["id": .string("asset-\(UUID().uuidString.lowercased())")]
                }
                object[key] = .string(value)
                model.document.values[id] = .object(object)
            }
        )
    }

    private func appendArrayItem(_ id: String, value: JSONScalar) {
        var values = arrayValue(id)
        values.append(value)
        model.document.values[id] = .array(values)
    }

    private func removeArrayItem(_ id: String, index: Int) {
        var values = arrayValue(id)
        guard values.indices.contains(index) else { return }
        values.remove(at: index)
        model.document.values[id] = .array(values)
    }

    private func moveArrayItem(_ id: String, from index: Int, offset: Int) {
        var values = arrayValue(id)
        let destination = index + offset
        guard values.indices.contains(index), values.indices.contains(destination) else { return }
        values.swapAt(index, destination)
        model.document.values[id] = .array(values)
    }

    private func display(_ value: JSONScalar?) -> String {
        switch value {
        case .string(let value): return value
        case .integer(let value): return value.formatted()
        case .number(let value): return value.formatted()
        case .bool(let value): return value ? "是" : "否"
        case .array(let value): return "\(value.count) 项"
        case .object(let value):
            if case .string(let name) = value["name"] { return name }
            return "\(value.count) 个字段"
        case .null, nil: return "未填写"
        }
    }
}
