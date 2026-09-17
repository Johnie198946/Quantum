import SwiftUI
import Combine
import OSLog
import PDFKit

// MARK: - 工作流主页

public struct WorkflowDashboardView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator
    @StateObject private var model = WorkflowDashboardModel()
    @State private var showingCreate = false
    @State private var showingTopology = false
    @State private var clarificationWorkflow: WorkflowDTO?
    @State private var navigationPath: [WorkflowDTO] = []
    @State private var pendingDeletion: WorkflowDTO?

    public init() {}

    public var body: some View {
        NavigationStack(path: $navigationPath) {
            ZStack {
                QuantumWorkflowBackground()

                Group {
                    if model.isLoading && model.workflows.isEmpty {
                        ProgressView("正在读取工作流…")
                    } else if model.workflows.isEmpty {
                        emptyState
                    } else {
                        ScrollView {
                            LazyVStack(spacing: AppTheme.Spacing.lg) {
                                ForEach(model.workflows) { workflow in
                                    NavigationLink(value: workflow) {
                                        WorkflowSummaryCard(workflow: workflow)
                                    }
                                    .buttonStyle(SoftButtonStyle())
                                    .accessibilityIdentifier("workflow-card-\(workflow.title)")
                                    .accessibilityHint("轻点查看详情，长按可删除任务")
                                    .contextMenu {
                                        Button(role: .destructive) {
                                            pendingDeletion = workflow
                                        } label: {
                                            Label("删除任务", systemImage: "trash")
                                        }
                                    }
                                }
                            }
                            .padding(AppTheme.Metrics.contentGutter)
                        }
                        .refreshable { await load() }
                    }
                }
            }
            .navigationTitle("任务")
            .navigationDestination(for: WorkflowDTO.self) { workflow in
                if let scope = workflowActivities.scope(for: workflow) {
                    WorkflowDetailView(workflow: workflow, scope: scope) {
                        await load()
                    }
                } else {
                    WorkflowErrorBanner(message: "此工作流不属于当前对话会话。")
                        .padding()
                }
            }
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button("协同拓扑", systemImage: "point.3.connected.trianglepath.dotted") {
                        showingTopology = true
                    }
                    .accessibilityHint("查看 Agent、工具与知识依赖")
                    Button("创建工作流", systemImage: "plus") {
                        showingCreate = true
                    }
                }
            }
            .overlay(alignment: .top) {
                if let error = model.errorMessage ?? appState.pendingWorkflowScopeError {
                    WorkflowErrorBanner(message: error)
                        .padding(.top, AppTheme.Spacing.sm)
                }
            }
            .sheet(isPresented: $showingCreate) {
                WorkflowCreateSheet { created in
                    showingCreate = false
                    clarificationWorkflow = created.workflow
                    await load()
                }
            }
            .fullScreenCover(item: $clarificationWorkflow) { workflow in
                NavigationStack {
                    WorkflowClarificationView(workflow: workflow) {
                        clarificationWorkflow = nil
                        await load()
                    }
                }
            }
            .sheet(isPresented: $showingTopology) {
                NavigationStack { TopologyCanvasView() }
            }
            .confirmationDialog(
                "删除任务？",
                isPresented: Binding(
                    get: { pendingDeletion != nil },
                    set: { if !$0 { pendingDeletion = nil } }
                ),
                titleVisibility: .visible
            ) {
                if let workflow = pendingDeletion {
                    Button("删除“\(workflow.title)”", role: .destructive) {
                        pendingDeletion = nil
                        Task {
                            guard let scope = workflowActivities.scope(for: workflow) else {
                                model.rejectMissingScope()
                                return
                            }
                            await model.delete(workflow, scope: scope)
                        }
                    }
                }
                Button("取消", role: .cancel) { pendingDeletion = nil }
            } message: {
                Text("任务将从列表中移除，正在执行的工作也会停止。")
            }
            .task(id: workflowActivities.currentScope) { await load() }
            .onChange(of: workflowActivities.currentScope) { _, _ in
                navigationPath.removeAll()
                clarificationWorkflow = nil
                pendingDeletion = nil
                showingCreate = false
                model.clearForScopeChange()
            }
            .task(id: appState.pendingWorkflowId) {
                guard appState.pendingWorkflowId != nil else { return }
                if let workflow = await appState.resolvePendingWorkflow(using: { workflowId in
                    if let tracked = workflowActivities.workflows[workflowId] {
                        return tracked
                    }
                    return try await APIClient.shared.fetchWorkflow(id: workflowId)
                }) {
                    navigationPath = [workflow]
                }
            }
        }
    }

    private func load() async {
        guard let scope = workflowActivities.currentScope else {
            model.rejectMissingScope()
            return
        }
        await model.load(scope: scope)
    }

    private var emptyState: some View {
        VStack(spacing: AppTheme.Spacing.xl) {
            Image(systemName: "sparkles.rectangle.stack.fill")
                .font(.system(size: 28, weight: .semibold))
                .foregroundStyle(AppTheme.Colors.quantumGradient)
                .frame(width: 64, height: 64)
                .background(AppTheme.Colors.selectionTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))

            VStack(spacing: AppTheme.Spacing.sm) {
                Text("把想法变成工作流")
                    .font(AppTheme.Typography.screenTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text("描述你想获得的结果。Quantum 会先澄清需求并生成可编辑方案，确认后构建专属 Agent，由你再次点击启动。")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .multilineTextAlignment(.center)
            }

            Button("创建第一个工作流", systemImage: "plus") { showingCreate = true }
                .buttonStyle(.borderedProminent)
                .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                .controlSize(.large)
        }
        .padding(AppTheme.Spacing.xxl)
        .frame(maxWidth: 340)
        .background(.ultraThinMaterial)
        .background(AppTheme.Colors.cardBackground.opacity(0.82))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.9), lineWidth: 0.75)
        }
        .padding(AppTheme.Metrics.contentGutter)
    }
}

private struct QuantumWorkflowBackground: View {
    var body: some View {
        ZStack {
            AppTheme.Colors.background
            Circle()
                .fill(AppTheme.Colors.quantumBlue.opacity(0.11))
                .frame(width: 330, height: 330)
                .blur(radius: 70)
                .offset(x: 150, y: -280)
            Circle()
                .fill(AppTheme.Colors.primary.opacity(0.10))
                .frame(width: 300, height: 300)
                .blur(radius: 80)
                .offset(x: -150, y: 250)
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }
}

@MainActor
private final class WorkflowDashboardModel: ObservableObject {
    @Published var workflows: [WorkflowDTO] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    func load(scope: WorkflowActivityCoordinator.Scope) async {
        isLoading = true
        defer {
            if WorkflowActivityCoordinator.shared.isCurrent(scope) { isLoading = false }
        }
        do {
            let loaded = try await APIClient.shared.fetchWorkflows()
            guard WorkflowActivityCoordinator.shared.isCurrent(scope) else { return }
            workflows = loaded.filter { WorkflowActivityCoordinator.shared.accepts($0, in: scope) }
            errorMessage = nil
        } catch {
            guard WorkflowActivityCoordinator.shared.isCurrent(scope) else { return }
            errorMessage = error.localizedDescription
        }
    }

    func delete(_ workflow: WorkflowDTO, scope: WorkflowActivityCoordinator.Scope) async {
        do {
            try await APIClient.shared.deleteWorkflow(id: workflow.id)
            guard WorkflowActivityCoordinator.shared.isCurrent(scope) else { return }
            workflows.removeAll { $0.id == workflow.id }
            errorMessage = nil
        } catch {
            guard WorkflowActivityCoordinator.shared.isCurrent(scope) else { return }
            errorMessage = "删除失败：\(error.localizedDescription)"
        }
    }

    func rejectMissingScope() {
        workflows.removeAll()
        isLoading = false
        errorMessage = "当前对话会话不可用，请先选择或新建对话。"
    }

    func clearForScopeChange() {
        workflows.removeAll()
        isLoading = false
        errorMessage = nil
    }
}

private struct WorkflowSummaryCard: View {
    let workflow: WorkflowDTO
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text(workflow.title)
                        .font(AppTheme.Typography.screenTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .multilineTextAlignment(.leading)
                    Text(workflow.description)
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                }
                Spacer(minLength: AppTheme.Spacing.sm)
                WorkflowStatusBadge(status: workflow.latestExecution?.status ?? workflow.status)
            }

            ProgressView(value: Double(workflow.latestExecution?.progress ?? planningProgress))
                .tint(AppTheme.Colors.quantumBlue)

            if let agent = workflow.agent {
                HStack(spacing: AppTheme.Spacing.md) {
                    Image(systemName: "person.crop.circle.badge.checkmark")
                        .foregroundStyle(AppTheme.Colors.quantumBlue)
                        .frame(width: 36, height: 36)
                        .background(AppTheme.Colors.surfaceTint, in: Circle())
                    VStack(alignment: .leading, spacing: 2) {
                        Text(agent.customName ?? "任务专用 Agent")
                            .font(AppTheme.Typography.cardTitle)
                        Text(agent.compositionManifest.capabilityAgentIds.map(\.workflowCapabilityLabel).joined(separator: " · "))
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(2)
                    }
                    Spacer(minLength: 0)
                }
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.Colors.surfaceTint)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            }

            HStack {
                Label(workflow.desiredOutput, systemImage: "doc.richtext")
                    .lineLimit(1)
                Spacer()
                Image(systemName: "chevron.right")
            }
            .font(AppTheme.Typography.label)
            .foregroundStyle(AppTheme.Colors.textSecondary)
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.xl)
                .stroke(AppTheme.Colors.border, lineWidth: 1)
        }
        .pressBorderGlow(cornerRadius: AppTheme.Radius.xl)
        .cardShadow(colorScheme: colorScheme)
        .accessibilityElement(children: .combine)
    }

    private var planningProgress: Int {
        switch workflow.status {
        case "clarifying": return 5
        case "planning", "needs_attention": return 10
        case "awaiting_approval": return 15
        case "building_agent": return 18
        case "agent_ready", "ready": return 20
        default: return 0
        }
    }
}

// MARK: - 创建

private struct WorkflowCreateSheet: View {
    let onCreated: (WorkflowCreateResponseDTO) async -> Void
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator
    @State private var title = ""
    @State private var description = ""
    @State private var output = "研究报告（Markdown）"
    @State private var outputKind = "general"
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("工作流") {
                    TextField("名称，例如：拜仁洞察", text: $title)
                        .textInputAutocapitalization(.never)
                    TextField("详细描述目标、范围和你希望看到的结果", text: $description, axis: .vertical)
                        .lineLimit(5...10)
                }
                Section("交付物") {
                    Picker("类型", selection: $outputKind) {
                        Text("通用").tag("general")
                        Text("演示文稿 PPTX").tag("presentation")
                        Text("Word 文档 DOCX").tag("document")
                    }
                    TextField("例如：带引用的 Markdown 研究报告", text: $output)
                }
                Section {
                    Label("创建后先通过独立会话澄清需求；确认方案前不会执行任务。", systemImage: "lock.shield")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                if let errorMessage {
                    Section { Text(errorMessage).foregroundStyle(AppTheme.Colors.statusError) }
                }
            }
            .navigationTitle("创建工作流")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                        .disabled(isSubmitting)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(isSubmitting ? "建档中…" : "开始澄清") { submit() }
                        .disabled(title.trimmingCharacters(in: .whitespaces).isEmpty || description.count < 3 || isSubmitting)
                }
            }
            .interactiveDismissDisabled(isSubmitting)
        }
    }

    private func submit() {
        guard let scope = workflowActivities.currentScope else {
            errorMessage = "当前对话会话不可用，请先选择或新建对话。"
            return
        }
        isSubmitting = true
        errorMessage = nil
        Task {
            do {
                let deliverable = outputKind == "presentation"
                    ? "可编辑 PPTX 与渲染预览"
                    : outputKind == "document" ? "可编辑 Word 文档 DOCX" : output
                let created = try await APIClient.shared.createWorkflow(
                    title: title, description: description, desiredOutput: deliverable,
                    outputKind: outputKind,
                    sourceClientSessionId: scope.clientSessionId
                )
                guard workflowActivities.isCurrent(scope),
                      workflowActivities.accepts(created.workflow, in: scope) else { return }
                await onCreated(created)
            } catch {
                guard workflowActivities.isCurrent(scope) else { return }
                errorMessage = error.localizedDescription
                isSubmitting = false
            }
        }
    }
}

