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
                                WorkflowDashboardHeader(onCreate: { showingCreate = true })
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
            .navigationTitle("")
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
                Text("说清想要的结果，Quantum 会帮你澄清、规划，再由你确认启动。")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .multilineTextAlignment(.center)
            }

            Button("创建第一个工作流", systemImage: "plus") { showingCreate = true }
                .buttonStyle(QuantumPrimaryButtonStyle())
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

private struct WorkflowDashboardHeader: View {
    let onCreate: () -> Void
    @State private var filter = "全部"

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            ZStack(alignment: .leading) {
                Image("knowledge_home_hero")
                    .resizable()
                    .scaledToFill()
                    .frame(height: 232)
                    .clipped()
                LinearGradient(
                    colors: [Color.black.opacity(0.04), Color(hex: "284044").opacity(0.68)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        QuantumAvatarView(size: 28)
                        Text("QUANTUM · FLOW")
                            .font(.caption2.weight(.bold))
                            .tracking(1.5)
                    }
                    .padding(.horizontal, 12)
                    .frame(height: 40)
                    .background(.ultraThinMaterial, in: Capsule())
                    Spacer()
                    Text("把一个想法，\n变成能完成的计划。")
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                    Button(action: onCreate) {
                        Label("新建任务", systemImage: "plus")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .frame(maxWidth: .infinity, minHeight: 48)
                            .background(Color.white.opacity(0.94), in: Capsule())
                    }
                    .buttonStyle(SoftButtonStyle())
                }
                .padding(AppTheme.Spacing.lg)
            }
            .frame(height: 232)
            .clipShape(RoundedRectangle(cornerRadius: 30, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 30, style: .continuous)
                    .stroke(Color.white.opacity(0.76), lineWidth: 0.8)
            }
            .shadow(color: Color(hex: "385A58").opacity(0.12), radius: 20, y: 8)

            Picker("任务筛选", selection: $filter) {
                Text("全部").tag("全部")
                Text("进行中").tag("进行中")
                Text("已完成").tag("已完成")
            }
            .pickerStyle(.segmented)
        }
    }
}

private struct QuantumWorkflowBackground: View {
    var body: some View {
        QuantumMistBackground()
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

struct WorkflowSummaryCard: View {
    let workflow: WorkflowDTO
    var showsChevron = true

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: summaryIcon)
                    .font(.system(size: 19, weight: .semibold))
                    .foregroundStyle(summaryTint)
                    .frame(width: 44, height: 44)
                    .background(Color.white.opacity(0.72), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 3) {
                    Text(workflow.title)
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text(workflow.description.isEmpty ? workflow.desiredOutput : workflow.description)
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(2)
                }
                Spacer(minLength: AppTheme.Spacing.xs)
                WorkflowStatusBadge(status: workflow.latestExecution?.status ?? workflow.status)
                if showsChevron {
                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppTheme.Icons.tertiary)
                }
            }

            HStack(spacing: 0) {
                ForEach(Array(phaseLabels.enumerated()), id: \.offset) { index, label in
                    VStack(spacing: 5) {
                        Circle()
                            .fill(index <= phaseIndex ? summaryTint : AppTheme.Colors.border)
                            .frame(width: index == phaseIndex ? 9 : 7, height: index == phaseIndex ? 9 : 7)
                        Text(label)
                            .font(.system(size: 9, weight: index == phaseIndex ? .bold : .medium))
                            .foregroundStyle(index <= phaseIndex ? AppTheme.Colors.textSecondary : AppTheme.Colors.textTertiary)
                    }
                    .frame(maxWidth: .infinity)
                    if index < phaseLabels.count - 1 {
                        Rectangle()
                            .fill(index < phaseIndex ? summaryTint.opacity(0.52) : AppTheme.Colors.border)
                            .frame(height: 1)
                            .offset(y: -7)
                    }
                }
            }

            Label(workflow.desiredOutput, systemImage: "doc.badge.arrow.up")
                .font(AppTheme.Typography.micro.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .lineLimit(1)
        }
        .padding(AppTheme.Spacing.lg)
        .background(
            LinearGradient(
                colors: [summaryTint.opacity(0.13), AppTheme.Colors.cardBackground],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.xl, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.xl).stroke(Color.white.opacity(0.86), lineWidth: 0.8) }
        .shadow(color: summaryTint.opacity(0.10), radius: 16, y: 7)
        .accessibilityElement(children: .combine)
    }

    private let phaseLabels = ["澄清", "规划", "准备", "执行"]

    private var phaseIndex: Int {
        let status = workflow.latestExecution?.status ?? workflow.status
        switch status {
        case "clarifying": return 0
        case "planning", "awaiting_approval", "needs_attention": return 1
        case "building_agent", "agent_ready", "ready": return 2
        default: return 3
        }
    }

    private var summaryIcon: String {
        if workflowText.contains("旅行") { return "airplane.departure" }
        if workflowText.contains("ppt") || workflowText.contains("演示") { return "rectangle.on.rectangle.angled" }
        return "sparkles.rectangle.stack"
    }

    private var summaryTint: Color {
        workflowText.contains("旅行") ? AppTheme.Colors.statusCompleted : AppTheme.Colors.quantumViolet
    }

    private var workflowText: String {
        "\(workflow.title) \(workflow.description) \(workflow.desiredOutput)".lowercased()
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
    @State private var outputKind = "document"
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                        Text("想完成什么？")
                            .font(.system(size: 30, weight: .semibold, design: .serif))

                        TextField("例如：写一篇关于人工智能的课程论文…", text: $description, axis: .vertical)
                            .lineLimit(6...8)
                            .padding(AppTheme.Spacing.lg)
                            .frame(minHeight: 160, alignment: .top)
                            .quantumCard()

                        Text("输出形式").font(AppTheme.Typography.label)
                        HStack(spacing: AppTheme.Spacing.sm) {
                            compactOutputPreset(title: "报告", icon: "doc.text", kind: "document", deliverable: "研究报告（Markdown）")
                            compactOutputPreset(title: "PPT", icon: "rectangle.on.rectangle", kind: "presentation", deliverable: "可编辑 PPTX 与渲染预览")
                            compactOutputPreset(title: "旅行计划", icon: "airplane.departure", kind: "general", deliverable: "图文旅行计划，可确认后转为旅行笔记或 PDF")
                        }

                        Text("参考资料（可选）").font(AppTheme.Typography.label)
                        Button(action: {}) {
                            VStack(spacing: AppTheme.Spacing.sm) {
                                Image(systemName: "doc.badge.plus")
                                Text("添加资料").font(AppTheme.Typography.label)
                                Text("支持 PDF、图片、链接等")
                                    .font(AppTheme.Typography.micro)
                                    .foregroundStyle(AppTheme.Colors.textTertiary)
                            }
                            .frame(maxWidth: .infinity, minHeight: 110)
                            .overlay {
                                RoundedRectangle(cornerRadius: AppTheme.Radius.md)
                                    .stroke(AppTheme.Colors.border, style: StrokeStyle(lineWidth: 1, dash: [5]))
                            }
                        }
                        .buttonStyle(SoftButtonStyle())

                        if let errorMessage {
                            WorkflowErrorBanner(message: errorMessage)
                        }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                    .padding(.bottom, AppTheme.Spacing.xxl)
                }
            }
            .safeAreaInset(edge: .bottom) {
                Button(isSubmitting ? "正在生成…" : "生成计划", action: submit)
                    .buttonStyle(QuantumPrimaryButtonStyle())
                    .disabled(description.trimmingCharacters(in: .whitespacesAndNewlines).count < 3 || isSubmitting)
                    .padding(AppTheme.Metrics.contentGutter)
                    .background(.ultraThinMaterial)
            }
            .navigationTitle("新建任务")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                        .disabled(isSubmitting)
                }
            }
            .interactiveDismissDisabled(isSubmitting)
        }
    }

    private func compactOutputPreset(title: String, icon: String, kind: String, deliverable: String) -> some View {
        Button {
            outputKind = kind
            output = deliverable
        } label: {
            VStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: icon).font(.title3)
                Text(title).font(AppTheme.Typography.supporting)
            }
            .foregroundStyle(output == deliverable ? AppTheme.Icons.interactive : AppTheme.Colors.textSecondary)
            .frame(maxWidth: .infinity, minHeight: 76)
            .background(output == deliverable ? AppTheme.Colors.surfaceTint : AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.md)
                    .stroke(output == deliverable ? AppTheme.Icons.interactive : AppTheme.Colors.border, lineWidth: output == deliverable ? 1.5 : 0.75)
            }
        }
        .buttonStyle(SoftButtonStyle())
    }

    private func outputPreset(
        title: String,
        detail: String,
        icon: String,
        kind: String,
        deliverable: String
    ) -> some View {
        Button {
            outputKind = kind
            output = deliverable
        } label: {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: icon)
                    .font(.headline)
                    .foregroundStyle(output == deliverable ? AppTheme.Colors.onPrimary : AppTheme.Colors.quantumViolet)
                    .frame(width: 44, height: 44)
                    .background(output == deliverable ? AppTheme.Colors.quantumBlue : AppTheme.Colors.mistLilac, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                    Text(title).font(AppTheme.Typography.cardTitle)
                    Text(detail)
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .multilineTextAlignment(.leading)
                }
                Spacer(minLength: AppTheme.Spacing.sm)
                Image(systemName: output == deliverable ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(output == deliverable ? AppTheme.Colors.quantumBlue : AppTheme.Colors.textTertiary)
            }
            .padding(AppTheme.Spacing.md)
            .frame(maxWidth: .infinity, minHeight: 76, alignment: .leading)
            .background(AppTheme.Colors.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(output == deliverable ? AppTheme.Colors.quantumBlue : AppTheme.Colors.border, lineWidth: output == deliverable ? 1.5 : 0.75)
            }
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityAddTraits(output == deliverable ? .isSelected : [])
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
                let deliverable = output
                let created = try await APIClient.shared.createWorkflow(
                    title: title.isEmpty ? String(description.prefix(24)) : title,
                    description: description, desiredOutput: deliverable,
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
        ZStack {
            QuantumMistBackground()
            VStack(spacing: 0) {
                WorkflowSummaryCard(workflow: current, showsChevron: false)
                    .padding(.horizontal, AppTheme.Metrics.contentGutter)
                    .padding(.vertical, AppTheme.Spacing.md)

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
    @State private var showingCanvas = false
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
        .sheet(isPresented: $showingCanvas) {
            if plan != nil {
                WorkflowCanvasEditor(plan: planBinding, agents: tenantAgents, onSave: save)
            }
        }
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
                Button("画布", systemImage: "point.3.connected.trianglepath.dotted") {
                    showingCanvas = true
                }
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

struct WorkflowCompactPlanView: View {
    let title: String
    @Binding var nodes: [WorkflowPlanNodeDTO]
    var primaryButtonTitle: String = "确认并构建 Agent"
    var onPrimary: () -> Void = {}
    @State private var editingIndex: Int?

    var body: some View {
        ZStack {
            QuantumMistBackground()
            VStack(spacing: 0) {
                workflowHeader("计划预览")
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        HStack(spacing: AppTheme.Spacing.md) {
                            Image(systemName: "doc.text.fill")
                                .font(.title2)
                                .foregroundStyle(AppTheme.Icons.interactive)
                                .frame(width: 48, height: 48)
                                .background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                            VStack(alignment: .leading, spacing: 3) {
                                Text(title).font(AppTheme.Typography.sectionTitle)
                                Text("\(nodes.count) 个步骤 · 约 3.5 小时")
                                    .font(AppTheme.Typography.supporting)
                                    .foregroundStyle(AppTheme.Colors.textSecondary)
                            }
                        }

                        VStack(spacing: 0) {
                            ForEach(nodes.indices, id: \.self) { index in
                                Button { editingIndex = index } label: {
                                    HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                                        VStack(spacing: 0) {
                                            Text("\(index + 1)")
                                                .font(AppTheme.Typography.label)
                                                .foregroundStyle(.white)
                                                .frame(width: 30, height: 30)
                                                .background(stepColor(index), in: Circle())
                                            if index < nodes.count - 1 {
                                                Rectangle().fill(AppTheme.Colors.border).frame(width: 1, height: 76)
                                            }
                                        }
                                        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                                            HStack {
                                                Text(nodes[index].name ?? "未命名步骤")
                                                    .font(AppTheme.Typography.label)
                                                    .foregroundStyle(AppTheme.Colors.textPrimary)
                                                Spacer()
                                                Image(systemName: "ellipsis")
                                                    .foregroundStyle(AppTheme.Icons.secondary)
                                            }
                                            HStack {
                                                Label(agentName(nodes[index].parameters.agentId), systemImage: "person.crop.circle.badge.checkmark")
                                                Spacer()
                                                Text(stepDuration(index))
                                            }
                                            .font(AppTheme.Typography.micro)
                                            .foregroundStyle(AppTheme.Colors.textSecondary)
                                        }
                                        .padding(AppTheme.Spacing.md)
                                        .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                                    }
                                }
                                .buttonStyle(SoftButtonStyle())
                            }
                        }
                    }
                    .padding(AppTheme.Spacing.lg)
                }
                Button(action: onPrimary) {
                    Label(primaryButtonTitle, systemImage: "play.fill")
                }
                .buttonStyle(QuantumPrimaryButtonStyle())
                .padding(AppTheme.Spacing.lg)
                .background(.ultraThinMaterial)
            }
        }
        .fullScreenCover(isPresented: Binding(
            get: { editingIndex != nil },
            set: { if !$0 { editingIndex = nil } }
        )) {
            if let editingIndex {
                WorkflowStepEditView(node: $nodes[editingIndex], onDismiss: { self.editingIndex = nil })
            }
        }
    }

    private func workflowHeader(_ title: String) -> some View {
        HStack {
            Image(systemName: "chevron.left").minimumTouchTarget()
            Spacer()
            Text(title).font(AppTheme.Typography.cardTitle)
            Spacer()
            Image(systemName: "ellipsis").minimumTouchTarget()
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(.thinMaterial)
    }

    private func stepColor(_ index: Int) -> Color {
        [AppTheme.Colors.quantumBlue, Color(hex: "8494AE"), Color(hex: "7288A8"), AppTheme.Colors.quantumViolet, Color(hex: "42B7AE")][index % 5]
    }

    private func agentName(_ id: String?) -> String {
        switch id {
        case "knowledge": return "文献助手"
        case "writer": return "写作助手"
        case "reviewer": return "润色助手"
        default: return "研究助手"
        }
    }

    private func stepDuration(_ index: Int) -> String {
        ["30 分钟", "1 小时", "1 小时", "45 分钟", "45 分钟"][index % 5]
    }
}

struct WorkflowStepEditView: View {
    @Binding var node: WorkflowPlanNodeDTO
    let onDismiss: () -> Void
    @State private var showingAgentFlow = false

    var body: some View {
        ZStack {
            QuantumMistBackground()
            VStack(spacing: 0) {
                HStack {
                    Button(action: onDismiss) { Image(systemName: "chevron.left").minimumTouchTarget() }
                    Spacer()
                    Text("编辑步骤").font(AppTheme.Typography.cardTitle)
                    Spacer()
                    Menu {
                        Button("上移", systemImage: "arrow.up") {}
                        Button("下移", systemImage: "arrow.down") {}
                        Button("删除步骤", systemImage: "trash", role: .destructive) {}
                    } label: { Image(systemName: "ellipsis").minimumTouchTarget() }
                }
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm)
                .background(.thinMaterial)

                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                        field("步骤标题") {
                            TextField("步骤标题", text: Binding(get: { node.name ?? "" }, set: { node.name = $0 }))
                        }
                        field("执行指令") {
                            TextField(
                                "说明这个步骤需要完成什么",
                                text: Binding(
                                    get: { node.parameters.instruction ?? node.parameters.query ?? "" },
                                    set: { node.parameters.instruction = $0; node.parameters.query = nil }
                                ),
                                axis: .vertical
                            )
                            .lineLimit(5...8)
                        }
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                            Text("执行智能体").font(AppTheme.Typography.label)
                            Button { showingAgentFlow = true } label: {
                                HStack {
                                    Label(agentTitle, systemImage: "person.crop.circle.badge.checkmark")
                                    Spacer()
                                    Image(systemName: "chevron.right")
                                }
                                .padding(AppTheme.Spacing.md)
                                .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                            }
                            .buttonStyle(SoftButtonStyle())
                        }
                        DisclosureGroup("高级设置") { Text("网络、知识范围与审核策略").font(AppTheme.Typography.supporting) }
                            .padding(AppTheme.Spacing.md)
                            .quantumCard()
                    }
                    .padding(AppTheme.Spacing.lg)
                }
                VStack(spacing: AppTheme.Spacing.sm) {
                    Button("修改一句话") {}
                        .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.minimumTouchTarget)
                        .buttonStyle(.bordered)
                    Button("确认执行", action: onDismiss)
                        .buttonStyle(QuantumPrimaryButtonStyle())
                }
                .padding(AppTheme.Spacing.lg)
                .background(.ultraThinMaterial)
            }
        }
        .fullScreenCover(isPresented: $showingAgentFlow) {
            WorkflowAgentSelectionFlow(selectedAgentID: agentBinding)
        }
    }

    private var agentBinding: Binding<String> {
        Binding(get: { node.parameters.agentId ?? "knowledge" }, set: { node.parameters.agentId = $0 })
    }

    private var agentTitle: String {
        WorkflowAgentSelectionFlow.title(for: node.parameters.agentId ?? "knowledge")
    }

    private func field<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Text(label).font(AppTheme.Typography.label)
            content()
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(AppTheme.Colors.border) }
        }
    }
}

