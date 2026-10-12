import SwiftUI
import Combine
import OSLog

// Session ownership and lifecycle transport shared by chat and the current renderer.
// Workflow pages are implemented only in TravelSpace; obsolete native pages are removed.

struct WorkflowSummaryCard: View {
    let workflow: WorkflowDTO
    var showsChevron = true

    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            Image(systemName: WorkflowDetailTransitionPolicy.isTravel(workflow) ? "book.closed" : "doc.text")
                .font(.system(size: 22, weight: .regular))
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .frame(width: 46, height: 46)
                .background(.white.opacity(0.45), in: Circle())
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 8) {
                Text(workflow.title)
                    .font(.custom(AppTheme.Typography.editorialName, size: 21, relativeTo: .title3))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text(workflow.description.split(separator: "\n").first.map(String.init) ?? workflow.desiredOutput)
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineLimit(2)
                WorkflowStatusBadge(status: workflow.latestExecution?.status ?? workflow.status)
            }
            Spacer(minLength: 0)
            if showsChevron {
                Image(systemName: "chevron.right").font(.system(size: 15))
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
        }
        .padding(20)
        .quantumCard()
        .accessibilityElement(children: .combine)
        .accessibilityHint("打开任务的新界面")
    }
}

enum WorkflowDetailTransitionPolicy {
    static func isTravel(_ workflow: WorkflowDTO) -> Bool {
        workflow.desiredOutput.contains("旅行") || workflow.desiredOutput.contains("旅游攻略")
    }

    static func travelBrief(destination: String, dates: String, travelers: String, preferences: String) -> String {
        [("目的地", destination), ("出行时间", dates), ("同行人", travelers), ("偏好与预算", preferences)]
            .filter { !$0.1.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            .map { "\($0.0)：\($0.1.trimmingCharacters(in: .whitespacesAndNewlines))" }
            .joined(separator: "\n")
    }

    static func showsLifecycleSession(status: String, hasExecution: Bool) -> Bool {
        !hasExecution && ["clarifying", "awaiting_requirement_confirmation", "planning", "building_agent", "needs_attention"].contains(status)
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


@MainActor
public final class WorkflowClarificationModel: ObservableObject {
    let workflowId: String
    @Published var snapshot: WorkflowClarificationSnapshotDTO?
    @Published var events: [WorkflowLifecycleEventDTO] = []
    @Published var isLoading = false
    @Published var isSubmitting = false
    @Published var errorMessage: String?
    @Published var connectionState: String = "idle"
    @Published var attachments: [DocumentReceiptDTO] = []
    @Published var isUploadingAttachment = false
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

    func attach(_ url: URL) async {
        guard scopeIsCurrent, !isUploadingAttachment else { return }
        isUploadingAttachment = true
        defer { if scopeIsCurrent { isUploadingAttachment = false } }
        do {
            let receipt = try await APIClient.shared.uploadDocument(at: url)
            guard scopeIsCurrent else { return }
            if !attachments.contains(where: { $0.sourceId == receipt.sourceId }) { attachments.append(receipt) }
        } catch {
            if scopeIsCurrent { errorMessage = error.localizedDescription }
        }
    }

    func respond(_ response: String) async {
        guard scopeIsCurrent,
              (!response.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !attachments.isEmpty) else { return }
        isSubmitting = true
        if response.hasPrefix("确认") || response.contains("进入方案") {
            optimisticPlanningMessage = "规划请求已提交到云端，离开此页不会中断"
        }
        defer {
            if scopeIsCurrent { isSubmitting = false }
        }
        do {
            _ = try await APIClient.shared.respondToWorkflowClarification(
                workflowId: workflowId, response: response,
                sourceRefs: attachments.map(WorkflowSourceReference.init), expectedRound: snapshot?.session.roundNumber
            )
            guard scopeIsCurrent else { return }
            attachments = []
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


struct PresentationProductStep {
    static let labels = ["需求确认", "全稿预览", "下载"]

    static func currentIndex(executionStatus: String) -> Int {
        executionStatus == "completed" ? 2 : 1
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


struct TravelWorkflowBriefCard: View {
    let content: String
    var title: String = "已带入的旅行需求"
    private var input: CapabilityProposalInput {
        TravelPlanPreferencesView.draft(title: "旅行", context: content)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label(title, systemImage: "suitcase.rolling")
                .font(AppTheme.Typography.cardTitle).foregroundStyle(AppTheme.Colors.primary)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), alignment: .leading)], alignment: .leading, spacing: 12) {
                fact("目的地", icon: "mappin.and.ellipse", value: input.destination)
                fact("出行时间", icon: "calendar", value: input.travelDates)
                fact("同行人", icon: "person.2", value: input.travelers)
                fact("偏好与预算", icon: "heart", value: input.travelPreferences)
            }
            DisclosureGroup {
                Text(content).font(AppTheme.Typography.supporting).lineSpacing(5)
                    .foregroundStyle(AppTheme.Colors.textSecondary).textSelection(.enabled)
                    .padding(.top, 8)
            } label: {
                Label("查看完整需求与聊天依据", systemImage: "text.alignleft")
                    .font(AppTheme.Typography.micro)
            }
            .accessibilityIdentifier("travel-original-requirements")
        }
        .padding(16)
        .quantumCard()
        .tint(AppTheme.Colors.primary)
        .accessibilityIdentifier("travel-workflow-brief")
    }

    private func fact(_ label: String, icon: String, value: String?) -> some View {
        let text = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let pending = text.isEmpty || text.contains("待确认") || text.contains("尚未决定")
        return VStack(alignment: .leading, spacing: 8) {
            Label(label, systemImage: icon).font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.primary)
            Text(pending ? "待补充" : text).font(AppTheme.Typography.supporting.weight(.semibold))
                .foregroundStyle(pending ? AppTheme.Colors.textSecondary : AppTheme.Colors.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            Text(pending ? "尚未确认" : "已带入")
                .font(.system(size: 10, weight: .medium)).foregroundStyle(AppTheme.Colors.primary)
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(AppTheme.Colors.surfaceTint, in: Capsule())
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(12)
        .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
    }
}