// MARK: - 详情与计划确认

enum WorkflowDetailTransitionPolicy {
    static func showsLifecycleSession(status: String, hasExecution: Bool) -> Bool {
        !hasExecution && ["clarifying", "planning", "building_agent"].contains(status)
    }

    static func accepts(remoteStatus: String, over currentStatus: String) -> Bool {
        !(currentStatus == "agent_ready" && remoteStatus == "building_agent")
    }
}

struct WorkflowFailurePresentation: Equatable {
    let cause: String
    let action: String

    static func make(execution: WorkflowExecutionDTO) -> Self? {
        guard ["failed", "cancelled"].contains(execution.status) else { return nil }
        let reported = execution.errorMessage?.trimmingCharacters(in: .whitespacesAndNewlines)
        let nodeReported = execution.nodes.compactMap(\.errorMessage).first?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let cause = [reported, nodeReported].compactMap { value in
            value?.isEmpty == false ? value : nil
        }.first ?? (execution.status == "cancelled"
            ? "任务已由用户取消，已完成步骤仍保留。"
            : "服务端未返回具体错误，可重新读取状态后重试。")
        return Self(cause: cause, action: "从失败步骤继续同一任务")
    }
}

private struct WorkflowDetailView: View {
    let workflow: WorkflowDTO
    let scope: WorkflowActivityCoordinator.Scope
    let onChanged: () async -> Void
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator
    @State private var current: WorkflowDTO
    @State private var execution: WorkflowExecutionDTO?

    init(
        workflow: WorkflowDTO,
        scope: WorkflowActivityCoordinator.Scope,
        onChanged: @escaping () async -> Void
    ) {
        self.workflow = workflow
        self.scope = scope
        self.onChanged = onChanged
        _current = State(initialValue: workflow)
        _execution = State(initialValue: workflow.latestExecution)
    }

    var body: some View {
        Group {
            if !workflowActivities.isCurrent(scope) {
                WorkflowErrorBanner(message: "对话会话已切换，此工作流页面已停止更新。")
                    .padding()
            } else if WorkflowDetailTransitionPolicy.showsLifecycleSession(
                status: current.status,
                hasExecution: execution != nil
            ) {
                WorkflowClarificationView(workflow: current) {
                    await refresh()
                    guard workflowActivities.isCurrent(scope) else { return }
                    await onChanged()
                }
            } else if current.status == "awaiting_approval" && execution == nil {
                WorkflowPlanReviewView(workflow: current, scope: scope) { buildResult in
                    current = buildResult.workflow
                    Task {
                        await refresh()
                        guard workflowActivities.isCurrent(scope) else { return }
                        await onChanged()
                    }
                }
            } else if current.status == "agent_ready", let agent = current.agent, execution == nil {
                WorkflowAgentReadyView(workflow: current, agent: agent, scope: scope) { started in
                    execution = started
                    Task { await onChanged() }
                }
            } else if let execution {
                WorkflowExecutionView(workflow: current, initialExecution: execution, scope: scope)
            } else {
                ProgressView("正在恢复工作流状态…")
            }
        }
        .navigationTitle(current.title)
        .navigationBarTitleDisplayMode(.inline)
        .task { await refresh() }
    }

    private func refresh() async {
        guard workflowActivities.isCurrent(scope) else { return }
        do {
            let remote = try await APIClient.shared.fetchWorkflow(id: workflow.id)
            guard workflowActivities.accepts(remote, in: scope),
                  WorkflowDetailTransitionPolicy.accepts(
                remoteStatus: remote.status,
                over: current.status
            ) else { return }
            current = remote
            if let remoteExecution = remote.latestExecution {
                execution = remoteExecution
            }
        } catch { }
    }
}

// MARK: - 任务内需求澄清

@MainActor
public final class WorkflowClarificationModel: ObservableObject {
    let workflowId: String
    @Published var snapshot: WorkflowClarificationSnapshotDTO?
    @Published var events: [WorkflowLifecycleEventDTO] = []
    @Published var isLoading = false
    @Published var isSubmitting = false
    @Published var errorMessage: String?
    @Published var connectionState: String = "idle"
    @Published var optimisticPlanningMessage: String?
    private var streamActive = false
    private var streamTask: Task<Void, Never>?
    private let scope: WorkflowActivityCoordinator.Scope?
    private let isScopeCurrent: (WorkflowActivityCoordinator.Scope) -> Bool

    init(
        workflowId: String,
        scope: WorkflowActivityCoordinator.Scope?,
        isScopeCurrent: @escaping (WorkflowActivityCoordinator.Scope) -> Bool
    ) {
        self.workflowId = workflowId
        self.scope = scope
        self.isScopeCurrent = isScopeCurrent
        if scope == nil { errorMessage = "此工作流不属于当前对话会话。" }
    }

    private var scopeIsCurrent: Bool {
        guard let scope else { return false }
        return isScopeCurrent(scope)
    }

    func startTracking() {
        guard scopeIsCurrent, streamTask == nil else { return }
        streamTask = Task { [weak self] in
            await self?.start()
            guard let self, self.scopeIsCurrent else { return }
            self.streamTask = nil
        }
    }

    func stopTracking() {
        streamTask?.cancel()
        streamTask = nil
        streamActive = false
        connectionState = "paused"
    }

    var phase: String { snapshot?.session.phase ?? "clarifying" }
    var lastEventId: Int { events.map(\.id).max() ?? 0 }

    func start() async {
        guard scopeIsCurrent, !streamActive else { return }
        streamActive = true
        connectionState = "connecting"
        defer {
            if scopeIsCurrent { streamActive = false }
        }
        await refresh()
        guard scopeIsCurrent, !Task.isCancelled,
              !["awaiting_approval", "agent_ready", "needs_attention"].contains(phase) else { return }
        var retries = 0
        while !Task.isCancelled {
            do {
                connectionState = "connected"
                for try await event in APIClient.shared.workflowLifecycleEventStream(
                    workflowId: workflowId, after: lastEventId
                ) {
                    guard scopeIsCurrent, !Task.isCancelled else { return }
                    retries = 0
                    if !events.contains(where: { $0.id == event.id }) { events.append(event) }
                    optimisticPlanningMessage = nil
                    if ["plan_ready", "agent_built", "planning_failed"].contains(event.type) {
                        await refresh()
                        guard scopeIsCurrent else { return }
                    }
                }
                guard scopeIsCurrent else { return }
                connectionState = "idle"
                return
            } catch is CancellationError {
                return
            } catch {
                guard scopeIsCurrent else { return }
                retries += 1
                connectionState = "reconnecting"
                errorMessage = "进度连接已中断，正在恢复同一任务…"
                let delay = UInt64(min(retries, 8)) * 1_000_000_000
                try? await Task.sleep(nanoseconds: delay)
                guard scopeIsCurrent else { return }
                await refresh()
            }
        }
    }

    func refresh() async {
        guard scopeIsCurrent else { return }
        isLoading = snapshot == nil
        defer {
            if scopeIsCurrent { isLoading = false }
        }
        do {
            let loaded = try await APIClient.shared.fetchWorkflowClarification(workflowId: workflowId)
            guard scopeIsCurrent else { return }
            snapshot = loaded
            events = loaded.events
            errorMessage = nil
            if ["awaiting_approval", "agent_ready"].contains(loaded.session.phase) {
                connectionState = "idle"
            }
        } catch {
            guard scopeIsCurrent else { return }
            errorMessage = "无法恢复任务会话：\(error.localizedDescription)"
        }
    }

    func respond(_ response: String) async {
        guard scopeIsCurrent,
              !response.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        isSubmitting = true
        if response.hasPrefix("确认") || response.contains("进入方案") {
            optimisticPlanningMessage = "规划请求已提交到云端，离开此页不会中断"
        }
        defer {
            if scopeIsCurrent { isSubmitting = false }
        }
        do {
            _ = try await APIClient.shared.respondToWorkflowClarification(
                workflowId: workflowId, response: response
            )
            guard scopeIsCurrent else { return }
            await refresh()
            guard scopeIsCurrent else { return }
            if phase == "planning" {
                startTracking()
            }
        } catch {
            guard scopeIsCurrent else { return }
            optimisticPlanningMessage = nil
            errorMessage = "提交失败，需求进度已保留：\(error.localizedDescription)"
        }
    }

    func retryPlanning() async {
        guard scopeIsCurrent else { return }
        isSubmitting = true
        defer {
            if scopeIsCurrent { isSubmitting = false }
        }
        do {
            _ = try await APIClient.shared.retryWorkflowPlanning(workflowId: workflowId)
            guard scopeIsCurrent else { return }
            await refresh()
            guard scopeIsCurrent else { return }
            startTracking()
        } catch {
            guard scopeIsCurrent else { return }
            errorMessage = "规划重试失败，已有内容不会丢失：\(error.localizedDescription)"
        }
    }

    func reopenClarification() async {
        guard scopeIsCurrent else { return }
        isSubmitting = true
        defer {
            if scopeIsCurrent { isSubmitting = false }
        }
        do {
            _ = try await APIClient.shared.reopenWorkflowClarification(workflowId: workflowId)
            guard scopeIsCurrent else { return }
            await refresh()
        } catch {
            guard scopeIsCurrent else { return }
            errorMessage = "无法继续澄清：\(error.localizedDescription)"
        }
    }

    var reasoningSteps: [ReasoningStep] {
        events.filter {
            ["planning_queued", "planning_retry_scheduled", "planning_started", "planning_worker_claimed", "planner_context_loaded", "capabilities_selecting", "planner_step", "plan_compiling", "plan_compiled", "policy_validated", "plan_ready", "planning_failed", "agent_built"].contains($0.type)
        }.map { event in
            let type: ReasoningStepType
            switch event.payload.category ?? event.type {
            case "skill_load", "planner_context_loaded": type = .skillLoad
            case "agent_spawn", "capabilities_selecting", "agent_built": type = .agentSpawn
            case "tool_call", "plan_compiling", "plan_compiled", "policy_validated": type = .toolCall
            default: type = .thought
            }
            let running = event.id == lastEventId && ["planning", "building_agent"].contains(phase)
            return ReasoningStep(
                id: "workflow-event-\(event.id)", type: type,
                title: event.message,
                detail: event.payload.detail ?? event.payload.tool ?? "",
                status: event.payload.status ?? (event.type == "planning_failed" ? "failed" : (running ? "running" : "done"))
            )
        }
    }
}

@MainActor
public final class WorkflowActivityCoordinator: ObservableObject {
    public static let shared = WorkflowActivityCoordinator()
    private static let scopeLogger = Logger(
        subsystem: "com.quantumn.aiplatform",
        category: "workflow-scope"
    )

    public struct Scope: Hashable, Sendable {
        public let ownerIdentity: String
        public let clientSessionId: String
        public let generation: UInt64
    }

    @Published public private(set) var workflows: [String: WorkflowDTO] = [:]
    @Published public private(set) var dismissedWorkflowIds: Set<String> = []
    @Published public private(set) var executions: [String: WorkflowExecutionDTO] = [:]

    private var models: [String: WorkflowClarificationModel] = [:]
    private var subscriptions: [String: AnyCancellable] = [:]
    private var publishScheduled = false
    private var executionWorkflows: [String: WorkflowDTO] = [:]
    private var executionTasks: [String: Task<Void, Never>] = [:]
    private var activeOwnerScope: String?
    private var activeClientSessionId: String?
    private var generation: UInt64 = 0