struct WorkflowAgentSelectionFlow: View {
    enum Stage { case picker, preview, configuration, test }

    @Binding var selectedAgentID: String
    @State private var stage: Stage
    @Environment(\.dismiss) private var dismiss

    init(selectedAgentID: Binding<String>, initialStage: Stage = .picker) {
        self._selectedAgentID = selectedAgentID
        _stage = State(initialValue: initialStage)
    }

    static func title(for id: String) -> String {
        agents.first(where: { $0.id == id })?.name ?? "文献助手"
    }

    private static let agents = [
        (id: "knowledge", name: "文献助手", detail: "检索、阅读与综述", icon: "doc.text.fill", tint: Color(hex: "356BFF")),
        (id: "writer", name: "写作助手", detail: "论文撰写与写作", icon: "pencil.and.outline", tint: Color(hex: "7454F5")),
        (id: "analyst", name: "数据分析师", detail: "数据处理与可视化", icon: "chart.bar.xaxis", tint: Color(hex: "16A6C9")),
        (id: "coach", name: "思维教练", detail: "梳理思路与论证", icon: "lightbulb.fill", tint: Color(hex: "8C4BE8")),
        (id: "translator", name: "翻译助手", detail: "多语种文献翻译", icon: "globe", tint: Color(hex: "2196F3")),
        (id: "slides", name: "PPT 助手", detail: "演示文稿生成", icon: "rectangle.on.rectangle", tint: Color(hex: "5050E8")),
    ]