    public var currentScope: Scope? {
        guard let ownerIdentity = activeOwnerScope,
              let clientSessionId = activeClientSessionId else { return nil }
        return Scope(
            ownerIdentity: ownerIdentity,
            clientSessionId: clientSessionId,
            generation: generation
        )
    }

    public func isCurrent(_ scope: Scope) -> Bool {
        let matches = currentScope == scope
        if !matches {
            Self.scopeLogger.notice(
                "Dropped stale workflow state write for generation \(scope.generation, privacy: .public)"
            )
        }
        return matches
    }

    public func accepts(_ workflow: WorkflowDTO, in scope: Scope) -> Bool {
        isCurrent(scope) && workflow.sourceClientSessionId == scope.clientSessionId
    }

    public func scope(for workflow: WorkflowDTO) -> Scope? {
        guard let scope = currentScope, accepts(workflow, in: scope) else { return nil }
        return scope
    }

    public func activate(tenantKey: String, userId: String) {
        let scope = tenantKey + "\u{0}" + userId
        guard activeOwnerScope != scope else { return }
        advanceGenerationAndClear()
        activeOwnerScope = scope
        activeClientSessionId = nil
    }

    public func deactivate() {
        guard activeOwnerScope != nil || activeClientSessionId != nil else { return }
        advanceGenerationAndClear()
        activeOwnerScope = nil
        activeClientSessionId = nil
    }

    public func selectClientSession(_ sessionId: String?) {
        let sessionId = sessionId.flatMap { $0.isEmpty ? nil : $0 }
        guard activeClientSessionId != sessionId else { return }
        advanceGenerationAndClear()
        activeClientSessionId = sessionId
        objectWillChange.send()
    }

    private func advanceGenerationAndClear() {
        generation += 1
        clearTrackedState()
    }

    private func clearTrackedState() {
        for model in models.values { model.stopTracking() }
        for task in executionTasks.values { task.cancel() }
        workflows.removeAll()
        dismissedWorkflowIds.removeAll()
        executions.removeAll()
        models.removeAll()
        subscriptions.removeAll()
        executionWorkflows.removeAll()
        executionTasks.removeAll()
        publishScheduled = false
    }

    public struct Activity {
        public let workflow: WorkflowDTO
        public let model: WorkflowClarificationModel
    }

    public var visibleActivities: [Activity] {
        workflows.values.compactMap { workflow in
            guard !dismissedWorkflowIds.contains(workflow.id),
                  let activeClientSessionId,
                  workflow.sourceClientSessionId == activeClientSessionId,
                  let model = models[workflow.id],
                  ["clarifying", "clarifying_pending", "planning", "building_agent", "awaiting_approval", "needs_attention"].contains(model.phase)
            else { return nil }
            return Activity(workflow: workflow, model: model)
        }
        .sorted { ($0.workflow.updatedAt ?? "") > ($1.workflow.updatedAt ?? "") }
    }

    public var primaryActivity: Activity? { visibleActivities.first }

    public struct ExecutionActivity {
        public let workflow: WorkflowDTO
        public let execution: WorkflowExecutionDTO
    }

    public var visibleExecutionActivities: [ExecutionActivity] {
        executions.values.compactMap { execution in
            guard !dismissedWorkflowIds.contains(execution.workflowId),
                  let workflow = executionWorkflows[execution.workflowId],
                  let activeClientSessionId,
                  workflow.sourceClientSessionId == activeClientSessionId,
                  ["queued", "running", "awaiting_approval", "awaiting_review", "failed"].contains(execution.status)
            else { return nil }
            return ExecutionActivity(workflow: workflow, execution: execution)
        }
        .sorted { ($0.execution.createdAt ?? "") > ($1.execution.createdAt ?? "") }
    }

    public var primaryExecutionActivity: ExecutionActivity? { visibleExecutionActivities.first }

    public func model(for workflow: WorkflowDTO) -> WorkflowClarificationModel {
        if let existing = models[workflow.id] { return existing }
        let scope = scope(for: workflow)
        let model = WorkflowClarificationModel(
            workflowId: workflow.id,
            scope: scope,
            isScopeCurrent: { [weak self] token in self?.isCurrent(token) == true }
        )
        guard let scope else { return model }
        models[workflow.id] = model
        subscriptions[workflow.id] = model.objectWillChange.sink { [weak self, weak model] _ in
            DispatchQueue.main.async { [weak self, weak model] in
                guard let self, let model, self.isCurrent(scope) else { return }
                UserDefaults.standard.set(model.lastEventId, forKey: "workflow.cursor.\(workflow.id)")
                self.schedulePublish(scope: scope)
            }
        }
        return model
    }

    public func track(_ workflow: WorkflowDTO) {
        guard let scope = currentScope else { return }
        track(workflow, in: scope)
    }

    func track(_ workflow: WorkflowDTO, in scope: Scope) {
        guard accepts(workflow, in: scope) else { return }
        if workflows[workflow.id] != workflow { workflows[workflow.id] = workflow }
        if dismissedWorkflowIds.contains(workflow.id) { dismissedWorkflowIds.remove(workflow.id) }
        model(for: workflow).startTracking()
    }

    public func trackExecution(_ execution: WorkflowExecutionDTO, workflow: WorkflowDTO) {
        guard let scope = currentScope else { return }
        trackExecution(execution, workflow: workflow, in: scope)
    }

    private func trackExecution(
        _ execution: WorkflowExecutionDTO,
        workflow: WorkflowDTO,
        in scope: Scope
    ) {
        guard accepts(workflow, in: scope) else { return }
        executionWorkflows[workflow.id] = workflow
        if executions[execution.id] != execution { executions[execution.id] = execution }
        if dismissedWorkflowIds.contains(workflow.id) { dismissedWorkflowIds.remove(workflow.id) }
        guard !["awaiting_approval", "awaiting_review", "completed", "failed", "cancelled"].contains(execution.status),
              executionTasks[execution.id] == nil else { return }
        executionTasks[execution.id] = Task { [weak self] in
            guard let self else { return }
            defer {
                if self.isCurrent(scope) { self.executionTasks[execution.id] = nil }
            }
            while !Task.isCancelled {
                do {
                    let snapshot = try await APIClient.shared.fetchWorkflowExecution(id: execution.id)
                    guard self.isCurrent(scope), !Task.isCancelled else { return }
                    if self.executions[snapshot.id] != snapshot { self.executions[snapshot.id] = snapshot }
                    if ["awaiting_approval", "awaiting_review", "completed", "failed", "cancelled"].contains(snapshot.status) { return }
                } catch {
                    // The cloud run is authoritative; foreground/bootstrap will retry.
                }
                try? await Task.sleep(for: .seconds(2))
            }
        }
    }

    private func schedulePublish(scope: Scope) {
        guard isCurrent(scope), !publishScheduled else { return }
        publishScheduled = true
        DispatchQueue.main.async { [weak self] in
            guard let self, self.isCurrent(scope) else { return }
            self.publishScheduled = false
            self.objectWillChange.send()
        }
    }

    public func bootstrap() async {
        guard let scope = currentScope else { return }
        do {
            async let activitiesRequest = APIClient.shared.fetchActiveWorkflowActivities(
                clientSessionId: scope.clientSessionId
            )
            async let executionsRequest = APIClient.shared.fetchActiveWorkflowExecutions(
                clientSessionId: scope.clientSessionId
            )
            let (activities, active) = try await (activitiesRequest, executionsRequest)
            guard isCurrent(scope) else { return }
            let authoritativeWorkflowIds = Set(
                activities.map(\.workflow.id) + active.map(\.workflow.id)
            )
            let authoritativeExecutionIds = Set(active.map(\.execution.id))
            for workflowId in Array(workflows.keys) where !authoritativeWorkflowIds.contains(workflowId) {
                models[workflowId]?.stopTracking()
                models.removeValue(forKey: workflowId)
                workflows.removeValue(forKey: workflowId)
                dismissedWorkflowIds.remove(workflowId)
            }
            for executionId in Array(executions.keys) where !authoritativeExecutionIds.contains(executionId) {
                executionTasks[executionId]?.cancel()
                executionTasks.removeValue(forKey: executionId)
                if let execution = executions[executionId] {
                    executionWorkflows.removeValue(forKey: execution.workflowId)
                }
                executions.removeValue(forKey: executionId)
            }
            for activity in activities {
                track(activity.workflow, in: scope)
            }
            for item in active {
                trackExecution(item.execution, workflow: item.workflow, in: scope)
            }
        } catch {
            guard isCurrent(scope) else { return }
            // Existing models retain their last durable snapshot while offline.
            schedulePublish(scope: scope)
        }
    }

    public func pauseForBackground() {
        for model in models.values { model.stopTracking() }
        for task in executionTasks.values { task.cancel() }
        executionTasks.removeAll()
    }

    public func resumeFromForeground() async {
        guard let scope = currentScope else { return }
        await bootstrap()
        guard isCurrent(scope) else { return }
        for activity in visibleActivities { activity.model.startTracking() }
        for activity in visibleExecutionActivities {
            trackExecution(activity.execution, workflow: activity.workflow)
        }
    }

    public func dismiss(_ workflowId: String) {
        dismissedWorkflowIds.insert(workflowId)
    }
}

private struct WorkflowClarificationView: View {
    let workflow: WorkflowDTO
    let onFinished: () async -> Void
    @ObservedObject private var model: WorkflowClarificationModel

    init(workflow: WorkflowDTO, onFinished: @escaping () async -> Void) {
        self.workflow = workflow
        self.onFinished = onFinished
        _model = ObservedObject(
            wrappedValue: WorkflowActivityCoordinator.shared.model(for: workflow)
        )
    }

    var body: some View {
        VStack(spacing: 0) {
            WorkflowTaskStageHeader(phase: model.phase)
                .padding(.horizontal, AppTheme.Metrics.contentGutter)
                .padding(.vertical, AppTheme.Spacing.md)

            Divider()

            if model.isLoading {
                Spacer()
                ProgressView("正在恢复需求会话…")
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                        if !model.reasoningSteps.isEmpty || model.optimisticPlanningMessage != nil {
                            if let optimistic = model.optimisticPlanningMessage,
                               model.reasoningSteps.isEmpty {
                                WorkflowPlanningPendingCard(message: optimistic)
                            }
                            ReasoningCard(
                                steps: model.reasoningSteps,
                                isStreaming: ["planning", "building_agent"].contains(model.phase),
                                initiallyExpanded: false
                            )
                        }
                        ForEach(model.snapshot?.messages ?? []) { message in
                            workflowMessage(message)
                        }
                        if let error = model.errorMessage {
                            WorkflowErrorBanner(message: error)
                            if model.phase != "needs_attention" {
                                Button("重新连接", systemImage: "arrow.clockwise") {
                                    Task {
                                        await model.refresh()
                                        model.startTracking()
                                    }
                                }
                                .buttonStyle(.bordered)
                                .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                                .frame(minHeight: 44)
                            }
                        }
                        if model.phase == "needs_attention" {
                            if model.errorMessage == nil {
                                WorkflowErrorBanner(message: "方案生成未完成，已保留需求与过程记录。")
                            }
                            HStack(spacing: AppTheme.Spacing.md) {
                                Button("继续澄清", systemImage: "bubble.left.and.text.bubble.right") {
                                    Task { await model.reopenClarification() }
                                }
                                .buttonStyle(.bordered)
                                .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                                Button("重试规划", systemImage: "arrow.clockwise") {
                                    Task { await model.retryPlanning() }
                                }
                                .buttonStyle(.borderedProminent)
                                .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                            }
                            .frame(minHeight: 44)
                            .disabled(model.isSubmitting)
                        }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                }
                .scrollDismissesKeyboard(.interactively)
            }
        }
        .background(AppTheme.Colors.background)
        .navigationTitle(workflow.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button("返回任务") { Task { await onFinished() } }
            }
        }
        .safeAreaInset(edge: .bottom) {
            if ["awaiting_approval", "agent_ready"].contains(model.phase) {
                Button(model.phase == "agent_ready" ? "查看专属 Agent" : "查看并确认方案") {
                    Task { await onFinished() }
                }
                .buttonStyle(.borderedProminent)
                .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                .controlSize(.large)
                .frame(maxWidth: .infinity, minHeight: 44)
                .padding(AppTheme.Metrics.contentGutter)
                .background(.ultraThinMaterial)
            }
        }
        .task { WorkflowActivityCoordinator.shared.track(workflow) }
    }

    @ViewBuilder
    private func workflowMessage(_ message: WorkflowSessionMessageDTO) -> some View {
        let isLast = message.id == model.snapshot?.messages.last?.id
        if message.role == "assistant",
           isLast,
           ["clarify", "requirement_confirmation"].contains(message.messageType),
           let question = message.payload.question {
            let block = ClarifyBlock(
                question: question,
                choices: message.payload.choices ?? [],
                multiSelect: message.payload.multiSelect ?? false,
                submitLabel: message.payload.submitLabel ?? "确认并继续",
                source: "workflow"
            )
            if message.messageType == "requirement_confirmation" {
                RequirementConfirmationCard(
                    block: block,
                    onSubmit: { selection in Task { await model.respond(selection) } }
                )
                .disabled(model.isSubmitting)
            } else {
                ClarifyCard(
                    block: block,
                    onSubmit: { selection in Task { await model.respond(selection) } }
                )
                .disabled(model.isSubmitting)
            }
        } else {
            HStack {
                if message.role == "user" { Spacer(minLength: 44) }
                Text(message.content)
                    .font(AppTheme.Typography.body)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .padding(AppTheme.Spacing.md)
                    .background(
                        message.role == "user"
                        ? AppTheme.Colors.quantumBlue.opacity(0.16)
                        : AppTheme.Colors.cardBackground
                    )
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
                if message.role != "user" { Spacer(minLength: 44) }
            }
        }
    }
}

private struct WorkflowPlanningPendingCard: View {
    let message: String
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            ZStack {
                Circle()
                    .fill(AppTheme.Colors.selectionTint)
                    .frame(width: 40, height: 40)
                Image(systemName: "sparkles")
                    .foregroundStyle(AppTheme.Colors.quantumBlue)
                    .symbolEffect(.pulse, isActive: !reduceMotion)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("已开始生成方案")
                    .font(AppTheme.Typography.body.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text(message)
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                Label("云端持续执行，切换页面不会中断", systemImage: "cloud.fill")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            }
            Spacer(minLength: 0)
            ProgressView().controlSize(.small)
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(AppTheme.Colors.border.opacity(0.8), lineWidth: 0.75)
        }
        .pressBorderGlow(cornerRadius: AppTheme.Radius.lg)
        .accessibilityElement(children: .combine)
    }
}

private struct WorkflowTaskStageHeader: View {
    let phase: String
    private let stages = [
        ("需求", "clarifying"), ("方案", "planning"), ("确认", "awaiting_approval"),
        ("构建", "building_agent"), ("待启动", "agent_ready")
    ]

    private var currentIndex: Int {
        switch phase {
        case "planning", "needs_attention": return 1
        case "awaiting_approval": return 2
        case "building_agent": return 3
        case "agent_ready": return 4
        default: return 0
        }
    }

    var body: some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            ForEach(Array(stages.enumerated()), id: \.offset) { index, stage in
                VStack(spacing: 4) {
                    Image(systemName: index < currentIndex ? "checkmark.circle.fill" : (index == currentIndex ? "circle.inset.filled" : "circle"))
                        .foregroundStyle(index <= currentIndex ? AppTheme.Colors.quantumBlue : AppTheme.Colors.textTertiary)
                    Text(stage.0)
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(index <= currentIndex ? AppTheme.Colors.textPrimary : AppTheme.Colors.textTertiary)
                }
                .frame(maxWidth: .infinity, minHeight: 44)
                if index < stages.count - 1 {
                    Rectangle()
                        .fill(index < currentIndex ? AppTheme.Colors.quantumBlue : AppTheme.Colors.border)
                        .frame(height: 1)
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("任务阶段：\(phase.workflowStatusLabel)")
    }
}

private struct WorkflowAgentReadyView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator
    let workflow: WorkflowDTO
    let agent: WorkflowTaskAgentDTO
    let scope: WorkflowActivityCoordinator.Scope
    let onStarted: (WorkflowExecutionDTO) -> Void
    @State private var isStarting = false
    @State private var errorMessage: String?
    @State private var requestId = UUID().uuidString

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                WorkflowTaskStageHeader(phase: "agent_ready")
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    Label("任务专用 Agent", systemImage: "person.crop.circle.badge.checkmark")
                        .font(AppTheme.Typography.label)
                        .foregroundStyle(AppTheme.Colors.quantumBlue)
                    Text(agent.customName ?? "专属 Agent")
                        .font(AppTheme.Typography.screenTitle)
                    Text("创建者：\(agent.ownerUserId ?? "当前用户") · 仅创建者可见 · 已绑定批准方案")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                    capabilitySection
                    Label(
                        "临时子 Agent：最多并发 \(agent.compositionManifest.delegation.maxConcurrentChildren) 个 · 深度 \(agent.compositionManifest.delegation.maxSpawnDepth) 层",
                        systemImage: "person.3.sequence"
                    )
                    .font(AppTheme.Typography.supporting)
                    if !agent.compositionManifest.knowledgeScope.isEmpty {
                        Text("知识范围：\(agent.compositionManifest.knowledgeScope.joined(separator: "、"))")
                            .font(AppTheme.Typography.supporting)
                    }
                }
                .padding(AppTheme.Spacing.xl)
                .quantumCard()
                if let errorMessage { WorkflowErrorBanner(message: errorMessage) }
            }
            .padding(AppTheme.Metrics.contentGutter)
        }
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: AppTheme.Spacing.sm) {
                Button(isStarting ? "正在启动…" : "启动任务", systemImage: "play.fill") { start() }
                    .buttonStyle(.borderedProminent)
                    .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                    .controlSize(.large)
                    .disabled(isStarting)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .accessibilityIdentifier("workflow-primary-action")

                Button("与此 Agent 对话", systemImage: "bubble.left.and.bubble.right.fill") {
                    appState.openChat(
                        agentId: agent.id,
                        agentName: agent.customName ?? workflow.title
                    )
                }
                .buttonStyle(.bordered)
                .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                .controlSize(.large)
                .frame(maxWidth: .infinity, minHeight: 44)
            }
                .padding(AppTheme.Metrics.contentGutter)
                .background(.ultraThinMaterial)
        }
    }

    private var capabilitySection: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 108), spacing: AppTheme.Spacing.sm)], spacing: AppTheme.Spacing.sm) {
            ForEach(agent.compositionManifest.capabilityAgentIds, id: \.self) { capability in
                Text(capability.workflowCapabilityLabel)
                    .font(AppTheme.Typography.micro)
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, 6)
                    .background(AppTheme.Colors.surfaceTint, in: Capsule())
            }
        }
    }

    private func start() {
        guard workflowActivities.accepts(workflow, in: scope) else {
            errorMessage = "对话会话已切换，无法启动此工作流。"
            return
        }
        isStarting = true
        Task {
            do {
                let execution = try await APIClient.shared.startWorkflow(
                    workflowId: workflow.id, requestId: requestId
                )
                guard workflowActivities.isCurrent(scope) else { return }
                onStarted(execution)
            } catch {
                guard workflowActivities.isCurrent(scope) else { return }
                errorMessage = error.localizedDescription
                isStarting = false
            }
        }
    }
}

private struct WorkflowPlanReviewView: View {
    let workflow: WorkflowDTO
    let scope: WorkflowActivityCoordinator.Scope
    let onApproved: (WorkflowAgentBuildResponseDTO) -> Void
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator
    @State private var plan: WorkflowPlanDTO?
    @State private var tenantAgents: [TenantAgentDTO] = []
    @State private var isSaving = false
    @State private var errorMessage: String?
    @State private var replanErrorMessage: String?
    @State private var isGoalExpanded = false
    @State private var approvalRequestId = UUID().uuidString
    @State private var replanEvents: [WorkflowLifecycleEventDTO] = []
    @State private var showsAdvancedOptions = false

    var body: some View {
        Group {
            if let draft = plan {
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                        WorkflowTaskStageHeader(phase: "awaiting_approval")
                        planHeader(draft)
                        if !draft.validationErrors.isEmpty {
                            WorkflowErrorBanner(message: draft.validationErrors.joined(separator: "\n"))
                        }
                        DisclosureGroup(isExpanded: $showsAdvancedOptions) {
                            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                                nodeTimeline(plan: planBinding)
                                if !replanReasoningSteps.isEmpty {
                                    ReasoningCard(steps: replanReasoningSteps, isStreaming: isSaving)
                                }
                                WorkflowReplanComposer(
                                    isSaving: isSaving,
                                    errorMessage: replanErrorMessage,
                                    onSubmit: replan
                                )
                            }
                            .padding(.top, AppTheme.Spacing.md)
                        } label: {
                            VStack(alignment: .leading, spacing: 3) {
                                Text("高级选项").font(AppTheme.Typography.sectionTitle)
                                Text("按需调整执行步骤或要求重新规划")
                                    .font(AppTheme.Typography.supporting)
                                    .foregroundStyle(AppTheme.Colors.textSecondary)
                            }
                        }
                        .accessibilityIdentifier("workflow-advanced-options")
                        if let errorMessage { WorkflowErrorBanner(message: errorMessage) }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                    .padding(.bottom, 96)
                }
                .safeAreaInset(edge: .bottom) {
                    HStack(spacing: AppTheme.Spacing.md) {
                        if showsAdvancedOptions {
                            Button("保存修改") { save() }
                                .buttonStyle(.bordered)
                                .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                                .frame(maxWidth: .infinity)
                        }
                        Button(isSaving ? "正在处理…" : "确认并构建 Agent") { approve() }
                            .buttonStyle(.borderedProminent)
                            .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                            .frame(maxWidth: .infinity)
                            .disabled(!draft.validationErrors.isEmpty)
                            .accessibilityIdentifier("workflow-primary-action")
                    }
                    .controlSize(.large)
                    .padding(AppTheme.Metrics.contentGutter)
                    .background(.ultraThinMaterial)
                }
                .disabled(isSaving)
            } else {
                VStack(spacing: AppTheme.Spacing.lg) {
                    if let errorMessage {
                        WorkflowErrorBanner(message: errorMessage)
                        Button("重新读取", systemImage: "arrow.clockwise") {
                            Task { await load() }
                        }
                        .buttonStyle(.borderedProminent)
                        .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                    } else {
                        ProgressView("正在读取执行计划…")
                    }
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
        }
        .task { await load() }
    }

    private var planBinding: Binding<WorkflowPlanDTO> {
        Binding(
            get: { plan! },
            set: { plan = $0 }
        )
    }