    var body: some View {
        ZStack {
            QuantumMistBackground()
            VStack(spacing: 0) {
                HStack {
                    Button { if stage == .picker { dismiss() } else { stage = previousStage } } label: {
                        Image(systemName: stage == .picker ? "xmark" : "chevron.left").minimumTouchTarget()
                    }
                    Spacer()
                    Text(stageTitle).font(AppTheme.Typography.cardTitle)
                    Spacer()
                    Image(systemName: "ellipsis").minimumTouchTarget()
                }
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm)
                .background(.thinMaterial)

                switch stage {
                case .picker: picker
                case .preview: preview
                case .configuration: configuration
                case .test: testResult
                }
            }
        }
    }

    private var stageTitle: String {
        switch stage {
        case .picker: return "选择智能体"
        case .preview: return "智能体预览"
        case .configuration: return "配置参与方式"
        case .test: return "测试与替换"
        }
    }

    private var previousStage: Stage {
        switch stage {
        case .picker: return .picker
        case .preview: return .picker
        case .configuration: return .preview
        case .test: return .configuration
        }
    }

    private var selectedAgent: (id: String, name: String, detail: String, icon: String, tint: Color) {
        Self.agents.first(where: { $0.id == selectedAgentID }) ?? Self.agents[0]
    }

    private var picker: some View {
        ScrollView {
            VStack(spacing: AppTheme.Spacing.sm) {
                Text("为“文献检索与阅读”选择合适的智能体")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                TextField("搜索智能体", text: .constant(""))
                    .padding(AppTheme.Spacing.md)
                    .background(AppTheme.Colors.cardBackground, in: Capsule())
                HStack { ForEach(["全部", "学术研究", "写作编辑", "数据分析"], id: \.self) { Text($0).font(AppTheme.Typography.micro).padding(8).background(AppTheme.Colors.surfaceTint, in: Capsule()) } }
                    .frame(maxWidth: .infinity, alignment: .leading)
                ForEach(Self.agents, id: \.id) { agent in
                    Button {
                        selectedAgentID = agent.id
                        stage = .preview
                    } label: {
                        HStack(spacing: AppTheme.Spacing.md) {
                            Image(systemName: agent.icon)
                                .foregroundStyle(agent.tint)
                                .frame(width: 44, height: 44)
                                .background(agent.tint.opacity(0.10), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                            VStack(alignment: .leading, spacing: 3) {
                                Text(agent.name).font(AppTheme.Typography.label)
                                Text(agent.detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                            }
                            Spacer()
                            Label("可用", systemImage: "circle.fill")
                                .labelStyle(.titleOnly)
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(AppTheme.Icons.success)
                            Image(systemName: selectedAgentID == agent.id ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(selectedAgentID == agent.id ? AppTheme.Icons.interactive : AppTheme.Icons.tertiary)
                        }
                        .padding(AppTheme.Spacing.md)
                        .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(selectedAgentID == agent.id ? AppTheme.Icons.interactive : AppTheme.Colors.border) }
                    }
                    .buttonStyle(SoftButtonStyle())
                }
            }
            .padding(AppTheme.Spacing.lg)
        }
    }

    private var preview: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                agentHeader(status: "可用")
                section("擅长") {
                    ForEach(["精准检索高质量文献", "快速阅读与提炼要点", "生成结构化综述"], id: \.self) { Label($0, systemImage: "checkmark").foregroundStyle(AppTheme.Icons.success) }
                }
                section("知识来源") { flowLabels(["学术数据库", "知网", "PubMed", "arXiv", "更多"]) }
                section("可用工具") { flowLabels(["文献检索", "PDF 阅读", "文献管理"]) }
                section("示例输出") { Label("生成的文献综述示例", systemImage: "doc.text.fill") }
                VStack(alignment: .leading) { Text("综合评价").font(AppTheme.Typography.label); Text("4.8 / 5.0").font(.title.weight(.bold)) }
            }
            .padding(AppTheme.Spacing.lg)
        }
        .safeAreaInset(edge: .bottom) {
            HStack {
                Button("试着聊一句") {}
                    .buttonStyle(.bordered)
                Button("用于此步骤") { stage = .configuration }
                    .buttonStyle(.borderedProminent)
            }
            .controlSize(.large)
            .padding(AppTheme.Spacing.lg)
            .background(.ultraThinMaterial)
        }
    }

    private var configuration: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                agentHeader(status: "已选择")
                numberedField(1, "负责什么", "检索近三年有关人工智能教育应用的高质量文献，并提炼核心观点。")
                numberedField(2, "读取哪些输入", "研究方向\n前序步骤的笔记")
                numberedField(3, "可使用工具", "文献检索  ·  PDF 阅读  ·  文献管理")
                numberedField(4, "交付什么", "文献列表、摘要和关键观点总结。")
                DisclosureGroup("可选：设置使用边界") { Text("仅使用公开文献，不编造来源。") }
                    .padding(AppTheme.Spacing.md).quantumCard()
            }
            .padding(AppTheme.Spacing.lg)
        }
        .safeAreaInset(edge: .bottom) {
            Button("保存并测试") { stage = .test }
                .buttonStyle(QuantumPrimaryButtonStyle())
                .padding(AppTheme.Spacing.lg)
                .background(.ultraThinMaterial)
        }
    }

    private var testResult: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                agentHeader(status: "测试完成")
                section("运行结果预览") {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        Label("人工智能在教育中的应用：近三年研究综述", systemImage: "doc.text.fill")
                            .font(AppTheme.Typography.label)
                        Text("PDF · 12 页").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                        Text("基于 32 篇高质量文献，本文从教学场景、学习效果和伦理风险三个维度，梳理了人工智能在教育中的应用现状与未来趋势……")
                            .font(AppTheme.Typography.supporting)
                    }
                    .padding(AppTheme.Spacing.md).quantumCard()
                }
                section("下一步交付给") { Label("写作助手", systemImage: "pencil.and.outline") }
                Label("测试结果符合预期，可继续执行。", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(AppTheme.Icons.success)
                    .padding(AppTheme.Spacing.md)
                    .background(AppTheme.Icons.success.opacity(0.08), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                HStack { Button("保留") { dismiss() }; Button("换一个") { stage = .picker } }
                    .buttonStyle(.bordered)
                Button("比较结果") {}
                    .buttonStyle(QuantumPrimaryButtonStyle())
            }
            .padding(AppTheme.Spacing.lg)
        }
    }

    private func agentHeader(status: String) -> some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: selectedAgent.icon)
                .font(.title2).foregroundStyle(selectedAgent.tint)
                .frame(width: 52, height: 52)
                .background(selectedAgent.tint.opacity(0.10), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            VStack(alignment: .leading) {
                Text(selectedAgent.name).font(AppTheme.Typography.sectionTitle)
                Text(selectedAgent.detail).font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
            }
            Spacer()
            Label(status, systemImage: "circle.fill").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Icons.success)
        }
    }

    private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) { Text(title).font(AppTheme.Typography.label); content() }
    }

    private func flowLabels(_ labels: [String]) -> some View {
        HStack { ForEach(labels, id: \.self) { Text($0).font(AppTheme.Typography.micro).padding(8).background(AppTheme.Colors.surfaceTint, in: Capsule()) } }
    }

    private func numberedField(_ number: Int, _ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Label(title, systemImage: "\(number).circle.fill").font(AppTheme.Typography.label)
            Text(value).font(AppTheme.Typography.supporting).padding(AppTheme.Spacing.md).frame(maxWidth: .infinity, alignment: .leading).quantumCard()
        }
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
    @State private var showingAgentPreview = false
    @State private var showingAgentSelection = false

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
                Button { showingAgentSelection = true } label: {
                    HStack {
                        Label(
                            WorkflowAgentSelectionFlow.title(for: node.parameters.agentId ?? "knowledge"),
                            systemImage: "person.crop.circle.badge.checkmark"
                        )
                        Spacer()
                        Image(systemName: "chevron.right")
                    }
                }
                .buttonStyle(SoftButtonStyle())
                Button("预览与试跑", systemImage: "play.square.stack") {
                    showingAgentPreview = true
                }
                .font(AppTheme.Typography.supporting.weight(.semibold))
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
        .sheet(isPresented: $showingAgentPreview) {
            WorkflowAgentPreview(
                agent: agents.first(where: { $0.id == node.parameters.agentId }),
                fallbackID: node.parameters.agentId ?? "main_agent",
                instruction: node.parameters.instruction ?? node.parameters.query ?? ""
            )
            .presentationDetents([.medium, .large])
        }
        .fullScreenCover(isPresented: $showingAgentSelection) {
            WorkflowAgentSelectionFlow(
                selectedAgentID: Binding(
                    get: { node.parameters.agentId ?? "knowledge" },
                    set: { node.parameters.agentId = $0 }
                )
            )
        }
    }
}

private struct WorkflowAgentPreview: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss
    let agent: TenantAgentDTO?
    let fallbackID: String
    let instruction: String

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    HStack(spacing: AppTheme.Spacing.md) {
                        Image(systemName: "cpu")
                            .font(.title2)
                            .foregroundStyle(AppTheme.Colors.quantumViolet)
                            .frame(width: 56, height: 56)
                            .background(AppTheme.Colors.mistLilac, in: RoundedRectangle(cornerRadius: 16))
                        VStack(alignment: .leading, spacing: 4) {
                            Text(agent?.customName ?? fallbackID).font(AppTheme.Typography.sectionTitle)
                            Text("参与当前节点").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                    }

                    capability("任务职责", agent?.privatePromptDelta ?? "按节点要求完成工作")
                    capability("当前节点要求", instruction.isEmpty ? "暂未配置" : instruction)
                    capability("知识访问", agent?.subscribedKnowledgePacks.isEmpty == false ? agent!.subscribedKnowledgePacks.joined(separator: "、") : "继承工作流知识范围")
                    capability("工具能力", agent?.allowedTools?.isEmpty == false ? agent!.allowedTools!.joined(separator: "、") : "无额外工具")

                    Button("在 Chat 中试跑", systemImage: "play.fill") {
                        dismiss()
                        appState.openChat(
                            agentId: agent?.id ?? fallbackID,
                            agentName: agent?.customName ?? fallbackID,
                            prompt: instruction.isEmpty ? "请用一个简短示例展示你的能力" : instruction
                        )
                    }
                    .buttonStyle(QuantumPrimaryButtonStyle())
                    .controlSize(.large)
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .navigationTitle("智能体能力预览")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("完成") { dismiss() } }
        }
    }

    private func capability(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Text(title).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
            Text(value).font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textPrimary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(AppTheme.Colors.border) }
    }
}

// MARK: - ComfyUI-style workflow canvas backed by the existing plan DSL