    private func planHeader(_ plan: WorkflowPlanDTO) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Label("计划 v\(plan.version)", systemImage: "checklist.checked")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.Colors.quantumBlue)
                Spacer()
                Text("等待确认")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.statusWarning)
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.vertical, AppTheme.Spacing.sm)
                    .background(AppTheme.Colors.warningSurface)
                    .clipShape(Capsule())
            }

            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Text("方案目标")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                Text(goalSummary(plan.goal))
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .lineSpacing(3)
                    .lineLimit(isGoalExpanded ? nil : 4)
                if goalSummary(plan.goal).count > 80 {
                    Button(isGoalExpanded ? "收起目标" : "展开完整目标", systemImage: isGoalExpanded ? "chevron.up" : "chevron.down") {
                        withAnimation(AppTheme.Motion.quick) { isGoalExpanded.toggle() }
                    }
                    .font(AppTheme.Typography.supporting.weight(.semibold))
                    .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                }
            }

            if !confirmedRequirementRows(plan.goal).isEmpty {
                Divider()
                VStack(spacing: AppTheme.Spacing.md) {
                    ForEach(Array(confirmedRequirementRows(plan.goal).enumerated()), id: \.offset) { index, item in
                        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                            Image(systemName: requirementIcon(index))
                                .foregroundStyle(AppTheme.Colors.quantumViolet)
                                .frame(width: 24, height: 24)
                            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                                Text(item.0)
                                    .font(AppTheme.Typography.micro)
                                    .foregroundStyle(AppTheme.Colors.textSecondary)
                                Text(item.1)
                                    .font(AppTheme.Typography.supporting.weight(.medium))
                                    .foregroundStyle(AppTheme.Colors.textPrimary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                    }
                }
            }

            ViewThatFits(in: .horizontal) {
                HStack(spacing: AppTheme.Spacing.sm) { planMetrics(plan) }
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) { planMetrics(plan) }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(AppTheme.Spacing.lg)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg)
                .stroke(AppTheme.Colors.border, lineWidth: 1)
        }
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder
    private func planMetrics(_ plan: WorkflowPlanDTO) -> some View {
        planMetric("\(plan.dsl.nodes.count) 个步骤", icon: "point.3.connected.trianglepath.dotted")
        planMetric(plan.allowNetwork ? "可联网补证" : "仅知识库", icon: plan.allowNetwork ? "network" : "internaldrive")
    }

    private func planMetric(_ title: String, icon: String) -> some View {
        Label(title, systemImage: icon)
            .font(AppTheme.Typography.micro)
            .foregroundStyle(AppTheme.Colors.textSecondary)
            .padding(.horizontal, AppTheme.Spacing.md)
            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            .background(AppTheme.Colors.surfaceTint)
            .clipShape(Capsule())
    }

    private func goalSummary(_ goal: String) -> String {
        goal.components(separatedBy: "\n\n已确认需求：").first?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? goal
    }

    private func confirmedRequirementRows(_ goal: String) -> [(String, String)] {
        var result: [(String, String)] = []
        var seen = Set<String>()
        for line in goal.components(separatedBy: .newlines) {
            let cleaned = line.trimmingCharacters(in: .whitespacesAndNewlines)
                .replacingOccurrences(of: "- ", with: "")
            guard let separator = cleaned.firstIndex(of: "：") else { continue }
            let title = String(cleaned[..<separator])
            let value = String(cleaned[cleaned.index(after: separator)...])
            guard ["目标用户与场景", "MVP 范围", "约束与验收"].contains(title),
                  !value.isEmpty, seen.insert(title).inserted else { continue }
            result.append((title, value))
        }
        return result
    }

    private func requirementIcon(_ index: Int) -> String {
        ["person.crop.circle", "scope", "checkmark.seal"][min(index, 2)]
    }

    private func nodeTimeline(plan: Binding<WorkflowPlanDTO>) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                Text("执行步骤").font(AppTheme.Typography.sectionTitle)
                Spacer()
                Button("添加", systemImage: "plus") { addNode() }
            }
            ForEach(plan.wrappedValue.dsl.nodes.indices, id: \.self) { index in
                WorkflowPlanNodeEditor(
                    index: index,
                    node: plan.dsl.nodes[index],
                    agents: tenantAgents,
                    isLast: index == plan.wrappedValue.dsl.nodes.count - 1,
                    onDelete: { deleteNode(at: index) },
                    onMoveUp: { moveNode(from: index, to: index - 1) },
                    onMoveDown: { moveNode(from: index, to: index + 1) }
                )
            }
        }
    }

    private func load() async {
        guard workflowActivities.accepts(workflow, in: scope) else {
            errorMessage = "对话会话已切换，无法读取此工作流。"
            return
        }
        do {
            async let loadedPlan = APIClient.shared.fetchWorkflowPlan(workflowId: workflow.id)
            async let loadedAgents = APIClient.shared.fetchTenantAgents()
            let loadedPlanValue = try await loadedPlan
            let loadedAgentsValue = (try? await loadedAgents) ?? []
            guard workflowActivities.isCurrent(scope) else { return }
            plan = loadedPlanValue
            tenantAgents = loadedAgentsValue
        } catch {
            guard workflowActivities.isCurrent(scope) else { return }
            errorMessage = error.localizedDescription
        }
    }

    private func save() {
        guard let plan, workflowActivities.accepts(workflow, in: scope) else { return }
        isSaving = true
        Task {
            do {
                let updated = try await APIClient.shared.updateWorkflowPlan(workflowId: workflow.id, plan: plan)
                guard workflowActivities.isCurrent(scope) else { return }
                self.plan = updated
                errorMessage = nil
            } catch {
                guard workflowActivities.isCurrent(scope) else { return }
                errorMessage = error.localizedDescription
            }
            guard workflowActivities.isCurrent(scope) else { return }
            isSaving = false
        }
    }

    private func approve() {
        guard let plan, workflowActivities.accepts(workflow, in: scope) else { return }
        isSaving = true
        Task {
            do {
                _ = try await APIClient.shared.updateWorkflowPlan(workflowId: workflow.id, plan: plan)
                guard workflowActivities.isCurrent(scope) else { return }
                let buildResult = try await APIClient.shared.approveWorkflowPlan(
                    workflowId: workflow.id,
                    requestId: approvalRequestId
                )
                guard workflowActivities.isCurrent(scope) else { return }
                onApproved(buildResult)
            } catch {
                guard workflowActivities.isCurrent(scope) else { return }
                errorMessage = error.localizedDescription
                isSaving = false
            }
        }
    }

    private func replan(instruction: String) {
        guard workflowActivities.accepts(workflow, in: scope) else { return }
        isSaving = true
        errorMessage = nil
        replanErrorMessage = nil
        Task {
            do {
                let startedSession = try await APIClient.shared.replanWorkflow(
                    workflowId: workflow.id, instruction: instruction
                )
                guard workflowActivities.isCurrent(scope) else { return }
                replanEvents.removeAll()
                var cursor = startedSession.lastEventSeq
                var finished = false
                var reconnectAttempt = 0
                while !finished && !Task.isCancelled {
                    do {
                        for try await event in APIClient.shared.workflowLifecycleEventStream(
                            workflowId: workflow.id, after: cursor
                        ) {
                            guard workflowActivities.isCurrent(scope) else { return }
                            reconnectAttempt = 0
                            cursor = max(cursor, event.id)
                            if !replanEvents.contains(where: { $0.id == event.id }) {
                                replanEvents.append(event)
                            }
                            if event.type == "planning_failed" {
                                let detail = event.payload.detail?.trimmingCharacters(in: .whitespacesAndNewlines)
                                replanErrorMessage = (detail?.isEmpty == false ? detail : nil)
                                    ?? "方案生成失败，需求与过程记录已保留，可以修改意见后重试。"
                                finished = true
                                break
                            }
                            if event.type == "plan_ready" {
                                let loaded = try await APIClient.shared.fetchWorkflowPlan(workflowId: workflow.id)
                                guard workflowActivities.isCurrent(scope) else { return }
                                plan = loaded
                                finished = true
                                break
                            }
                        }
                    } catch is CancellationError {
                        return
                    } catch {
                        guard workflowActivities.isCurrent(scope) else { return }
                        reconnectAttempt += 1
                        replanErrorMessage = "进度连接中断，正在恢复同一规划任务…"
                        let delay = UInt64(min(reconnectAttempt, 8)) * 1_000_000_000
                        try? await Task.sleep(nanoseconds: delay)
                        guard workflowActivities.isCurrent(scope) else { return }
                    }
                }
            } catch {
                guard workflowActivities.isCurrent(scope) else { return }
                replanErrorMessage = error.localizedDescription
            }
            guard workflowActivities.isCurrent(scope) else { return }
            isSaving = false
        }
    }

    private var replanReasoningSteps: [ReasoningStep] {
        replanEvents.filter {
            ["replan_requested", "planning_started", "planner_context_loaded", "capabilities_selecting", "plan_compiled", "policy_validated", "plan_ready", "planning_failed"].contains($0.type)
        }.map { event in
            let type: ReasoningStepType
            switch event.type {
            case "planner_context_loaded": type = .skillLoad
            case "capabilities_selecting": type = .agentSpawn
            case "plan_compiled", "policy_validated": type = .toolCall
            default: type = .thought
            }
            return ReasoningStep(
                id: "replan-event-\(event.id)", type: type,
                title: event.message,
                detail: event.payload.detail ?? event.payload.tool ?? "",
                status: event.type == "planning_failed" ? "failed" : "done"
            )
        }
    }

    private func addNode() {
        guard var plan else { return }
        let id = "custom_\(UUID().uuidString.lowercased().replacingOccurrences(of: "-", with: ""))"
        plan.dsl.nodes.append(
            WorkflowPlanNodeDTO(
                id: id,
                nodeType: "PROMPT_TRANSFORM",
                name: "新增处理步骤",
                parameters: WorkflowNodeParametersDTO(
                    agentId: "main_agent", query: nil, instruction: "",
                    outputFormat: nil, knowledgeScope: plan.knowledgeScope,
                    allowNetwork: plan.allowNetwork, requiresReview: false,
                    maxTokens: 3000, revisionNote: nil
                )
            )
        )
        self.plan = rebuiltEdges(plan)
    }

    private func deleteNode(at index: Int) {
        guard var plan, plan.dsl.nodes.count > 1 else { return }
        plan.dsl.nodes.remove(at: index)
        self.plan = rebuiltEdges(plan)
    }

    private func moveNode(from: Int, to: Int) {
        guard var plan, plan.dsl.nodes.indices.contains(from), plan.dsl.nodes.indices.contains(to) else { return }
        let node = plan.dsl.nodes.remove(at: from)
        plan.dsl.nodes.insert(node, at: to)
        self.plan = rebuiltEdges(plan)
    }

    private func rebuiltEdges(_ value: WorkflowPlanDTO) -> WorkflowPlanDTO {
        var copy = value
        copy.dsl.edges = zip(copy.dsl.nodes, copy.dsl.nodes.dropFirst()).map {
            WorkflowPlanEdgeDTO(source: $0.id, target: $1.id, condition: nil)
        }
        return copy
    }
}

/// Keeps marked-text/IME updates local so typing does not invalidate the full
/// plan header and every node editor on each keystroke.
private struct WorkflowReplanComposer: View {
    let isSaving: Bool
    let errorMessage: String?
    let onSubmit: (String) -> Void

    @State private var instruction = ""
    @FocusState private var isFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Text("让 Quantum 重新规划")
                .font(AppTheme.Typography.sectionTitle)
            TextField(
                "例如：增加竞品对比和近三个月新闻",
                text: $instruction,
                axis: .vertical
            )
            .textFieldStyle(.roundedBorder)
            .lineLimit(1...4)
            .focused($isFocused)
            .submitLabel(.send)
            .onSubmit(submit)

            Button("按意见重新生成", systemImage: "arrow.triangle.2.circlepath", action: submit)
                .disabled(isSaving || normalizedInstruction.isEmpty)
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)

            if let errorMessage {
                WorkflowErrorBanner(message: errorMessage)
                    .accessibilityLabel("重新规划失败：\(errorMessage)")
            }
        }
    }

    private var normalizedInstruction: String {
        instruction.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func submit() {
        let value = normalizedInstruction
        guard !isSaving, !value.isEmpty else { return }
        isFocused = false
        instruction = ""
        onSubmit(value)
    }
}