private struct WorkflowCanvasEditor: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var plan: WorkflowPlanDTO
    let agents: [TenantAgentDTO]
    let onSave: () -> Void

    @State private var showingLibrary = false
    @State private var showingConnectionEditor = false
    @State private var selectedNodeID: String?
    @State private var selectedNodeIDs: Set<String> = []
    @State private var scale: CGFloat = 1
    @State private var canvasNotice: String?

    init(
        plan: Binding<WorkflowPlanDTO>,
        agents: [TenantAgentDTO],
        onSave: @escaping () -> Void,
        prototypeStage: Int? = nil
    ) {
        _plan = plan
        self.agents = agents
        self.onSave = onSave
        let ids = plan.wrappedValue.dsl.nodes.map(\.id)
        _showingLibrary = State(initialValue: prototypeStage == 2)
        _showingConnectionEditor = State(initialValue: prototypeStage == 3)
        _selectedNodeIDs = State(initialValue: Set(ids.prefix(prototypeStage == 4 ? 3 : (prototypeStage == 3 ? 2 : 0))))
    }

    var body: some View {
        NavigationStack {
            ZStack(alignment: .bottom) {
                QuantumMistBackground()
                canvas
                if !selectedNodeIDs.isEmpty { batchBar }
            }
            .navigationTitle(plan.dsl.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("关闭") { dismiss() }
                }
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button("添加", systemImage: "plus") { showingLibrary = true }
                    Button("运行", systemImage: "play.fill") {
                        onSave()
                        dismiss()
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .sheet(isPresented: $showingLibrary) { nodeLibrary }
            .sheet(isPresented: $showingConnectionEditor) {
                if selectedNodes.count == 2 {
                    WorkflowCanvasConnectionEditor(
                        plan: $plan,
                        sourceID: selectedNodes[0].id,
                        targetID: selectedNodes[1].id
                    )
                    .presentationDetents([.medium])
                }
            }
            .sheet(isPresented: Binding(
                get: { selectedNodeID != nil && selectedNodeIDs.isEmpty },
                set: { if !$0 { selectedNodeID = nil } }
            )) {
                if let id = selectedNodeID,
                   let index = plan.dsl.nodes.firstIndex(where: { $0.id == id }) {
                    WorkflowCanvasNodeInspector(node: $plan.dsl.nodes[index], agents: agents)
                        .presentationDetents([.medium, .large])
                }
            }
            .alert("工作流画布", isPresented: Binding(
                get: { canvasNotice != nil },
                set: { if !$0 { canvasNotice = nil } }
            )) {
                Button("知道了") { canvasNotice = nil }
            } message: {
                Text(canvasNotice ?? "")
            }
        }
    }

    private var canvas: some View {
        GeometryReader { proxy in
            let contentSize = CGSize(
                width: max(proxy.size.width, 430),
                height: max(proxy.size.height, CGFloat(plan.dsl.nodes.count) * 122 + 96)
            )
            let points = nodePoints(in: contentSize)
            ScrollView([.horizontal, .vertical]) {
                ZStack {
                    Canvas { context, _ in
                        for edge in plan.dsl.edges {
                            guard let from = points[edge.source], let to = points[edge.target] else { continue }
                            var path = Path()
                            path.move(to: CGPoint(x: from.x + 55, y: from.y))
                            path.addCurve(
                                to: CGPoint(x: to.x - 55, y: to.y),
                                control1: CGPoint(x: from.x + 95, y: from.y),
                                control2: CGPoint(x: to.x - 95, y: to.y)
                            )
                            context.stroke(path, with: .color(AppTheme.Colors.quantumBlue.opacity(0.78)), lineWidth: 2)
                        }
                    }
                    ForEach(plan.dsl.nodes) { node in
                        WorkflowCanvasNode(
                            node: node,
                            isSelected: selectedNodeIDs.contains(node.id),
                            action: { select(node.id) }
                        )
                        .position(points[node.id] ?? .zero)
                        .simultaneousGesture(LongPressGesture().onEnded { _ in
                            selectedNodeID = nil
                            selectedNodeIDs.insert(node.id)
                        })
                    }
                }
                .frame(width: contentSize.width, height: contentSize.height)
                .scaleEffect(scale)
            }
            .overlay(alignment: .bottomTrailing) { minimap }
            .overlay(alignment: .bottomLeading) { zoomControls }
        }
        .padding(.bottom, selectedNodeIDs.isEmpty ? 0 : 112)
    }

    private func nodePoints(in size: CGSize) -> [String: CGPoint] {
        Dictionary(uniqueKeysWithValues: plan.dsl.nodes.enumerated().map { index, node in
            let left = max(76, size.width * 0.26)
            let right = min(size.width - 76, size.width * 0.72)
            return (node.id, CGPoint(x: index.isMultiple(of: 2) ? left : right, y: 92 + CGFloat(index) * 112))
        })
    }

    private func select(_ id: String) {
        if selectedNodeIDs.isEmpty {
            selectedNodeID = id
        } else if selectedNodeIDs.remove(id) == nil {
            selectedNodeIDs.insert(id)
        }
    }

    private var zoomControls: some View {
        HStack(spacing: 12) {
            Button { scale = max(0.72, scale - 0.1) } label: { Image(systemName: "minus") }
            Text("\(Int(scale * 100))%").font(AppTheme.Typography.micro.monospacedDigit())
            Button { scale = min(1.2, scale + 0.1) } label: { Image(systemName: "plus") }
        }
        .padding(.horizontal, 12).frame(height: 44)
        .background(.ultraThinMaterial, in: Capsule())
        .padding()
    }

    private var minimap: some View {
        RoundedRectangle(cornerRadius: 12)
            .fill(AppTheme.Colors.cardBackground.opacity(0.9))
            .frame(width: 88, height: 66)
            .overlay {
                HStack(spacing: 5) {
                    ForEach(0..<min(plan.dsl.nodes.count, 5), id: \.self) { index in
                        RoundedRectangle(cornerRadius: 2)
                            .fill(index.isMultiple(of: 2) ? AppTheme.Colors.mistMint : AppTheme.Colors.mistLilac)
                            .frame(width: 9, height: 9)
                    }
                }
            }
            .overlay { RoundedRectangle(cornerRadius: 12).stroke(AppTheme.Colors.border) }
            .padding()
    }

    private var batchBar: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("已选择 \(selectedNodeIDs.count) 个节点").font(AppTheme.Typography.cardTitle)
                Spacer()
                Button { selectedNodeIDs.removeAll() } label: { Image(systemName: "xmark") }
            }
            HStack {
                batchAction("运行", "play.fill") {
                    onSave()
                    dismiss()
                }
                batchAction("禁用", "pause.fill") {
                    canvasNotice = "现有工作流 DSL 没有节点启停字段。为避免伪造保存结果，本次升级保留现有数据结构，不写入无效状态。"
                }
                batchAction("复制", "square.on.square", action: copySelectedNodes)
                batchAction("连接", "point.3.connected.trianglepath.dotted") {
                    showingConnectionEditor = true
                }
                .disabled(selectedNodeIDs.count != 2)
                Button(role: .destructive) {
                    plan.dsl.edges.removeAll {
                        selectedNodeIDs.contains($0.source) || selectedNodeIDs.contains($0.target)
                    }
                    plan.dsl.nodes.removeAll { selectedNodeIDs.contains($0.id) }
                    selectedNodeIDs.removeAll()
                } label: { Label("删除", systemImage: "trash") }
                .labelStyle(.iconOnly)
                .frame(maxWidth: .infinity, minHeight: 44)
            }
        }
        .padding(AppTheme.Spacing.lg)
        .background(.ultraThinMaterial)
        .clipShape(UnevenRoundedRectangle(topLeadingRadius: 24, topTrailingRadius: 24))
    }

    private func batchAction(_ title: String, _ icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { Label(title, systemImage: icon) }
            .labelStyle(.iconOnly)
            .frame(maxWidth: .infinity, minHeight: 44)
            .accessibilityLabel(title)
    }

    private var nodeLibrary: some View {
        NavigationStack {
            ScrollView {
                LazyVGrid(columns: [.init(.adaptive(minimum: 92))], spacing: 18) {
                    ForEach(nodeTemplates, id: \.0) { item in
                        Button { addNode(type: item.0, name: item.1); showingLibrary = false } label: {
                            VStack(spacing: 10) {
                                Image(systemName: item.2)
                                    .font(.title2)
                                    .foregroundStyle(item.3)
                                    .frame(width: 52, height: 52)
                                    .background(item.3.opacity(0.1), in: RoundedRectangle(cornerRadius: 14))
                                Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textPrimary)
                            }
                        }
                    }
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .navigationTitle("添加节点")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium])
    }

    private var nodeTemplates: [(String, String, String, Color)] {
        [
            ("AGENT", "Agent", "cpu", AppTheme.Colors.quantumViolet),
            ("KNOWLEDGE_SEARCH", "知识检索", "books.vertical.fill", AppTheme.Colors.quantumBlue),
            ("PROMPT_TRANSFORM", "信息整理", "leaf.fill", AppTheme.Colors.statusCompleted),
            ("IMAGE_GENERATION", "图像生成", "photo.fill", AppTheme.Colors.quantumViolet),
            ("HUMAN_REVIEW", "人工审核", "person.fill", AppTheme.Colors.emberOrange),
            ("OUTPUT", "输出", "doc.fill", AppTheme.Colors.quantumBlue)
        ]
    }

    private func addNode(type: String, name: String) {
        plan.dsl.nodes.append(WorkflowPlanNodeDTO(
            id: "custom_\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())",
            nodeType: type,
            name: name,
            parameters: WorkflowNodeParametersDTO(agentId: type == "AGENT" ? "main_agent" : nil)
        ))
    }

    private var selectedNodes: [WorkflowPlanNodeDTO] {
        plan.dsl.nodes.filter { selectedNodeIDs.contains($0.id) }
    }

    private func copySelectedNodes() {
        let copies = selectedNodes.map { node in
            WorkflowPlanNodeDTO(
                id: "copy_\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())",
                nodeType: node.nodeType,
                name: "\(node.name ?? node.nodeType) 副本",
                parameters: node.parameters
            )
        }
        plan.dsl.nodes.append(contentsOf: copies)
        selectedNodeIDs = Set(copies.map(\.id))
    }
}

private struct WorkflowCanvasNode: View {
    let node: WorkflowPlanNodeDTO
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.headline)
                    .foregroundStyle(tint)
                    .frame(width: 28)
                VStack(alignment: .leading, spacing: 3) {
                    Text(node.name ?? node.nodeType).font(AppTheme.Typography.label).lineLimit(1)
                    Text(node.parameters.agentId ?? subtitle).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary).lineLimit(1)
                }
                Circle().fill(AppTheme.Colors.cardBackground).frame(width: 8, height: 8)
                    .overlay { Circle().stroke(tint, lineWidth: 2) }
            }
            .foregroundStyle(AppTheme.Colors.textPrimary)
            .padding(12)
            .frame(width: 132, height: 72, alignment: .leading)
            .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 14))
            .overlay { RoundedRectangle(cornerRadius: 14).stroke(isSelected ? AppTheme.Colors.quantumBlue : tint.opacity(0.48), lineWidth: isSelected ? 2.5 : 1) }
            .shadow(color: tint.opacity(0.12), radius: 14, y: 6)
        }
        .buttonStyle(.plain)
    }

    private var icon: String {
        switch node.nodeType {
        case "AGENT": "cpu"
        case "KNOWLEDGE_SEARCH": "books.vertical.fill"
        case "IMAGE_GENERATION": "photo.fill"
        case "HUMAN_REVIEW": "person.fill"
        case "OUTPUT": "doc.fill"
        default: "leaf.fill"
        }
    }

    private var tint: Color {
        switch node.nodeType {
        case "KNOWLEDGE_SEARCH", "OUTPUT": AppTheme.Colors.quantumBlue
        case "HUMAN_REVIEW": AppTheme.Colors.emberOrange
        case "PROMPT_TRANSFORM": AppTheme.Colors.statusCompleted
        default: AppTheme.Colors.quantumViolet
        }
    }

    private var subtitle: String { node.nodeType.replacingOccurrences(of: "_", with: " ").lowercased() }
}

private struct WorkflowCanvasConnectionEditor: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var plan: WorkflowPlanDTO
    @State private var sourceID: String
    @State private var targetID: String

    init(plan: Binding<WorkflowPlanDTO>, sourceID: String, targetID: String) {
        _plan = plan
        _sourceID = State(initialValue: sourceID)
        _targetID = State(initialValue: targetID)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("连接") {
                    LabeledContent("从", value: nodeName(sourceID))
                    LabeledContent("到", value: nodeName(targetID))
                    Button("交换方向", systemImage: "arrow.up.arrow.down") {
                        swap(&sourceID, &targetID)
                    }
                }
                Section("传递内容") {
                    TextField("例如：检索结果", text: conditionBinding)
                }
            }
            .navigationTitle("连接设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") {
                        upsertEdge()
                        dismiss()
                    }
                }
            }
        }
    }

    private var conditionBinding: Binding<String> {
        Binding(
            get: {
                plan.dsl.edges.first { $0.source == sourceID && $0.target == targetID }?.condition ?? ""
            },
            set: { value in
                upsertEdge(condition: value)
            }
        )
    }

    private func nodeName(_ id: String) -> String {
        plan.dsl.nodes.first { $0.id == id }?.name ?? id
    }

    private func upsertEdge(condition: String? = nil) {
        let value = condition?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let index = plan.dsl.edges.firstIndex(where: { $0.source == sourceID && $0.target == targetID }) {
            if condition != nil { plan.dsl.edges[index].condition = value?.isEmpty == false ? value : nil }
        } else {
            plan.dsl.edges.append(WorkflowPlanEdgeDTO(
                source: sourceID,
                target: targetID,
                condition: value?.isEmpty == false ? value : nil
            ))
        }
    }
}

private struct WorkflowCanvasNodeInspector: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var node: WorkflowPlanNodeDTO
    let agents: [TenantAgentDTO]

    var body: some View {
        NavigationStack {
            Form {
                Section("节点") {
                    TextField("名称", text: Binding(get: { node.name ?? "" }, set: { node.name = $0 }))
                    LabeledContent("类型", value: node.nodeType)
                }
                if node.nodeType == "AGENT" || node.parameters.agentId != nil {
                    Section("智能体") {
                        Picker("参与者", selection: Binding(get: { node.parameters.agentId ?? "main_agent" }, set: { node.parameters.agentId = $0 })) {
                            Text("主智能体").tag("main_agent")
                            ForEach(agents) { Text($0.customName ?? $0.id).tag($0.id) }
                        }
                    }
                }
                Section("输入与输出") {
                    TextField("节点执行要求", text: Binding(
                        get: { node.parameters.instruction ?? node.parameters.query ?? "" },
                        set: { node.parameters.instruction = $0; node.parameters.query = nil }
                    ), axis: .vertical)
                    TextField("输出格式", text: Binding(get: { node.parameters.outputFormat ?? "" }, set: { node.parameters.outputFormat = $0 }))
                }
                Section {
                    Toggle("需要人工确认", isOn: Binding(get: { node.parameters.requiresReview ?? false }, set: { node.parameters.requiresReview = $0 }))
                    Toggle("允许联网", isOn: Binding(get: { node.parameters.allowNetwork ?? false }, set: { node.parameters.allowNetwork = $0 }))
                }
            }
            .navigationTitle("节点设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("完成") { dismiss() } }
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
    @State private var savedTravelNote = false
    @State private var showingTravelNoteSave = false
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var workflowActivities: WorkflowActivityCoordinator

    private var isTravelArtifact: Bool {
        if artifact.metadata.renderType == "travel_plan_v1" { return true }
        let value = "\(artifact.title) \(artifact.kind) \(content?.prefix(300) ?? "")"
        return value.contains("旅行") || value.localizedCaseInsensitiveContains("travel")
    }

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
                    } else if isTravelArtifact {
                        TravelPlanResultView(title: artifact.title, content: content)
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
                if allowsDownload {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        if isTravelArtifact, content != nil {
                            Button(savedTravelNote ? "已存入旅行笔记" : "存为旅行笔记", systemImage: savedTravelNote ? "checkmark.circle.fill" : "book.closed") {
                                showingTravelNoteSave = true
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(savedTravelNote)
                        }
                        if let downloadURL {
                            ShareLink(item: downloadURL) {
                                Label("导出 \(artifact.extension.uppercased())", systemImage: "square.and.arrow.up")
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(.ultraThinMaterial)
                }
            }
            .sheet(isPresented: $showingTravelNoteSave) {
                TravelNoteSaveSheet(title: artifact.title, content: content ?? "") { title, body in
                    if KnowledgeNoteStore.shared.createNote(
                        title: title,
                        body: body,
                        tags: ["旅行", "workflow"]
                    ) != nil {
                        savedTravelNote = true
                    }
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

#if DEBUG
struct V4WorkflowPrototypeHost: View {
    let pageID: String
    @State private var nodes = Self.fixtureNodes
    @State private var selectedAgentID = "knowledge"

    var body: some View {
        if pageID.hasPrefix("v4/04-workflow-simple-plan-v4-") {
            simpleWorkflowPage
        } else {
            WorkflowAgentSelectionFlow(
                selectedAgentID: $selectedAgentID,
                initialStage: agentStage
            )
        }
    }

    @ViewBuilder
    private var simpleWorkflowPage: some View {
        if pageID.hasSuffix("p02") {
            WorkflowCreateSheet { _ in }
        } else if pageID.hasSuffix("p03") {
            WorkflowCompactPlanView(
                title: "毕业论文写作",
                nodes: $nodes,
                primaryButtonTitle: "开始执行"
            )
        } else if pageID.hasSuffix("p04") {
            WorkflowStepEditView(node: $nodes[1], onDismiss: {})
        } else {
            ZStack {
                QuantumMistBackground()
                ScrollView {
                    LazyVStack(spacing: AppTheme.Spacing.md) {
                        WorkflowDashboardHeader(onCreate: {})
                        ForEach(Self.fixtureWorkflows) { workflow in
                            WorkflowSummaryCard(workflow: workflow)
                        }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                    .padding(.bottom, 80)
                }
                .safeAreaInset(edge: .bottom) {
                    HStack {
                        Label("首页", systemImage: "house.fill")
                        Spacer()
                        Label("阅读", systemImage: "doc.text")
                        Spacer()
                        Label("工作流", systemImage: "rectangle.stack.fill")
                            .foregroundStyle(AppTheme.Icons.interactive)
                        Spacer()
                        Label("我的", systemImage: "person.fill")
                    }
                    .labelStyle(.iconOnly)
                    .font(.title3)
                    .padding(.horizontal, 36)
                    .padding(.vertical, AppTheme.Spacing.md)
                    .background(.ultraThinMaterial)
                }
            }
        }
    }

    private var agentStage: WorkflowAgentSelectionFlow.Stage {
        if pageID.hasSuffix("p02") { return .preview }
        if pageID.hasSuffix("p03") { return .configuration }
        if pageID.hasSuffix("p04") { return .test }
        return .picker
    }

    private static let fixtureNodes: [WorkflowPlanNodeDTO] = [
        node("direction", "确定研究方向", "research"),
        node("literature", "文献检索与阅读", "knowledge", "检索近三年高质量文献，并阅读摘要，提炼与研究方向相关的核心观点。"),
        node("outline", "整理笔记与提纲", "research"),
        node("draft", "撰写初稿", "writer"),
        node("review", "修改与润色", "reviewer"),
    ]

    private static func node(_ id: String, _ name: String, _ agentID: String, _ instruction: String = "") -> WorkflowPlanNodeDTO {
        WorkflowPlanNodeDTO(
            id: id,
            nodeType: "PROMPT_TRANSFORM",
            name: name,
            parameters: WorkflowNodeParametersDTO(agentId: agentID, instruction: instruction)
        )
    }

    private static let fixtureWorkflows: [WorkflowDTO] = [
        workflow("thesis", "毕业论文写作", "完成毕业论文", "研究报告（Markdown）", "running"),
        workflow("slides", "课程演示 PPT", "准备课程演示", "可编辑 PPTX", "completed"),
        workflow("travel", "日本旅行计划", "完成日本旅行规划", "图文旅行计划", "completed"),
        workflow("reading", "量子力学阅读", "系统阅读量子力学", "阅读笔记", "paused"),
    ]

    private static func workflow(_ id: String, _ title: String, _ description: String, _ output: String, _ status: String) -> WorkflowDTO {
        WorkflowDTO(
            id: id,
            title: title,
            description: description,
            desiredOutput: output,
            status: status,
            activePlanId: nil,
            clarificationSessionId: nil,
            sourceClientSessionId: nil,
            primaryAgentId: nil,
            createdAt: nil,
            updatedAt: nil,
            latestExecution: nil,
            agent: nil
        )
    }
}

struct V4CanvasPrototypeHost: View {
    let pageID: String
    @State private var plan = Self.fixturePlan

    var body: some View {
        WorkflowCanvasEditor(
            plan: $plan,
            agents: [],
            onSave: {},
            prototypeStage: pageID.hasSuffix("p02") ? 2 : (pageID.hasSuffix("p03") ? 3 : (pageID.hasSuffix("p04") ? 4 : 1))
        )
    }

    private static let fixturePlan: WorkflowPlanDTO = {
        let data = #"{"id":"travel-plan","workflowId":"travel","version":1,"goal":"生成京都旅行攻略","deliverable":"图文旅行攻略","allowNetwork":true,"maxTokens":12000,"estimatedTokens":6200,"knowledgeScope":["旅行资料"],"validationErrors":[],"contentHash":"preview","activationRevision":1,"dsl":{"planId":"travel-plan","name":"旅行攻略生成","nodes":[{"id":"trigger","nodeType":"TRIGGER","name":"触发","parameters":{}},{"id":"agent","nodeType":"AGENT","name":"Agent","parameters":{"agentId":"旅行规划"}},{"id":"knowledge","nodeType":"KNOWLEDGE_SEARCH","name":"知识检索","parameters":{"query":"京都旅行资料"}},{"id":"organize","nodeType":"PROMPT_TRANSFORM","name":"信息整理","parameters":{"instruction":"生成行程"}},{"id":"image","nodeType":"IMAGE_GENERATION","name":"图像生成","parameters":{"instruction":"攻略封面"}},{"id":"review","nodeType":"HUMAN_REVIEW","name":"人工审核","parameters":{"requiresReview":true}},{"id":"output","nodeType":"OUTPUT","name":"输出","parameters":{"outputFormat":"旅行攻略"}}],"edges":[{"source":"trigger","target":"agent"},{"source":"knowledge","target":"agent"},{"source":"knowledge","target":"organize"},{"source":"organize","target":"image"},{"source":"organize","target":"review"},{"source":"review","target":"output"}],"version":"1.0.0"}}"#.data(using: .utf8)!
        return try! JSONDecoder().decode(WorkflowPlanDTO.self, from: data)
    }()
}

struct V4NodeEvaluationPrototypeHost: View {
    let pageID: String

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    switch stage {
                    case 1: overview
                    case 2: inputs
                    case 3: execution
                    default: comparison
                    }
                }
                .padding(AppTheme.Metrics.contentGutter)
                .padding(.bottom, 76)
            }
            .background { QuantumMistBackground() }
            .navigationTitle(["", "写作生成", "输入配置", "执行与输出", "A/B 评估"][stage])
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("更多", systemImage: "ellipsis") {}.labelStyle(.iconOnly) } }
            .safeAreaInset(edge: .bottom) { bottomAction }
        }
    }

    private var stage: Int {
        pageID.hasSuffix("p02") ? 2 : (pageID.hasSuffix("p03") ? 3 : (pageID.hasSuffix("p04") ? 4 : 1))
    }

    @ViewBuilder private var overview: some View {
        HStack(spacing: 14) {
            Image(systemName: "pencil.and.outline").font(.largeTitle).foregroundStyle(AppTheme.Colors.quantumViolet)
                .frame(width: 66, height: 66).background(AppTheme.Colors.mistLilac, in: RoundedRectangle(cornerRadius: 18))
            VStack(alignment: .leading, spacing: 5) {
                HStack { Text("写作生成").font(AppTheme.Typography.sectionTitle); Text("LLM").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.quantumViolet).padding(6).background(AppTheme.Colors.mistLilac, in: Capsule()) }
                Text("基于资料生成结构化内容").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
            }
        }
        field("节点名称", value: "写作生成")
        cardRow("节点类型", "内容生成", "生成、改写、总结等文本内容", "pencil.and.outline", AppTheme.Colors.quantumViolet)
        cardRow("分配的智能体", "GPT-4o", "擅长长文本写作与结构化输出", "brain.head.profile", AppTheme.Colors.textPrimary)
        field("节点说明", value: "根据研究资料生成一篇结构清晰、论证充分的文章。")
        sectionTitle("预览能力", trailing: "试试这个节点")
        Text("基于上传的研究资料，写一篇关于“大学生的高效学习方法”的文章。")
            .font(AppTheme.Typography.supporting).padding().frame(maxWidth: .infinity, alignment: .leading).background(AppTheme.Colors.selectionTint, in: RoundedRectangle(cornerRadius: 14))
    }

    @ViewBuilder private var inputs: some View {
        sectionTitle("上游输入", trailing: "从上游选择")
        inputRow("研究资料", "来自节点 1 · 资料检索", true, false)
        inputRow("用户要求", "来自开始节点", true, false)
        inputRow("参考资料", "未连接上游节点", false, true)
        Button("添加上游输入", systemImage: "plus") {}.buttonStyle(SoftButtonStyle()).frame(maxWidth: .infinity)
        sectionTitle("知识范围")
        cardRow("知识范围", "学习与教育", "2 个知识库 · 3,421 篇内容", "cube.fill", AppTheme.Colors.quantumBlue)
        sectionTitle("文件与数据")
        cardRow("上传文件", "大学生学习方法研究.pdf", "2.4 MB", "doc.fill", AppTheme.Colors.quantumBlue)
        Label("仍有 1 项输入未连接", systemImage: "exclamationmark.triangle.fill")
            .foregroundStyle(AppTheme.Colors.statusError).padding().frame(maxWidth: .infinity, alignment: .leading).background(AppTheme.Colors.dangerSurface, in: RoundedRectangle(cornerRadius: 14))
    }

    @ViewBuilder private var execution: some View {
        setting("执行指令", "请基于提供的资料，撰写一篇结构清晰、论证充分、适合大学生阅读的文章。", "doc.text")
        setting("工具与权限", "联网搜索 · 知识库检索", "wrench.and.screwdriver")
        setting("运行参数", "最大 Token 8,000 · 最长运行 3 分钟", "slider.horizontal.3")
        setting("重试策略", "失败时最多重试 2 次", "arrow.clockwise")
        HStack { Label("人工把关", systemImage: "person"); Spacer(); Toggle("", isOn: .constant(true)).labelsHidden() }
            .padding().background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 14))
        setting("输出格式", "标题、摘要、正文、参考文献", "doc")
        setting("交付目标", "输出到 节点 4 · 评估", "paperplane")
    }

    @ViewBuilder private var comparison: some View {
        setting("测试用例", "请写一篇关于“大学生的高效学习方法”的文章，要求结构清晰、可操作性强。", "doc.text")
        HStack(alignment: .top, spacing: 10) {
            resultCard("A", "方案 A", "GPT-4o", "大学生的高效学习方法", AppTheme.Colors.statusCompleted)
            resultCard("B", "方案 B", "Claude 3.5", "构建可持续的学习体系", AppTheme.Colors.quantumViolet)
        }
        Text("维度对比").font(AppTheme.Typography.cardTitle)
        ForEach([("内容质量", 0.90, 0.84), ("结构逻辑", 0.94, 0.86), ("实用性", 0.86, 0.92), ("创新性", 0.76, 0.88)], id: \.0) { item in
            HStack { Text(item.0).font(AppTheme.Typography.micro).frame(width: 58, alignment: .leading); ProgressView(value: item.1).tint(AppTheme.Colors.statusCompleted); ProgressView(value: item.2).tint(AppTheme.Colors.quantumViolet) }
        }
        .padding(.horizontal, 4)
        setting("主要差异", "B 在方法论和长期视角上更深入，但 A 更偏流程、操作性更强。", "waveform.path.ecg")
        Label("A 存在 1 个问题", systemImage: "exclamationmark.triangle.fill").foregroundStyle(AppTheme.Colors.statusWarning)
            .padding().frame(maxWidth: .infinity, alignment: .leading).background(AppTheme.Colors.warningSurface, in: RoundedRectangle(cornerRadius: 14))
    }

    private var bottomAction: some View {
        HStack {
            if stage == 4 {
                Button("选择 A") {}.buttonStyle(.bordered)
                Button("选择 B") {}.buttonStyle(.bordered)
                Button("再次测试", systemImage: "arrow.clockwise") {}.buttonStyle(.borderedProminent)
            } else {
                Button(stage == 1 ? "预览能力" : (stage == 3 ? "测试此节点" : "保存配置"), systemImage: "play.fill") {}
                    .buttonStyle(QuantumPrimaryButtonStyle()).controlSize(.large).frame(maxWidth: .infinity)
            }
        }
        .padding(.horizontal).padding(.vertical, 10).background(.ultraThinMaterial)
    }

    private func sectionTitle(_ title: String, trailing: String? = nil) -> some View {
        HStack { Text(title).font(AppTheme.Typography.cardTitle); Spacer(); if let trailing { Text(trailing).font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Icons.interactive) } }
    }

    private func field(_ title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 7) { Text(title).font(AppTheme.Typography.cardTitle); Text(value).font(AppTheme.Typography.supporting).padding().frame(maxWidth: .infinity, alignment: .leading).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 12)) }
    }

    private func cardRow(_ section: String, _ title: String, _ detail: String, _ icon: String, _ tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 7) { Text(section).font(AppTheme.Typography.cardTitle); HStack { Image(systemName: icon).foregroundStyle(tint).frame(width: 34); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "chevron.right").foregroundStyle(AppTheme.Icons.tertiary) }.padding().background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 12)) }
    }

    private func inputRow(_ title: String, _ detail: String, _ checked: Bool, _ warning: Bool) -> some View {
        HStack { Image(systemName: checked ? "checkmark.square.fill" : "square").foregroundStyle(checked ? AppTheme.Icons.interactive : AppTheme.Icons.tertiary); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(warning ? AppTheme.Colors.statusError : AppTheme.Colors.textSecondary) }; Spacer(); Text("文档列表").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Icons.interactive) }
            .padding().background(warning ? AppTheme.Colors.dangerSurface : AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 12))
    }

    private func setting(_ title: String, _ detail: String, _ icon: String) -> some View {
        HStack(alignment: .top) { Image(systemName: icon).foregroundStyle(AppTheme.Icons.interactive).frame(width: 28); VStack(alignment: .leading, spacing: 5) { Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "chevron.down").foregroundStyle(AppTheme.Icons.tertiary) }
            .padding().background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 14)).overlay { RoundedRectangle(cornerRadius: 14).stroke(AppTheme.Colors.border) }
    }

    private func resultCard(_ badge: String, _ title: String, _ model: String, _ answer: String, _ tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 9) { HStack { Text(badge).foregroundStyle(.white).frame(width: 28, height: 28).background(tint, in: Circle()); Text(title).font(AppTheme.Typography.label) }; Text(model).font(AppTheme.Typography.supporting); Divider(); Text(answer).font(AppTheme.Typography.supporting.weight(.semibold)); Text("在信息快速变化的时代，大学生需要更科学的学习方法来应对……").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary); Text("查看完整回答 〉").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Icons.interactive) }
            .padding().frame(maxWidth: .infinity, minHeight: 220, alignment: .topLeading).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 14)).overlay { RoundedRectangle(cornerRadius: 14).stroke(AppTheme.Colors.border) }
    }
}