private struct WorkflowPlanNodeEditor: View {
    let index: Int
    @Binding var node: WorkflowPlanNodeDTO
    let agents: [TenantAgentDTO]
    let isLast: Bool
    let onDelete: () -> Void
    let onMoveUp: () -> Void
    let onMoveDown: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            VStack(spacing: 0) {
                Text("\(index + 1)")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(.white)
                    .frame(width: 28, height: 28)
                    .background(AppTheme.Colors.quantumBlue, in: Circle())
                Rectangle().fill(AppTheme.Colors.border).frame(width: 1, height: 92)
            }
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                TextField("步骤名称", text: Binding(get: { node.name ?? "" }, set: { node.name = $0 }))
                    .font(AppTheme.Typography.cardTitle)
                Text(node.nodeType.replacingOccurrences(of: "_", with: " "))
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
                Menu {
                    ForEach(["main_agent", "knowledge", "coder", "supervision"], id: \.self) { id in
                        Button(id) { node.parameters.agentId = id }
                    }
                    ForEach(agents) { agent in
                        Button(agent.customName ?? agent.id) { node.parameters.agentId = agent.id }
                    }
                } label: {
                    Label(node.parameters.agentId ?? "main_agent", systemImage: "person.crop.circle.badge.checkmark")
                }
                TextField(
                    "节点执行要求",
                    text: Binding(
                        get: { node.parameters.instruction ?? node.parameters.query ?? "" },
                        set: { node.parameters.instruction = $0; node.parameters.query = nil }
                    ),
                    axis: .vertical
                )
                .font(AppTheme.Typography.supporting)
                HStack {
                    Button("上移", systemImage: "arrow.up", action: onMoveUp).disabled(index == 0)
                    Button("下移", systemImage: "arrow.down", action: onMoveDown).disabled(isLast)
                    Spacer()
                    Button("删除", systemImage: "trash", role: .destructive, action: onDelete)
                }
                .labelStyle(.iconOnly)
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg))
        }
    }
}

// MARK: - 执行与成果复核

struct PresentationProductStep {
    static let labels = ["需求确认", "全稿预览", "下载"]

    static func currentIndex(executionStatus: String) -> Int {
        executionStatus == "completed" ? 2 : 1
    }
}

private struct PresentationWorkflowStageHeader: View {
    let currentIndex: Int
    private let stages = PresentationProductStep.labels

    var body: some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            ForEach(Array(stages.enumerated()), id: \.offset) { index, title in
                VStack(spacing: 4) {
                    Image(systemName: index < currentIndex ? "checkmark.circle.fill" : (index == currentIndex ? "circle.inset.filled" : "circle"))
                        .foregroundStyle(index <= currentIndex ? AppTheme.Colors.quantumBlue : AppTheme.Colors.textTertiary)
                    Text(title).font(AppTheme.Typography.micro)
                        .foregroundStyle(index <= currentIndex ? AppTheme.Colors.textPrimary : AppTheme.Colors.textTertiary)
                }
                .frame(maxWidth: .infinity, minHeight: 44)
                if index < stages.count - 1 {
                    Rectangle()
                        .fill(index < currentIndex ? AppTheme.Colors.quantumBlue : AppTheme.Colors.border)
                        .frame(height: 1)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("PPT 工作流，第 \(currentIndex + 1) 步，共 3 步：\(stages[currentIndex])")
        .accessibilityIdentifier("presentation.three-step-header")
    }
}

private struct WorkflowExecutionView: View {
    let workflow: WorkflowDTO
    let scope: WorkflowActivityCoordinator.Scope
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator
    @State private var execution: WorkflowExecutionDTO
    @State private var artifacts: [WorkflowArtifactDTO] = []
    @State private var selectedArtifacts: Set<String> = []
    @State private var selectedArtifact: WorkflowArtifactDTO?
    @State private var errorMessage: String?
    @State private var isWorking = false
    @State private var executionEvents: [WorkflowEventDTO] = []
    @State private var lastExecutionEventId = 0
    @State private var feedback = ""
    @State private var slideNumber = 1
    @State private var showsStructuredReview = false
    @State private var showsAdvancedExecutionDetails = false

    private var isPresentation: Bool { workflow.desiredOutput.lowercased().contains("pptx") }
    private var isDocument: Bool {
        let output = workflow.desiredOutput.lowercased()
        return output.contains("docx") || output.contains("word")
    }
    private var isStagedOutput: Bool { isPresentation || isDocument }

    init(
        workflow: WorkflowDTO,
        initialExecution: WorkflowExecutionDTO,
        scope: WorkflowActivityCoordinator.Scope
    ) {
        self.workflow = workflow
        self.scope = scope
        _execution = State(initialValue: initialExecution)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                if isPresentation { PresentationWorkflowStageHeader(currentIndex: presentationStageIndex) }
                executionHeader
                if isPresentation {
                    DisclosureGroup(isExpanded: $showsAdvancedExecutionDetails) {
                        ReasoningCard(
                            steps: executionReasoningSteps,
                            isStreaming: ["queued", "running"].contains(execution.status),
                            initiallyExpanded: false
                        )
                        nodeProgress
                    } label: {
                        Label("高级详情", systemImage: "slider.horizontal.3")
                            .font(AppTheme.Typography.supporting)
                    }
                    .accessibilityIdentifier("presentation.advanced-details")
                } else {
                    ReasoningCard(
                        steps: executionReasoningSteps,
                        isStreaming: ["queued", "running"].contains(execution.status),
                        initiallyExpanded: false
                    )
                    nodeProgress
                }
                if let failure = WorkflowFailurePresentation.make(execution: execution) {
                    WorkflowFailureCard(failure: failure)
                }
                if ["awaiting_approval", "awaiting_review", "completed"].contains(execution.status) {
                    artifactReview
                }
                if let errorMessage { WorkflowErrorBanner(message: errorMessage) }
            }
            .padding(AppTheme.Metrics.contentGutter)
            .padding(.bottom, 88)
        }
        .safeAreaInset(edge: .bottom) { actionBar }
        .task {
            WorkflowActivityCoordinator.shared.trackExecution(execution, workflow: workflow)
            await monitor()
        }
        .sheet(item: $selectedArtifact) { artifact in
            WorkflowArtifactPreview(
                executionId: execution.id,
                artifact: artifact,
                scope: scope,
                currentPage: $slideNumber,
                allowsDownload: execution.status == "completed"
            )
        }
        .sheet(isPresented: $showsStructuredReview) {
            if let artifact = visibleArtifacts.last {
                NavigationStack {
                    StructuredReviewView(
                        workflowId: workflow.id,
                        reviewKey: "final-draft",
                        initialDocument: structuredReviewSeed(from: artifact),
                        scope: scope
                    )
                    .navigationTitle("结构化审核")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button("关闭") { showsStructuredReview = false }
                        }
                    }
                }
            }
        }
    }

    private var activePresentationGate: String? {
        artifacts.last(where: { $0.metadata.approvalGate != nil })?.metadata.approvalGate
    }

    private var presentationStageIndex: Int {
        PresentationProductStep.currentIndex(executionStatus: execution.status)
    }

    private var visibleArtifacts: [WorkflowArtifactDTO] {
        if isDocument {
            if execution.status == "awaiting_approval" {
                return artifacts.filter { $0.metadata.approvalGate == activePresentationGate }
            }
            if execution.status == "awaiting_review" || execution.status == "completed" {
                return artifacts.filter { $0.extension == "docx" && $0.metadata.approvalGate == nil }
            }
            return artifacts
        }
        guard isPresentation else { return artifacts }
        if execution.status == "awaiting_approval" {
            let gate = activePresentationGate
            return artifacts.filter {
                $0.metadata.approvalGate == gate || (gate == "outline" && $0.metadata.renderType == "markdown")
            }
        }
        if execution.status == "awaiting_review" || execution.status == "completed" {
            return artifacts.filter { $0.extension == "pptx" && $0.sourceKind != "design_sample" }
        }
        return artifacts
    }

    private var executionHeader: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                WorkflowStatusBadge(status: execution.status)
                Spacer()
                Text("\(execution.progress)%").font(AppTheme.Typography.screenTitle)
            }
            ProgressView(value: Double(execution.progress), total: 100)
                .tint(AppTheme.Colors.quantumBlue)
            Label("\(execution.artifactCount) 个产物", systemImage: "doc.on.doc")
            .font(AppTheme.Typography.micro)
            .foregroundStyle(AppTheme.Colors.textSecondary)
        }
        .padding(AppTheme.Spacing.xl)
        .background(AppTheme.Colors.surfaceTint)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl))
    }

    private var executionReasoningSteps: [ReasoningStep] {
        executionEvents.map { event in
            let category = event.payload?.category ?? event.type
            let type: ReasoningStepType
            switch category {
            case "tool_start", "tool_complete", "tool_call": type = .toolCall
            case "skill_load": type = .skillLoad
            case "agent_spawn": type = .agentSpawn
            default: type = .thought
            }
            return ReasoningStep(
                id: String(event.id),
                type: type,
                title: event.message,
                detail: [event.payload?.tool, event.payload?.detail].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "),
                status: event.payload?.status ?? (category.hasSuffix("started") || category == "tool_start" ? "running" : "done")
            )
        }
    }

    private var nodeProgress: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Text("实时执行").font(AppTheme.Typography.sectionTitle)
            ForEach(execution.nodes) { node in
                HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                    Image(systemName: nodeIcon(node.status))
                        .foregroundStyle(nodeColor(node.status))
                        .frame(width: 28, height: 28)
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                        Text(node.name).font(AppTheme.Typography.cardTitle)
                        if let error = node.errorMessage {
                            Text(error).font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.statusError)
                        }
                    }
                    Spacer()
                    Text(node.status.workflowStatusLabel)
                        .font(AppTheme.Typography.micro)
                }
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            }
        }
    }

    private var artifactReview: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Text(isStagedOutput ? stagedReviewTitle : "成果与入库素材").font(AppTheme.Typography.sectionTitle)
            Text(isStagedOutput ? stagedReviewHelp : "所有内容已保存到工作流档案。勾选后批准，才会进入正式知识库。")
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            ForEach(visibleArtifacts) { artifact in
                HStack(spacing: AppTheme.Spacing.md) {
                    if !isStagedOutput { Button {
                        if selectedArtifacts.contains(artifact.id) { selectedArtifacts.remove(artifact.id) }
                        else { selectedArtifacts.insert(artifact.id) }
                    } label: {
                        Image(systemName: selectedArtifacts.contains(artifact.id) ? "checkmark.square.fill" : "square")
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                            .frame(width: 44, height: 44)
                    } }
                    Button {
                        selectedArtifact = artifact
                    } label: {
                        HStack(spacing: AppTheme.Spacing.sm) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(artifact.title).font(AppTheme.Typography.cardTitle).lineLimit(2)
                                Text(artifact.kind).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            Image(systemName: "chevron.right").foregroundStyle(AppTheme.Colors.textTertiary)
                        }
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(SoftButtonStyle())
                    .accessibilityIdentifier("workflow-artifact-preview-\(artifact.id)")
                    .accessibilityHint("打开成果预览")
                }
                .padding(AppTheme.Spacing.sm)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            }
            if isStagedOutput,
               ["awaiting_review", "completed"].contains(execution.status),
               visibleArtifacts.last != nil {
                Button(isPresentation ? "编辑全稿内容" : "填写结构化审核", systemImage: "checklist") {
                    showsStructuredReview = true
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                .accessibilityIdentifier("open-structured-review")
            }
            if isStagedOutput && ["awaiting_approval", "awaiting_review"].contains(execution.status) {
                TextField(stagedFeedbackPrompt, text: $feedback, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityLabel(stagedFeedbackPrompt)
                if execution.status == "awaiting_review" && isPresentation {
                    Stepper("反馈页：第 \(slideNumber) 页", value: $slideNumber, in: 1...60)
                    Text("打开全稿预览时，页码会自动同步到这里。")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                }
            }
        }
    }

    private func structuredReviewSeed(from artifact: WorkflowArtifactDTO) -> StructuredReviewDocumentDTO {
        var values: [String: JSONScalar] = ["deliverable_title": .string(artifact.title)]
        if isPresentation {
            values["outline_items"] = .array([])
            values["slides"] = .array([])
        }
        if let version = artifact.metadata.artifactVersion {
            values["artifact_version"] = .integer(Int64(version))
        }
        return StructuredReviewDocumentDTO(
            title: artifact.title,
            fields: [
                .init(id: "deliverable_title", label: "成果标题", type: .text, required: true, options: nil),
                .init(id: "review_notes", label: "审核意见", type: .textarea, required: false, options: nil),
                .init(id: "decision", label: "审核结论", type: .choice, required: true, options: ["需要修改", "可以确认"]),
                .init(id: "artifact_version", label: "成果版本", type: .number, required: false, options: nil),
                .init(id: "preview_checked", label: "已检查成果预览", type: .toggle, required: true, options: nil),
            ] + (isPresentation ? [
                .init(id: "outline_items", label: "内容清单", type: .list, required: false, options: nil),
                .init(id: "slides", label: "页面结构", type: .pageStructure, required: false, options: nil),
                .init(id: "cover_asset", label: "封面素材", type: .asset, required: false, options: nil),
            ] : []),
            values: values
        )
    }

    private var stagedReviewTitle: String {
        if isPresentation { return presentationReviewTitle }
        return activePresentationGate == "outline" ? "确认 Word 文档大纲" : "确认 Word 文档全文"
    }

    private var stagedReviewHelp: String {
        if isPresentation { return presentationReviewHelp }
        if execution.status == "completed" { return "文档已确认，可预览、下载 DOCX 或用系统分享。" }
        if execution.status == "awaiting_review" { return "检查完整正文；可退回修改，确认后开放 DOCX 下载与系统分享。" }
        return activePresentationGate == "outline"
            ? "先确认章节结构和每节要点，再生成完整 Word 文档。"
            : "检查完整正文；可以继续退回修改。"
    }

    private var stagedFeedbackPrompt: String {
        if isPresentation { return presentationFeedbackPrompt }
        return activePresentationGate == "outline" ? "说明大纲要如何修改（退回时必填）" : "说明正文要如何修改（退回时必填）"
    }

    private var presentationReviewTitle: String {
        if execution.status == "awaiting_review" || execution.status == "completed" { return "逐页验收全稿" }
        return activePresentationGate == "design" ? "确认版式与真实内容" : "确认故事线与逐页大纲"
    }

    private var presentationReviewHelp: String {
        if execution.status == "awaiting_review" { return "先打开全稿逐页检查。退回时会从指定页修订；确认后开放 PPTX 下载与系统分享。" }
        if execution.status == "completed" { return "全稿已确认，可打开预览并下载可编辑 PPTX。" }
        if activePresentationGate == "design" { return "检查代表页的配色、字体、信息密度和真实内容。可以反复退回，确认后才会铺开整份 PPT。" }
        return "先查看文档分析，再检查每页的作用、标题、证据和视觉建议。可以反复退回，确认后才进入版式设计。"
    }

    private var presentationFeedbackPrompt: String {
        if execution.status == "awaiting_review" { return "说明这一页要如何修改（退回时必填）" }
        return activePresentationGate == "design" ? "说明版式或内容要如何调整（退回时必填）" : "说明大纲要如何调整（退回时必填）"
    }

    @ViewBuilder
    private var actionBar: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            if isWorking { ProgressView().controlSize(.small) }
            if execution.status == "queued" || execution.status == "running" {
                Button("取消执行", role: .destructive) { cancel() }
                    .buttonStyle(.bordered)
                    .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
            } else if execution.status == "failed" || execution.status == "cancelled" {
                Button("从失败处重试", systemImage: "arrow.clockwise") { retry() }
                    .buttonStyle(.borderedProminent)
                    .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
            } else if execution.status == "awaiting_approval" && isPresentation {
                Button(activePresentationGate == "design" ? "修改版式" : "修改大纲") { reviewPresentation(decision: "revise") }.buttonStyle(.bordered)
                Button(activePresentationGate == "design" ? "确认并生成全稿" : "确认大纲") { reviewPresentation(decision: "approve") }.buttonStyle(.borderedProminent)
            } else if execution.status == "awaiting_review" && isPresentation {
                Button("修改第 \(slideNumber) 页") { reviewPresentation(decision: "revise", perSlide: true) }.buttonStyle(.bordered)
                Button("确认并下载") { reviewPresentation(decision: "approve") }.buttonStyle(.borderedProminent)
            } else if execution.status == "awaiting_approval" && isDocument {
                Button("修改") { reviewStagedOutput(decision: "revise") }.buttonStyle(.bordered)
                Button(activePresentationGate == "outline" ? "确认大纲" : "确认全文") { reviewStagedOutput(decision: "approve") }.buttonStyle(.borderedProminent)
            } else if execution.status == "awaiting_review" && isDocument {
                Button("退回修改") { reviewStagedOutput(decision: "revise") }.buttonStyle(.bordered)
                Button("确认并下载") { reviewStagedOutput(decision: "approve") }.buttonStyle(.borderedProminent)
            } else if execution.status == "awaiting_review" {
                Button("退回修改") { requestRevision() }
                    .buttonStyle(.bordered)
                    .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                Button("批准并入库", systemImage: "checkmark.shield") { approveOutput() }
                    .buttonStyle(.borderedProminent)
                    .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                    .disabled(selectedArtifacts.isEmpty)
            } else {
                Label("已完成并归档", systemImage: "checkmark.seal.fill")
                    .foregroundStyle(AppTheme.Colors.statusCompleted)
            }
        }
        .controlSize(.large)
        .frame(maxWidth: .infinity)
        .padding(AppTheme.Metrics.contentGutter)
        .background(.ultraThinMaterial)
        .disabled(isWorking)
    }

    private func monitor() async {
        guard workflowActivities.accepts(workflow, in: scope) else { return }
        do {
            let initial = try await APIClient.shared.fetchWorkflowExecution(id: execution.id)
            guard workflowActivities.isCurrent(scope) else { return }
            execution = initial
            if !["awaiting_approval", "awaiting_review", "completed", "failed", "cancelled"].contains(execution.status) {
                for try await event in APIClient.shared.workflowEventStream(
                    executionId: execution.id,
                    after: lastExecutionEventId
                ) {
                    guard workflowActivities.isCurrent(scope) else { return }
                    if event.id > lastExecutionEventId {
                        executionEvents.append(event)
                        lastExecutionEventId = event.id
                    }
                    let snapshot = try await APIClient.shared.fetchWorkflowExecution(id: execution.id)
                    guard workflowActivities.isCurrent(scope) else { return }
                    execution = snapshot
                }
            }
        } catch {
            guard workflowActivities.isCurrent(scope) else { return }
            // SSE 在代理或弱网下不可用时，下面的持久状态轮询接管恢复。
        }
        while !Task.isCancelled {
            do {
                let snapshot = try await APIClient.shared.fetchWorkflowExecution(id: execution.id)
                guard workflowActivities.isCurrent(scope) else { return }
                execution = snapshot
                if ["awaiting_approval", "awaiting_review", "completed"].contains(execution.status) {
                    let loaded = try await APIClient.shared.fetchWorkflowArtifacts(executionId: execution.id)
                    guard workflowActivities.isCurrent(scope) else { return }
                    artifacts = loaded
                    if selectedArtifacts.isEmpty {
                        selectedArtifacts = Set(artifacts.filter(\.selectedForPublish).map(\.id))
                    }
                    return
                }
                if ["failed", "cancelled"].contains(execution.status) { return }
            } catch {
                guard workflowActivities.isCurrent(scope) else { return }
                errorMessage = error.localizedDescription
            }
            try? await Task.sleep(for: .seconds(2))
            guard workflowActivities.isCurrent(scope) else { return }
        }
    }

    private func cancel() {
        perform {
            let updated = try await APIClient.shared.cancelWorkflowExecution(id: execution.id)
            guard workflowActivities.isCurrent(scope) else { return }
            execution = updated
        }
    }
    private func retry() {
        perform {
            let updated = try await APIClient.shared.retryWorkflowExecution(id: execution.id)
            guard workflowActivities.isCurrent(scope) else { return }
            execution = updated
            await monitor()
        }
    }
    private func requestRevision() {
        let nodeId = execution.nodes.first(where: { $0.nodeType == "FILTER_PASS" })?.nodeId ?? execution.nodes.last?.nodeId ?? "review_output"
        perform {
            let updated = try await APIClient.shared.requestWorkflowRevision(
                executionId: execution.id, nodeId: nodeId, comment: "请根据复核意见重新检查并完善成果"
            )
            guard workflowActivities.isCurrent(scope) else { return }
            execution = updated
            await monitor()
        }
    }
    private func approveOutput() {
        perform {
            try await APIClient.shared.approveWorkflowOutput(
                executionId: execution.id, artifactIds: Array(selectedArtifacts)
            )
            guard workflowActivities.isCurrent(scope) else { return }
            let updated = try await APIClient.shared.fetchWorkflowExecution(id: execution.id)
            guard workflowActivities.isCurrent(scope) else { return }
            execution = updated
        }
    }
    private func reviewPresentation(decision: String, perSlide: Bool = false) {
        guard let artifact = artifacts.last(where: { item in
            if execution.status == "awaiting_approval" { return item.metadata.approvalGate == activePresentationGate }
            return item.extension == "pptx" && item.sourceKind != "design_sample"
        }) else { errorMessage = "待确认成果尚未同步"; return }
        if decision == "revise" && feedback.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { errorMessage = "请填写修改意见"; return }
        perform {
            let updated = try await APIClient.shared.reviewPresentationStage(executionId: execution.id, artifact: artifact, decision: decision, comment: feedback, slideNumber: perSlide ? slideNumber : nil)
            guard workflowActivities.isCurrent(scope) else { return }
            execution = updated
            feedback = ""
            if decision == "approve" && execution.status == "completed" { selectedArtifact = artifact }
            else { await monitor() }
        }
    }
    private func reviewStagedOutput(decision: String) {
        guard let artifact = artifacts.last(where: { item in
            if execution.status == "awaiting_approval" {
                return item.metadata.approvalGate == activePresentationGate
            }
            return item.extension == "docx"
        }) else { errorMessage = "待确认成果尚未同步"; return }
        if decision == "revise" && feedback.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            errorMessage = "请填写修改意见"
            return
        }
        perform {
            let updated = try await APIClient.shared.reviewPresentationStage(
                executionId: execution.id,
                artifact: artifact,
                decision: decision,
                comment: feedback
            )
            guard workflowActivities.isCurrent(scope) else { return }
            execution = updated
            feedback = ""
            if decision == "approve" && execution.status == "completed" { selectedArtifact = artifact }
            else { await monitor() }
        }
    }
    private func perform(_ operation: @escaping () async throws -> Void) {
        guard workflowActivities.accepts(workflow, in: scope) else {
            errorMessage = "对话会话已切换，无法执行此操作。"
            return
        }
        isWorking = true
        Task {
            do {
                try await operation()
                guard workflowActivities.isCurrent(scope) else { return }
                errorMessage = nil
            } catch {
                guard workflowActivities.isCurrent(scope) else { return }
                errorMessage = error.localizedDescription
            }
            guard workflowActivities.isCurrent(scope) else { return }
            isWorking = false
        }
    }
    private func nodeIcon(_ status: String) -> String {
        switch status {
        case "running": return "waveform.circle.fill"
        case "succeeded": return "checkmark.circle.fill"
        case "failed": return "exclamationmark.triangle.fill"
        default: return "circle.dotted"
        }
    }
    private func nodeColor(_ status: String) -> Color {
        switch status {
        case "running": return AppTheme.Colors.statusRunning
        case "succeeded": return AppTheme.Colors.statusCompleted
        case "failed": return AppTheme.Colors.statusError
        default: return AppTheme.Colors.statusIdle
        }
    }
}