struct V4SmartResearchPrototypeHost: View {
    let pageID: String

    var body: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        switch stage {
                        case 1: request
                        case 2: settings
                        case 3: outline
                        default: preview
                        }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                    .padding(.bottom, stage == 4 ? 16 : 72)
                }
            }
            .navigationTitle(stage == 2 ? "设置" : (stage == 3 ? "研究方案" : (stage == 4 ? "预览与导出" : "")))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    if stage < 3 { Button("取消") {} }
                    else { Button("更多", systemImage: "ellipsis") {}.labelStyle(.iconOnly) }
                }
            }
            .safeAreaInset(edge: .bottom) { footer }
        }
    }

    private var stage: Int {
        pageID.hasSuffix("p02") ? 2 : (pageID.hasSuffix("p03") ? 3 : (pageID.hasSuffix("p04") ? 4 : 1))
    }

    @ViewBuilder private var request: some View {
        Text("想研究什么？").font(.system(size: 30, weight: .semibold, design: .serif))
        Text("用 AI 帮你收集资料、分析整理，生成高质量研究报告或 PPT。")
            .font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
        Text("大学生心理健康现状及支持策略")
            .font(AppTheme.Typography.body).foregroundStyle(AppTheme.Colors.textSecondary)
            .padding().frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading).quantumCard()
        Text("输出形式").font(AppTheme.Typography.label)
        HStack(spacing: 12) {
            outputChoice("研究报告", "doc.text.fill", true)
            outputChoice("PPT", "rectangle.on.rectangle.angled", false)
        }
        Text("参考资料（可选）").font(AppTheme.Typography.label)
        VStack(spacing: 8) { Image(systemName: "plus.circle.fill").font(.title2).foregroundStyle(AppTheme.Icons.tertiary); Text("添加资料").font(AppTheme.Typography.label); Text("支持 PDF、图片、链接等").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }
            .frame(maxWidth: .infinity, minHeight: 120).overlay { RoundedRectangle(cornerRadius: 14).stroke(AppTheme.Colors.border, style: StrokeStyle(lineWidth: 1, dash: [5])) }
    }

    @ViewBuilder private var settings: some View {
        Text("确认研究设置").font(.system(size: 30, weight: .semibold, design: .serif))
        Text("简单设置，让结果更符合你的需求。").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
        choiceSection("目标读者", icon: "person", items: ["大学生", "教师", "公众", "自定义"], selected: 0)
        choiceSection("篇幅长度", icon: "doc", items: ["精简\n5–8页", "标准\n10–15页", "详细\n20–30页"], selected: 1)
        Text("视觉风格").font(AppTheme.Typography.label)
        HStack(spacing: 9) {
            styleChoice("清新简约", [AppTheme.Colors.mistSky, AppTheme.Colors.mistMint], true)
            styleChoice("学术专业", [AppTheme.Colors.mistMint, AppTheme.Colors.mistSky], false)
            styleChoice("生动现代", [AppTheme.Colors.mistLilac, AppTheme.Colors.mistRose], false)
        }
    }

    @ViewBuilder private var outline: some View {
        Text("研究大纲已生成").font(.system(size: 28, weight: .semibold, design: .serif))
        Text("共 6 个章节 · 基于 12 篇参考资料").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
        ProgressView(value: 0.3).tint(AppTheme.Colors.quantumBlue)
        HStack { Text("研究中… 正在整合资料与生成内容…").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary); Spacer(); Text("30%").font(AppTheme.Typography.micro) }
        ForEach(Array([("研究背景", "问题提出与研究意义"), ("国内外研究现状", "相关理论与现有成果"), ("研究方法", "数据来源与研究设计"), ("主要发现", "核心结果与分析"), ("讨论与建议", "对策建议与启示"), ("总结与展望", "研究结论与未来方向")].enumerated()), id: \.offset) { index, item in
            HStack(spacing: 12) { Image(systemName: "circle.grid.2x1.left.filled").foregroundStyle(AppTheme.Icons.tertiary); Text("\(index + 1)").foregroundStyle(.white).frame(width: 32, height: 32).background(index.isMultiple(of: 2) ? AppTheme.Colors.quantumBlue : AppTheme.Colors.statusCompleted, in: Circle()); VStack(alignment: .leading) { Text(item.0).font(AppTheme.Typography.label); Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "ellipsis") }
                .padding().background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 12)).overlay { RoundedRectangle(cornerRadius: 12).stroke(AppTheme.Colors.border) }
        }
    }

    @ViewBuilder private var preview: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("1 / 15").font(AppTheme.Typography.micro).foregroundStyle(.white).padding(.horizontal, 9).padding(.vertical, 5).background(AppTheme.Colors.textSecondary, in: Capsule())
            Text("大学生心理健康\n现状与支持策略").font(.system(size: 30, weight: .bold, design: .serif)).foregroundStyle(Color(hex: "163A72"))
            Text("关爱心灵 · 共建更好的大学生活").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
            Spacer()
            HStack(alignment: .bottom) { Image(systemName: "leaf.fill").font(.system(size: 64)).foregroundStyle(AppTheme.Colors.statusCompleted.opacity(0.55)); Spacer(); Image(systemName: "building.columns.fill").font(.system(size: 92)).foregroundStyle(AppTheme.Colors.quantumBlue.opacity(0.35)) }
        }
        .padding(22).frame(maxWidth: .infinity, minHeight: 360).background(LinearGradient(colors: [.white, AppTheme.Colors.mistSky], startPoint: .top, endPoint: .bottom), in: RoundedRectangle(cornerRadius: 16)).overlay { RoundedRectangle(cornerRadius: 16).stroke(AppTheme.Colors.border) }
        HStack(spacing: 8) { ForEach(1...5, id: \.self) { number in Text("\(number)").font(AppTheme.Typography.micro).frame(width: 62, height: 64).background(number == 1 ? AppTheme.Colors.selectionTint : AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 8)).overlay { RoundedRectangle(cornerRadius: 8).stroke(number == 1 ? AppTheme.Icons.interactive : AppTheme.Colors.border) } } }
        HStack { Label("参考资料", systemImage: "doc.text.fill").font(AppTheme.Typography.label); Spacer(); Text("12 篇").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary); Image(systemName: "chevron.right") }.padding().quantumCard()
        HStack { Image(systemName: "bubble.left"); Text("对当前幻灯片提出修改意见…").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary); Spacer(); Image(systemName: "arrow.up.circle.fill").foregroundStyle(AppTheme.Icons.interactive) }.padding().background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: 12))
        HStack(spacing: 8) { action("重新生成", "arrow.clockwise"); action("更换模板", "square.grid.2x2"); action("导出", "square.and.arrow.up"); action("分享", "shareplay") }
    }

    @ViewBuilder private var footer: some View {
        if stage < 4 {
            Button(action: {}) {
                if stage == 3 { Label("一键优化大纲", systemImage: "wand.and.stars") }
                else { Text(stage == 1 ? "下一步" : "开始研究") }
            }
                .buttonStyle(QuantumPrimaryButtonStyle()).controlSize(.large).frame(maxWidth: .infinity).padding().background(.ultraThinMaterial)
        }
    }

    private func outputChoice(_ title: String, _ icon: String, _ selected: Bool) -> some View {
        VStack(spacing: 9) { Image(systemName: icon).font(.title2); Text(title).font(AppTheme.Typography.label) }.foregroundStyle(selected ? AppTheme.Icons.interactive : AppTheme.Colors.textSecondary).frame(maxWidth: .infinity, minHeight: 92).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 12)).overlay { RoundedRectangle(cornerRadius: 12).stroke(selected ? AppTheme.Icons.interactive : AppTheme.Colors.border, lineWidth: selected ? 2 : 1) }
    }

    private func choiceSection(_ title: String, icon: String, items: [String], selected: Int) -> some View {
        VStack(alignment: .leading, spacing: 10) { Label(title, systemImage: icon).font(AppTheme.Typography.label); HStack(spacing: 8) { ForEach(Array(items.enumerated()), id: \.offset) { index, item in Text(item).font(AppTheme.Typography.micro).multilineTextAlignment(.center).foregroundStyle(index == selected ? AppTheme.Icons.interactive : AppTheme.Colors.textSecondary).frame(maxWidth: .infinity, minHeight: 48).background(index == selected ? AppTheme.Colors.selectionTint : AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: 12)).overlay { RoundedRectangle(cornerRadius: 12).stroke(index == selected ? AppTheme.Icons.interactive : .clear) } } } }
    }

    private func styleChoice(_ title: String, _ colors: [Color], _ selected: Bool) -> some View {
        VStack(spacing: 7) { LinearGradient(colors: colors, startPoint: .topLeading, endPoint: .bottomTrailing).frame(height: 72).clipShape(RoundedRectangle(cornerRadius: 10)); Text(title).font(AppTheme.Typography.micro) }.padding(5).frame(maxWidth: .infinity).overlay { RoundedRectangle(cornerRadius: 12).stroke(selected ? AppTheme.Icons.interactive : AppTheme.Colors.border, lineWidth: selected ? 2 : 1) }
    }

    private func action(_ title: String, _ icon: String) -> some View {
        VStack(spacing: 7) { Image(systemName: icon).font(.title3); Text(title).font(AppTheme.Typography.micro) }.foregroundStyle(AppTheme.Colors.textPrimary).frame(maxWidth: .infinity, minHeight: 72).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 12)).overlay { RoundedRectangle(cornerRadius: 12).stroke(AppTheme.Colors.border) }
    }
}

struct V3WorkflowExecutionPrototypeHost: View {
    let pageID: String

    var body: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        if page == 1 { running }
                        else if page == 2 { blocked }
                        else if page == 3 { review }
                        else { completed }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                    .padding(.bottom, 72)
                }
            }
            .navigationTitle(page == 3 ? "请你审核" : (page == 4 ? "任务已完成" : "智能研究"))
            .navigationBarTitleDisplayMode(.inline)
            .safeAreaInset(edge: .bottom) { footer }
        }
    }

    @ViewBuilder private var running: some View {
        Text("大学生心理健康现状\n与支持策略").font(.system(size: 28, weight: .semibold, design: .serif))
        Text("深度研究").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Icons.interactive).padding(7).background(AppTheme.Colors.selectionTint, in: Capsule())
        ForEach(Array([("理解任务", "分析问题、拆解研究方向", "1/1"), ("收集与分析资料", "正在阅读并整理相关文献…", "3/5"), ("生成初稿", "等待中", ""), ("优化与最终输出", "等待中", "")].enumerated()), id: \.offset) { index, item in
            HStack(alignment: .top, spacing: 12) { Image(systemName: index == 0 ? "checkmark.circle.fill" : (index == 1 ? "circle.inset.filled" : "circle")).foregroundStyle(index < 2 ? AppTheme.Icons.interactive : AppTheme.Icons.tertiary).font(.title3); VStack(alignment: .leading, spacing: 5) { HStack { Text(item.0).font(AppTheme.Typography.label); Spacer(); Text(item.2).font(AppTheme.Typography.micro) }; Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary); if index == 1 { ProgressView(value: 0.6).tint(AppTheme.Colors.quantumBlue) } } }.padding().background(index == 1 ? AppTheme.Colors.selectionTint : .clear, in: RoundedRectangle(cornerRadius: 12))
        }
        VStack(alignment: .leading, spacing: 8) { Text("当前智能体").font(AppTheme.Typography.micro); Label("学术研究助手　检索文献 · 文献分析 · 生成初稿", systemImage: "person.crop.circle.badge.checkmark").font(AppTheme.Typography.supporting) }.padding().quantumCard()
        Text("实时日志").font(AppTheme.Typography.cardTitle)
        Text("09:41　正在分析《大学生心理健康…》\n09:40　已获取 12 篇相关文献").font(.system(.caption, design: .monospaced)).foregroundStyle(AppTheme.Colors.textSecondary).lineSpacing(8)
    }

    @ViewBuilder private var blocked: some View {
        Label("收集与分析资料", systemImage: "exclamationmark.circle.fill").font(AppTheme.Typography.sectionTitle).foregroundStyle(AppTheme.Colors.statusError)
        VStack(spacing: 16) { Image(systemName: "doc.badge.exclamationmark.fill").font(.system(size: 62)).foregroundStyle(AppTheme.Colors.statusError); Text("未找到足够的相关文献").font(AppTheme.Typography.sectionTitle); Text("关键词“大学生心理健康干预效果”的搜索结果较少，建议调整关键词或扩大搜索范围。").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary).multilineTextAlignment(.center); Divider(); VStack(alignment: .leading, spacing: 8) { Text("可能的解决方案").font(AppTheme.Typography.label); Text("• 尝试使用更通用的关键词\n• 增加英文关键词进行检索\n• 放宽时间范围（如：最近 10 年）").font(AppTheme.Typography.supporting).lineSpacing(7) }.frame(maxWidth: .infinity, alignment: .leading) }.padding(AppTheme.Spacing.xl).background(AppTheme.Colors.dangerSurface, in: RoundedRectangle(cornerRadius: 18))
        Button("重试", systemImage: "arrow.clockwise") {}.buttonStyle(QuantumPrimaryButtonStyle()).controlSize(.large).frame(maxWidth: .infinity)
        Button("编辑输入", systemImage: "pencil") {}.buttonStyle(.bordered).frame(maxWidth: .infinity)
        Button("跳过此步骤", systemImage: "forward.end") {}.buttonStyle(.bordered).frame(maxWidth: .infinity)
    }

    @ViewBuilder private var review: some View {
        Text("研究初稿已生成").font(.system(size: 30, weight: .semibold, design: .serif))
        Text("请阅读并提出修改意见。").foregroundStyle(AppTheme.Colors.textSecondary)
        HStack { Image(systemName: "doc.text.fill").foregroundStyle(AppTheme.Icons.interactive).frame(width: 54, height: 54).background(AppTheme.Colors.selectionTint, in: RoundedRectangle(cornerRadius: 10)); VStack(alignment: .leading) { Text("大学生心理健康现状与支持策略研究").font(AppTheme.Typography.label); Text("约 8,600 字 · 2024年3月18日").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer() }.padding().quantumCard()
        Picker("", selection: .constant(0)) { Text("预览").tag(0); Text("目录").tag(1); Text("要点").tag(2) }.pickerStyle(.segmented)
        VStack(alignment: .leading, spacing: 12) { Text("一、研究背景").font(AppTheme.Typography.sectionTitle); Text("近年来，大学生心理健康问题日益受到关注。研究显示，学业压力、人际关系和未来发展的不确定性是主要影响因素……").lineSpacing(8); Divider(); HStack { Label("我", systemImage: "person.circle.fill"); Text("这段可以增加近三年的数据对比。").font(AppTheme.Typography.supporting); Spacer(); Image(systemName: "ellipsis") } }.padding().quantumCard()
        Button("查看全部批注（3）", systemImage: "chevron.right") {}.labelStyle(V3WorkflowTrailingLabelStyle())
        HStack { decision("通过", "checkmark", AppTheme.Colors.statusCompleted); decision("请求修改", "pencil", AppTheme.Colors.quantumBlue); decision("拒绝", "xmark", AppTheme.Colors.statusError) }
    }

    @ViewBuilder private var completed: some View {
        Image(systemName: "checkmark.circle.fill").font(.system(size: 72)).foregroundStyle(AppTheme.Colors.statusCompleted).frame(maxWidth: .infinity)
        Text("研究任务已完成").font(.system(size: 29, weight: .semibold, design: .serif)).frame(maxWidth: .infinity)
        Text("共生成 4 个成果，可在下方查看和使用。").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary).frame(maxWidth: .infinity)
        Picker("", selection: .constant(0)) { Text("成果").tag(0); Text("引用文献").tag(1); Text("任务信息").tag(2) }.pickerStyle(.segmented)
        artifact("研究报告", "大学生心理健康现状与支持策略", "PDF · 8.6 MB", "doc.text.fill", AppTheme.Colors.quantumBlue)
        artifact("演示文稿", "研究要点与建议", "PPTX · 12.4 MB", "rectangle.on.rectangle.angled", AppTheme.Colors.emberOrange)
        artifact("相关文件", "数据表格与图表", "ZIP · 4.1 MB", "tablecells", AppTheme.Colors.statusCompleted)
        artifact("引用文献", "共 28 篇参考文献", "RIS · 320 KB", "doc.plaintext", AppTheme.Colors.quantumViolet)
        HStack { action("预览", "eye"); action("下载", "arrow.down.to.line"); action("分享", "square.and.arrow.up"); action("保存到知识库", "archivebox") }
        Button("归档到书架", systemImage: "books.vertical") {}.buttonStyle(.bordered).frame(maxWidth: .infinity)
    }

    @ViewBuilder private var footer: some View {
        if page == 1 { HStack { Label("在后台运行", systemImage: "pause.fill"); Spacer(); Button("取消", role: .destructive) {} }.padding().background(.ultraThinMaterial) }
    }

    private var page: Int { Int(pageID.suffix(2)) ?? 1 }
    private func decision(_ title: String, _ icon: String, _ color: Color) -> some View { VStack { Image(systemName: icon).font(.title2); Text(title).font(AppTheme.Typography.micro) }.foregroundStyle(color).frame(maxWidth: .infinity, minHeight: 78).background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: 12)) }
    private func artifact(_ title: String, _ detail: String, _ meta: String, _ icon: String, _ color: Color) -> some View { HStack { Image(systemName: icon).font(.title2).foregroundStyle(color).frame(width: 50, height: 50).background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: 10)); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.micro); Text(meta).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "chevron.right") }.padding().quantumCard() }
    private func action(_ title: String, _ icon: String) -> some View { VStack { Image(systemName: icon); Text(title).font(AppTheme.Typography.micro) }.frame(maxWidth: .infinity, minHeight: 62).background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: 10)) }
}