private struct WorkflowArtifactPreview: View {
    let executionId: String
    let artifact: WorkflowArtifactDTO
    let scope: WorkflowActivityCoordinator.Scope
    @Binding var currentPage: Int
    let allowsDownload: Bool
    @State private var content: String?
    @State private var errorMessage: String?
    @State private var pdfDocument: PDFDocument?
    @State private var downloadURL: URL?
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator

    var body: some View {
        NavigationStack {
            ScrollView {
                if let pdfDocument {
                    Text("第 \(currentPage) / \(pdfDocument.pageCount) 页").font(AppTheme.Typography.supporting)
                    PDFDeckView(document: pdfDocument, currentPage: $currentPage).frame(minHeight: 620)
                } else if let content {
                    if artifact.metadata.renderType == "presentation_outline",
                       let outline = PresentationOutlinePreview.decode(content) {
                        PresentationOutlinePreview(outline: outline)
                            .padding(AppTheme.Metrics.contentGutter)
                    } else {
                        Text(content)
                            .font(.body)
                            .textSelection(.enabled)
                            .frame(maxWidth: AppTheme.Metrics.readableContentWidth, alignment: .leading)
                            .padding(AppTheme.Metrics.contentGutter)
                    }
                } else if let errorMessage {
                    WorkflowErrorBanner(message: errorMessage).padding()
                } else {
                    ProgressView("正在读取落盘内容…").padding()
                }
            }
            .navigationTitle(artifact.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("完成") { dismiss() } }
            .safeAreaInset(edge: .bottom) {
                if allowsDownload, let downloadURL {
                    ShareLink(item: downloadURL) { Label("下载可编辑 \(artifact.extension.uppercased()) / 存储到文件 / 分享", systemImage: "square.and.arrow.up") }
                        .buttonStyle(.borderedProminent)
                        .frame(minHeight: 44)
                        .padding()
                }
            }
            .task {
                guard workflowActivities.isCurrent(scope) else {
                    errorMessage = "对话会话已切换，无法读取此成果。"
                    return
                }
                do {
                    if artifact.extension == "pptx" {
                        let deck = try await APIClient.shared.downloadAuthenticated(path: "workflow-executions/\(executionId)/artifacts/\(artifact.id)/download", expectedHash: artifact.contentHash)
                        guard workflowActivities.isCurrent(scope) else { return }
                        downloadURL = try InboxFileManager.shared.storePrivateFile(deck, sourceId: artifact.id, revision: artifact.metadata.artifactVersion ?? 1, filename: "\(artifact.title).pptx")
                        guard let previewId = artifact.metadata.previewArtifactId, let previewHash = artifact.metadata.previewContentHash else { throw APIError.network(artifact.metadata.previewError ?? "PPTX 已生成，但渲染预览不可用") }
                        let pdf = try await APIClient.shared.downloadAuthenticated(path: "workflow-executions/\(executionId)/artifacts/\(previewId)/download", expectedHash: previewHash)
                        guard workflowActivities.isCurrent(scope) else { return }
                        guard let document = PDFDocument(data: pdf) else { throw APIError.decoding("渲染预览不是有效 PDF") }; pdfDocument = document
                    } else if let previewId = artifact.metadata.previewArtifactId, let previewHash = artifact.metadata.previewContentHash {
                        let pdf = try await APIClient.shared.downloadAuthenticated(path: "workflow-executions/\(executionId)/artifacts/\(previewId)/download", expectedHash: previewHash)
                        guard workflowActivities.isCurrent(scope) else { return }
                        guard let document = PDFDocument(data: pdf) else { throw APIError.decoding("设计样稿预览不是有效 PDF") }; pdfDocument = document
                    } else if artifact.extension == "pdf" {
                        let pdf = try await APIClient.shared.downloadAuthenticated(path: "workflow-executions/\(executionId)/artifacts/\(artifact.id)/download", expectedHash: artifact.contentHash)
                        guard workflowActivities.isCurrent(scope) else { return }
                        guard let document = PDFDocument(data: pdf) else { throw APIError.decoding("预览不是有效 PDF") }; pdfDocument = document
                    } else {
                        if artifact.extension == "docx" {
                            let document = try await APIClient.shared.downloadAuthenticated(
                                path: "workflow-executions/\(executionId)/artifacts/\(artifact.id)/download",
                                expectedHash: artifact.contentHash
                            )
                            guard workflowActivities.isCurrent(scope) else { return }
                            downloadURL = try InboxFileManager.shared.storePrivateFile(
                                document,
                                sourceId: artifact.id,
                                revision: artifact.metadata.artifactVersion ?? 1,
                                filename: "\(artifact.title).docx"
                            )
                        }
                        let loaded = try await APIClient.shared.fetchWorkflowArtifactContent(executionId: executionId, artifactId: artifact.id).content
                        guard workflowActivities.isCurrent(scope) else { return }
                        content = loaded
                    }
                } catch {
                    guard workflowActivities.isCurrent(scope) else { return }
                    errorMessage = error.localizedDescription
                }
            }
        }
        .preferredColorScheme(.light)
    }
}

private struct PresentationOutlinePreview: View {
    struct Outline: Decodable { let title: String?; let slides: [Slide] }
    struct Slide: Decodable {
        let layout: String?
        let title: String?
        let purpose: String?
        let keyPoints: [String]?
        let evidence: [String]?
        let visual: String?

        enum CodingKeys: String, CodingKey {
            case layout, title, purpose, evidence, visual
            case keyPoints = "key_points"
        }
    }

    let outline: Outline

    static func decode(_ content: String) -> Outline? {
        try? JSONDecoder().decode(Outline.self, from: Data(content.utf8))
    }

    var body: some View {
        LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            if let title = outline.title { Text(title).font(AppTheme.Typography.screenTitle) }
            ForEach(Array(outline.slides.enumerated()), id: \.offset) { index, slide in
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(String(format: "%02d", index + 1))
                            .font(AppTheme.Typography.micro.monospacedDigit())
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                        Text(slide.title ?? "第 \(index + 1) 页").font(AppTheme.Typography.cardTitle)
                        Spacer()
                        Text(slide.layout ?? "").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary)
                    }
                    if let purpose = slide.purpose { Text(purpose).font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary) }
                    if let points = slide.keyPoints, !points.isEmpty { Label(points.joined(separator: "\n"), systemImage: "text.alignleft") }
                    if let evidence = slide.evidence, !evidence.isEmpty { Label(evidence.joined(separator: "\n"), systemImage: "checkmark.shield") }
                    if let visual = slide.visual, !visual.isEmpty { Label(visual, systemImage: "photo.on.rectangle") }
                }
                .font(AppTheme.Typography.supporting)
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.Colors.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(AppTheme.Colors.border) }
            }
        }
        .textSelection(.enabled)
    }
}

private struct PDFDeckView: UIViewRepresentable {
    let document: PDFDocument
    @Binding var currentPage: Int
    func makeCoordinator() -> Coordinator { Coordinator(currentPage: $currentPage) }
    func makeUIView(context: Context) -> UIStackView {
        let pdf = PDFView(); pdf.document = document; pdf.autoScales = true; pdf.displayMode = .singlePageContinuous; pdf.displayDirection = .vertical
        let thumbnails = PDFThumbnailView(); thumbnails.pdfView = pdf; thumbnails.thumbnailSize = CGSize(width: 72, height: 96); thumbnails.layoutMode = .vertical
        let stack = UIStackView(arrangedSubviews: [thumbnails, pdf]); stack.axis = .horizontal; thumbnails.widthAnchor.constraint(equalToConstant: 88).isActive = true
        context.coordinator.pdfView = pdf
        NotificationCenter.default.addObserver(context.coordinator, selector: #selector(Coordinator.pageChanged), name: .PDFViewPageChanged, object: pdf)
        return stack
    }
    func updateUIView(_ view: UIStackView, context: Context) {}
    final class Coordinator: NSObject {
        weak var pdfView: PDFView?; var currentPage: Binding<Int>
        init(currentPage: Binding<Int>) { self.currentPage = currentPage }
        @objc func pageChanged() { guard let pdf = pdfView, let page = pdf.currentPage else { return }; currentPage.wrappedValue = (pdf.document?.index(for: page) ?? 0) + 1 }
        deinit { NotificationCenter.default.removeObserver(self) }
    }
}

private struct WorkflowStatusBadge: View {
    let status: String
    var body: some View {
        Label(status.workflowStatusLabel, systemImage: status.workflowStatusIcon)
            .font(AppTheme.Typography.micro)
            .foregroundStyle(status.workflowStatusColor)
            .padding(.horizontal, AppTheme.Spacing.sm)
            .frame(minHeight: 28)
            .background(status.workflowStatusColor.opacity(0.12), in: Capsule())
    }
}

private struct WorkflowErrorBanner: View {
    let message: String
    var body: some View {
        Label(message, systemImage: "exclamationmark.triangle.fill")
            .font(AppTheme.Typography.supporting)
            .foregroundStyle(AppTheme.Colors.statusError)
            .padding(AppTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.statusError.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
    }
}

struct WorkflowFailureCard: View {
    let failure: WorkflowFailurePresentation

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Label("执行失败原因", systemImage: "exclamationmark.triangle.fill")
                .font(AppTheme.Typography.label)
                .foregroundStyle(AppTheme.Colors.statusError)
            Text(failure.cause)
                .font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textPrimary)
            Label("可执行操作：\(failure.action)", systemImage: "arrow.clockwise")
                .font(AppTheme.Typography.supporting.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.quantumBlue)
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.statusError.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("workflow-failure-cause")
    }
}

private extension String {
    var workflowCapabilityLabel: String {
        switch self {
        case "main_agent": return "Main · 智能编排"
        case "knowledge": return "Knowledge · 知识"
        case "coder": return "Coder · 开发"
        case "supervision": return "Supervision · 审查"
        default: return self
        }
    }
    var workflowStatusLabel: String {
        switch self {
        case "clarifying": return "需求澄清中"
        case "planning": return "生成计划中"
        case "needs_attention": return "规划需处理"
        case "awaiting_approval": return "待人工确认"
        case "building_agent": return "构建 Agent 中"
        case "agent_ready": return "Agent 待启动"
        case "ready": return "已就绪"
        case "queued": return "排队中"
        case "running": return "执行中"
        case "awaiting_review": return "待成果复核"
        case "completed", "succeeded": return "已完成"
        case "failed": return "执行失败"
        case "cancelled": return "已取消"
        case "pending": return "等待中"
        case "skipped": return "已跳过"
        default: return self
        }
    }
    var workflowStatusIcon: String {
        switch self {
        case "running", "planning", "building_agent": return "waveform"
        case "needs_attention": return "exclamationmark.arrow.triangle.2.circlepath"
        case "clarifying": return "bubble.left.and.text.bubble.right"
        case "agent_ready": return "person.crop.circle.badge.checkmark"
        case "awaiting_approval", "awaiting_review": return "person.badge.clock"
        case "completed", "succeeded": return "checkmark.circle.fill"
        case "failed": return "exclamationmark.triangle.fill"
        case "cancelled": return "xmark.circle.fill"
        default: return "clock"
        }
    }
    var workflowStatusColor: Color {
        switch self {
        case "running", "planning", "building_agent", "clarifying", "queued": return AppTheme.Colors.statusRunning
        case "awaiting_approval", "awaiting_review": return AppTheme.Colors.securityYellow
        case "completed", "succeeded", "ready", "agent_ready": return AppTheme.Colors.statusCompleted
        case "failed", "needs_attention": return AppTheme.Colors.statusError
        default: return AppTheme.Colors.statusIdle
        }
    }
}