struct V3TopologyEvaluationPrototypeHost: View {
    let pageID: String

    var body: some View {
        if page == 1 { topology }
        else {
            NavigationStack {
                ZStack { QuantumMistBackground(); ScrollView { VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) { if page == 2 { nodeDetail } else if page == 3 { evaluationSettings } else { evaluationResult } }.padding(AppTheme.Metrics.contentGutter).padding(.bottom, 72) } }
                .navigationTitle(page == 2 ? "写作者" : (page == 3 ? "评估设置" : "评估结果"))
                .navigationBarTitleDisplayMode(.inline)
                .safeAreaInset(edge: .bottom) { if page == 3 { Button("开始评估", systemImage: "play.fill") {}.buttonStyle(QuantumPrimaryButtonStyle()).controlSize(.large).frame(maxWidth: .infinity).padding().background(.ultraThinMaterial) } }
            }
        }
    }

    private var topology: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()
                Canvas { context, _ in
                    let lines = [(CGPoint(x: 205, y: 360), CGPoint(x: 205, y: 190)), (CGPoint(x: 205, y: 360), CGPoint(x: 90, y: 360)), (CGPoint(x: 205, y: 360), CGPoint(x: 320, y: 360)), (CGPoint(x: 205, y: 360), CGPoint(x: 205, y: 555))]
                    for line in lines { var path = Path(); path.move(to: line.0); path.addCurve(to: line.1, control1: CGPoint(x: line.0.x, y: (line.0.y + line.1.y) / 2), control2: CGPoint(x: line.1.x, y: (line.0.y + line.1.y) / 2)); context.stroke(path, with: .color(AppTheme.Colors.quantumBlue.opacity(0.65)), lineWidth: 2) }
                }
                node("研究员", "收集与阅读", "leaf.fill", AppTheme.Colors.statusCompleted).position(x: 205, y: 190)
                node("规划者", "拆解任务", "magnifyingglass", AppTheme.Colors.quantumBlue).position(x: 90, y: 360)
                node("写作者", "生成内容", "pencil.and.outline", AppTheme.Colors.quantumViolet).position(x: 205, y: 360)
                node("评审者", "检查与优化", "checkmark.seal.fill", AppTheme.Colors.statusWarning).position(x: 320, y: 360)
                node("资料库", "知识检索", "books.vertical.fill", AppTheme.Colors.statusCompleted).position(x: 205, y: 555)
                VStack { Spacer(); HStack { Button("添加节点", systemImage: "plus") {}.buttonStyle(.bordered); Spacer(); Button("适应画布") {}.buttonStyle(.bordered) }.padding() }
            }
            .navigationTitle("Agent 网络")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    @ViewBuilder private var nodeDetail: some View {
        HStack { Image(systemName: "pencil.and.outline").font(.largeTitle).foregroundStyle(AppTheme.Colors.quantumViolet).frame(width: 70, height: 70).background(AppTheme.Colors.mistLilac, in: RoundedRectangle(cornerRadius: 18)); VStack(alignment: .leading) { Text("写作者").font(AppTheme.Typography.sectionTitle); Text("生成高质量的结构化内容").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Button("编辑") {}.buttonStyle(.bordered) }
        setting("角色", "将资料整理为清晰、有逻辑的文章或报告。", "person.text.rectangle")
        setting("模型", "GPT-4o", "brain.head.profile")
        Text("技能").font(AppTheme.Typography.cardTitle); HStack { chip("内容生成"); chip("结构优化"); chip("风格调整") }
        Text("输入").font(AppTheme.Typography.cardTitle); HStack { chip("研究资料"); chip("用户要求"); chip("参考资料") }
        Text("输出").font(AppTheme.Typography.cardTitle); HStack { chip("文章草稿"); chip("思维导图"); chip("摘要") }
        setting("交接到", "评审者 · 检查与优化", "arrowshape.turn.up.right.fill")
        Button("删除节点", systemImage: "trash", role: .destructive) {}.buttonStyle(.bordered).frame(maxWidth: .infinity)
    }

    @ViewBuilder private var evaluationSettings: some View {
        Text("用真实任务，验证你的 Agent 团队。").foregroundStyle(AppTheme.Colors.textSecondary)
        field("任务样例", "请基于以下资料，写一篇关于“大学生如何高效学习”的文章，要求结构清晰、可操作性强。")
        Text("评估标准").font(AppTheme.Typography.cardTitle); LazyVGrid(columns: [.init(.flexible()), .init(.flexible()), .init(.flexible())]) { ForEach(["内容质量", "结构逻辑", "实用性", "创新性", "+ 自定义"], id: \.self) { value in chip(value) } }
        setting("对比对象", "GPT-4o（单 Agent）", "arrow.left.arrow.right")
        Text("资源预算").font(AppTheme.Typography.cardTitle); HStack { metric("最大 Token", "8,000"); metric("最长运行时间", "3 分钟") }
    }

    @ViewBuilder private var evaluationResult: some View {
        HStack { Image(systemName: "checkmark.circle.fill").font(.largeTitle).foregroundStyle(AppTheme.Colors.statusCompleted); VStack(alignment: .leading) { Text("任务完成").font(AppTheme.Typography.sectionTitle).foregroundStyle(AppTheme.Colors.statusCompleted); Text("整体表现优秀").font(AppTheme.Typography.micro) }; Spacer(); Text("92\n/ 100").font(.title.bold()).multilineTextAlignment(.center).foregroundStyle(AppTheme.Colors.statusCompleted) }.padding().background(AppTheme.Colors.successSurface, in: RoundedRectangle(cornerRadius: 16))
        Text("质量维度").font(AppTheme.Typography.cardTitle)
        ForEach([("内容质量", 0.94), ("结构逻辑", 0.90), ("实用性", 0.88), ("创新性", 0.85)], id: \.0) { item in HStack { Text(item.0).font(AppTheme.Typography.micro).frame(width: 70, alignment: .leading); ProgressView(value: item.1).tint(AppTheme.Colors.quantumGradient); Text("\(Int(item.1 * 100))") } }
        HStack { metric("Token 使用", "6,532 / 8,000"); metric("运行时间", "1分42秒 / 3分钟") }
        Text("问题与改进").font(AppTheme.Typography.cardTitle)
        setting("时间管理部分", "建议增加更具体的校园场景案例。", "exclamationmark.circle")
        setting("结论", "可以更有启发性，进一步提升号召力。", "exclamationmark.circle")
        HStack { Button("对比结果", systemImage: "chart.bar") {}.buttonStyle(.bordered); Button("重新运行", systemImage: "arrow.clockwise") {}.buttonStyle(.borderedProminent) }
    }

    private var page: Int { Int(pageID.suffix(2)) ?? 1 }
    private func node(_ title: String, _ detail: String, _ icon: String, _ tint: Color) -> some View { VStack(spacing: 5) { Image(systemName: icon).foregroundStyle(tint); Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }.frame(width: 110, height: 92).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 16)).overlay { RoundedRectangle(cornerRadius: 16).stroke(tint.opacity(0.65)) } }
    private func chip(_ title: String) -> some View { Text(title).font(AppTheme.Typography.micro).padding(.horizontal, 10).padding(.vertical, 8).background(AppTheme.Colors.surfaceTint, in: Capsule()) }
    private func setting(_ title: String, _ detail: String, _ icon: String) -> some View { HStack(alignment: .top) { Image(systemName: icon).foregroundStyle(AppTheme.Icons.interactive).frame(width: 32); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary) }; Spacer(); Image(systemName: "chevron.right") }.padding().quantumCard() }
    private func field(_ title: String, _ value: String) -> some View { VStack(alignment: .leading, spacing: 8) { Text(title).font(AppTheme.Typography.cardTitle); Text(value).font(AppTheme.Typography.supporting).padding().frame(maxWidth: .infinity, minHeight: 110, alignment: .topLeading).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 12)) } }
    private func metric(_ title: String, _ value: String) -> some View { VStack(alignment: .leading, spacing: 7) { Text(title).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary); Text(value).font(AppTheme.Typography.cardTitle) }.padding().frame(maxWidth: .infinity, minHeight: 82).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 12)).overlay { RoundedRectangle(cornerRadius: 12).stroke(AppTheme.Colors.border) } }
}

private struct V3WorkflowTrailingLabelStyle: LabelStyle { func makeBody(configuration: Configuration) -> some View { HStack { configuration.title; Spacer(); configuration.icon } } }
#endif

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
