//
//  AgentCreatorView.swift
//  AIPlatformApp
//
//  设置页：创建智能体（替换「提炼工作台」）。一行输入用途 + 一键创建 + 0.8s 骨架卡动画 → 结果卡。
//  本地模板引擎生成 AgentNode（0 LLM 成本）；去对话 = 本地 Mock 对话；不持久化（演示语义）。
//

import SwiftUI

// MARK: - 本地模板引擎（0 LLM 成本）

public enum LocalAgentTemplateEngine {
    public struct Template {
        public let name: String
        public let roleCategory: String
        public let summary: String
        /// 继承的基线 profile（后端白名单：main_agent / supervision / coder / knowledge）
        public let baseAgentId: String
    }

    public static func build(from purpose: String) -> AgentNode {
        let t = match(purpose)
        return AgentNode(
            id: "agent_" + UUID().uuidString.prefix(8),
            name: t.name,
            roleCategory: t.roleCategory,
            systemPromptSummary: t.summary,
            status: .idle,
            position: CGPoint(x: 0, y: 0),
            subscribedKnowledge: []
        )
    }

    public static func match(_ purpose: String) -> Template {
        let p = purpose
        if p.contains("制造") || p.contains("产线") || p.contains("SMT") || p.contains("质检") {
            return Template(
                name: "制造诊断 Sentinel",
                roleCategory: "根因诊断 · 制造",
                summary: "结合产线 IoT 遥测与 SMT 专家知识库，对设备异常进行因果推断，输出告警定级与处置工单。",
                baseAgentId: "main_agent"
            )
        }
        if p.contains("金融") || p.contains("对账") || p.contains("风控") || p.contains("清算") {
            return Template(
                name: "金融对账 Agent",
                roleCategory: "对账风控 · 金融",
                summary: "面向高并发清结算系统的幂等性校验与三方对账差异核销，输出防重放协议与差异报告。",
                baseAgentId: "coder"
            )
        }
        if p.contains("竞品") || p.contains("情报") || p.contains("监测") {
            return Template(
                name: "竞品情报雷达",
                roleCategory: "情报监测 · 竞品",
                summary: "增量追踪竞品动态、定价与开源策略，生成结构化情报卡片并回写竞品情报知识库。",
                baseAgentId: "knowledge"
            )
        }
        if p.contains("审计") || p.contains("合规") || p.contains("内控") {
            return Template(
                name: "审计合规哨兵",
                roleCategory: "合规审计 · 内控",
                summary: "全流程审计写操作与参数下发，校验 ABAC 权限与变更影响域，输出合规红线清单。",
                baseAgentId: "supervision"
            )
        }
        if p.contains("旅行") || p.contains("目的地") || p.contains("行程") {
            return Template(
                name: "旅行研究助手",
                roleCategory: "目的地研究 · 旅行规划",
                summary: "整理目的地资料、旅行攻略和实用信息，基于可靠来源给出行程建议，不代替用户预订或作主观推荐。",
                baseAgentId: "knowledge"
            )
        }
        return Template(
            name: "通用协同 Agent",
            roleCategory: "通用 · 任务分诊",
            summary: "基于已订阅知识库进行任务分诊与多智能体编排，输出结构化执行方案。",
            baseAgentId: "main_agent"
        )
    }
}

// MARK: - 创建智能体视图

private enum AgentCreationStep {
    case purpose
    case tone
    case boundary
    case confirmation
    case creating
    case completed
}

public struct AgentCreatorView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.dismiss) private var dismiss

    @State private var purposeText: String = ""
    @State private var draftText: String = ""
    @State private var selectedTone = "专业可靠"
    @State private var selectedBoundary = "只基于可靠来源，不提供预订服务"
    @State private var step: AgentCreationStep = .purpose
    @State private var isCreating: Bool = false
    @State private var createdAgent: AgentNode? = nil
    @State private var creationFailed: Bool = false
    @State private var creationError: String? = nil

    private let presetPurposes = [
        "旅行研究",
        "课程学习",
        "论文写作",
    ]

    public init(prototypePageID: String? = nil) {
        guard let prototypePageID else { return }
        let purpose = "主要是做目的地研究，帮我整理资料和攻略"
        _purposeText = State(initialValue: purpose)
        _selectedTone = State(initialValue: "专业可靠")
        _selectedBoundary = State(initialValue: "只基于可靠来源，不提供预订服务")
        if prototypePageID.hasSuffix("p03") {
            _step = State(initialValue: .confirmation)
        } else if prototypePageID.hasSuffix("p04") {
            _step = State(initialValue: .completed)
            _createdAgent = State(initialValue: AgentNode(
                id: "travel-research-preview", name: "旅行研究助手", roleCategory: "目的地研究 · 旅行规划",
                systemPromptSummary: "整理目的地资料、旅行攻略和实用信息，基于可靠来源给出行程建议。",
                position: .zero
            ))
        } else {
            _step = State(initialValue: .boundary)
        }
    }

    public var body: some View {
        ZStack {
            QuantumMistBackground()

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                        assistantBubble("首先，这个智能体主要用来做什么？\n例如：行程规划、目的地研究、课程复习或论文写作。")

                        if !purposeText.isEmpty {
                            userBubble(purposeText)
                            assistantBubble("好的。你希望它以什么风格回答？")
                            choiceRow(
                                ["专业可靠", "轻松有趣", "简洁高效"],
                                selected: selectedTone,
                                enabled: step == .tone
                            ) { value in
                                selectedTone = value
                                withAnimation(AppTheme.Motion.standard) { step = .boundary }
                            }
                        }

                        if step == .boundary || step == .confirmation || step == .creating || step == .completed {
                            userBubble(selectedTone)
                            assistantBubble("最后，有没有需要特别注意的边界？")
                            choiceRow(
                                ["只基于可靠来源，不提供预订服务", "不访问私人资料", "关键结果由我确认"],
                                selected: selectedBoundary,
                                enabled: step == .boundary
                            ) { value in
                                selectedBoundary = value
                                withAnimation(AppTheme.Motion.standard) { step = .confirmation }
                            }
                        }

                        if step == .confirmation || step == .creating || step == .completed {
                            userBubble(selectedBoundary)
                            confirmationCard
                        }

                        if step == .creating {
                            skeletonCard.id("creation-status")
                        } else if let agent = createdAgent {
                            resultCard(agent).id("creation-result")
                        }

                        if creationFailed, let creationError {
                            Label(creationError, systemImage: "exclamationmark.triangle.fill")
                                .font(AppTheme.Typography.supporting)
                                .foregroundStyle(AppTheme.Colors.statusError)
                                .padding(AppTheme.Spacing.md)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(AppTheme.Colors.dangerSurface, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                        }

                        Color.clear.frame(height: 1).id("bottom")
                    }
                    .padding(.horizontal, AppTheme.Metrics.contentGutter)
                    .padding(.top, AppTheme.Spacing.lg)
                    .padding(.bottom, 110)
                }
                .onChange(of: step) { _, _ in
                    withAnimation(AppTheme.Motion.standard) { proxy.scrollTo("bottom", anchor: .bottom) }
                }
            }
            if step == .confirmation {
                ZStack {
                    QuantumMistBackground()
                    ScrollView {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                            HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                                QuantumAvatarView(size: 34)
                                Text("根据我们的对话，这是为你生成的旅行研究智能体设置。你可以随时修改，确认后我将为你创建。")
                                    .font(AppTheme.Typography.supporting)
                                    .padding(AppTheme.Spacing.md)
                                    .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                            }
                            confirmationCard
                        }
                        .padding(AppTheme.Metrics.contentGutter)
                    }
                }
            } else if step == .completed, let agent = createdAgent {
                ZStack {
                    QuantumMistBackground()
                    ScrollView {
                        resultCard(agent)
                            .padding(AppTheme.Metrics.contentGutter)
                            .padding(.top, AppTheme.Spacing.md)
                    }
                }
            }
        }
        .navigationTitle("创建智能体")
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if step == .purpose {
                composer
            }
        }
    }

    private var composer: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: AppTheme.Spacing.sm) {
                    ForEach(presetPurposes, id: \.self) { preset in
                        Button(preset) { draftText = "帮我创建一个\(preset)智能体" }
                            .font(AppTheme.Typography.micro)
                            .buttonStyle(.bordered)
                            .clipShape(Capsule())
                    }
                }
                .padding(.horizontal, AppTheme.Metrics.contentGutter)
            }
            HStack(spacing: AppTheme.Spacing.sm) {
                TextField("发送消息…", text: $draftText, axis: .vertical)
                    .lineLimit(1...4)
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .frame(minHeight: 48)
                    .background(AppTheme.Colors.cardBackground, in: Capsule())
                    .overlay { Capsule().stroke(AppTheme.Colors.border, lineWidth: 0.75) }
                    .submitLabel(.send)
                    .onSubmit(submitPurpose)
                Button(action: submitPurpose) {
                    Image(systemName: "arrow.up")
                        .font(.headline.weight(.bold))
                        .foregroundStyle(Color.white)
                        .frame(width: 44, height: 44)
                        .background(draftText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? AppTheme.Colors.textTertiary : AppTheme.Colors.interactiveBlue, in: Circle())
                }
                .disabled(draftText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .accessibilityLabel("发送")
            }
            .padding(.horizontal, AppTheme.Metrics.contentGutter)
            .padding(.bottom, AppTheme.Spacing.sm)
        }
        .padding(.top, AppTheme.Spacing.sm)
        .background(.ultraThinMaterial)
    }

    private func assistantBubble(_ text: String) -> some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            Image("quantum_logo_icon")
                .resizable()
                .scaledToFit()
                .frame(width: 30, height: 30)
            Text(text)
                .font(AppTheme.Typography.body)
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func userBubble(_ text: String) -> some View {
        Text(text)
            .font(AppTheme.Typography.body)
            .foregroundStyle(AppTheme.Colors.textPrimary)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(AppTheme.Colors.selectionTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .frame(maxWidth: .infinity, alignment: .trailing)
            .padding(.leading, 70)
    }

    private func choiceRow(
        _ values: [String],
        selected: String,
        enabled: Bool,
        action: @escaping (String) -> Void
    ) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 118), spacing: AppTheme.Spacing.sm)], alignment: .leading, spacing: AppTheme.Spacing.sm) {
            ForEach(values, id: \.self) { value in
                Button(value) { action(value) }
                    .font(AppTheme.Typography.supporting.weight(.medium))
                    .buttonStyle(.bordered)
                    .tint(value == selected ? AppTheme.Colors.interactiveBlue : AppTheme.Colors.textSecondary)
                    .disabled(!enabled)
            }
        }
        .padding(.leading, 38)
    }

    private var confirmationCard: some View {
        let template = LocalAgentTemplateEngine.match(purposeText)
        return VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: "mountain.2.fill")
                    .font(.title2)
                    .foregroundStyle(AppTheme.Colors.statusCompleted)
                    .frame(width: 54, height: 54)
                    .background(AppTheme.Colors.mistMint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                VStack(alignment: .leading, spacing: 3) {
                    Text(template.name)
                        .font(AppTheme.Typography.sectionTitle)
                    Text(template.roleCategory)
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
            }
            summaryRow("主要任务", value: purposeText, icon: "scope")
            summaryRow("表达风格", value: selectedTone, icon: "text.bubble")
            summaryRow("边界与安全", value: selectedBoundary, icon: "checkmark.shield")

            Button(step == .creating ? "正在创建…" : "确认生成") { createAgent() }
                .buttonStyle(QuantumPrimaryButtonStyle())
                .disabled(step == .creating || step == .completed)
        }
        .padding(AppTheme.Spacing.lg)
        .quantumCard()
    }

    private func summaryRow(_ title: String, value: String, icon: String) -> some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            Image(systemName: icon)
                .foregroundStyle(AppTheme.Colors.interactiveBlue)
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                Text(value).font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textPrimary)
            }
        }
    }

    // 0.8s 骨架卡动画
    private var skeletonCard: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.sm) {
                skeletonBlock(width: 44, height: 44, corner: AppTheme.Radius.md)
                VStack(alignment: .leading, spacing: 6) {
                    skeletonBlock(width: 140, height: 14, corner: 4)
                    skeletonBlock(width: 90, height: 10, corner: 4)
                }
            }
            skeletonBlock(width: nil, height: 12, corner: 4)
            skeletonBlock(width: 200, height: 12, corner: 4)
            Text("正在生成智能体…")
                .font(.system(size: 11))
                .foregroundColor(AppTheme.Colors.textTertiary)
                .padding(.top, 2)
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.secondaryBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
    }

    private func skeletonBlock(width: CGFloat?, height: CGFloat, corner: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: corner)
            .fill(AppTheme.Colors.tertiaryBackground)
            .frame(width: width, height: height)
            .frame(maxWidth: width == nil ? .infinity : nil)
    }

    private func resultCard(_ agent: AgentNode) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(spacing: AppTheme.Spacing.md) {
                ProgressView(value: 1).tint(AppTheme.Colors.quantumBlue).frame(width: 44)
                VStack(alignment: .leading, spacing: 3) {
                    Text("正在创建你的智能体…").font(.subheadline.weight(.semibold))
                    Text("配置知识、工具和提示词").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                }
                Spacer(); Image(systemName: "checkmark").foregroundStyle(AppTheme.Colors.statusCompleted)
            }
            Divider()
            VStack(spacing: AppTheme.Spacing.sm) {
                ZStack(alignment: .bottomTrailing) {
                    RoundedRectangle(cornerRadius: AppTheme.Radius.lg)
                        .fill(AppTheme.Colors.mistMint).frame(width: 94, height: 94)
                    Image(systemName: "mountain.2.fill").font(.system(size: 46)).foregroundStyle(AppTheme.Colors.statusCompleted)
                        .frame(width: 94, height: 94)
                    Image(systemName: "checkmark.circle.fill").font(.title2).foregroundStyle(AppTheme.Colors.statusCompleted).background(.white, in: Circle())
                }
                Text(agent.name).font(AppTheme.Typography.screenTitle)
                Text("已创建完成").font(.caption.weight(.semibold)).foregroundStyle(AppTheme.Colors.statusCompleted)
                Text("用可靠的知识，发现更大的世界")
                    .font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
            }
            .frame(maxWidth: .infinity)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Text("它可以这样帮助你：").font(.caption.weight(.semibold))
                Label("整理日本京都的四季旅行攻略，包括必去景点、当地文化、美食推荐和实用贴士。", systemImage: "bubble.left")
                    .font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
            }
            .padding(AppTheme.Spacing.md).background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            Button("开始对话", systemImage: "bubble.left.and.bubble.right.fill", action: goToChat)
                .buttonStyle(QuantumPrimaryButtonStyle())
            Button("加入工作流", systemImage: "folder") { dismiss() }
                .buttonStyle(.bordered).frame(maxWidth: .infinity)
            Button("管理知识与工具", systemImage: "gearshape") { dismiss() }
                .buttonStyle(.bordered).frame(maxWidth: .infinity)
        }
        .padding(AppTheme.Spacing.lg)
        .quantumCard()
    }

    // MARK: - Actions

    private func createAgent() {
        let purpose = purposeText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !purpose.isEmpty else { return }
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif
        isCreating = true
        step = .creating
        createdAgent = nil
        creationFailed = false
        creationError = nil

        let template = LocalAgentTemplateEngine.match(purpose)
        let body = TenantAgentCreateDTO(
            baseAgentId: template.baseAgentId,
            customName: template.name,
            privatePromptDelta: template.summary
        )

        Task { @MainActor in
            do {
                // 直写云端 PostgreSQL（201），base_agent_id 由后端白名单校验（非法 422）
                let dto = try await APIClient.shared.createTenantAgent(body)
                isCreating = false
                createdAgent = AgentNode(
                    id: dto.id,
                    name: dto.customName ?? dto.baseAgentId,
                    roleCategory: template.roleCategory,
                    systemPromptSummary: dto.privatePromptDelta.isEmpty ? template.summary : dto.privatePromptDelta,
                    status: .idle,
                    position: CGPoint(x: 0, y: 0)
                )
                step = .completed
                NotificationCenter.default.post(name: .tenantAgentsDidUpdate, object: nil)
                #if os(iOS)
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                #endif
            } catch {
                // 云端失败：诚实报错，绝不落本地演示数据
                isCreating = false
                step = .confirmation
                creationFailed = true
                creationError = "创建失败：\(error.localizedDescription)"
                #if os(iOS)
                UINotificationFeedbackGenerator().notificationOccurred(.error)
                #endif
            }
        }
    }

    private func submitPurpose() {
        let value = draftText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        purposeText = value
        draftText = ""
        withAnimation(AppTheme.Motion.standard) { step = .tone }
    }

    private func goToChat() {
        guard let agent = createdAgent else { return }
        #if os(iOS)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        #endif
        appState.navigateToChatWithPrompt(
            "已加载智能体「\(agent.name)」System Directive：\n\(agent.systemPromptSummary)"
        )
    }
}

#if DEBUG
struct V4AgentCreationPrototypeHost: View {
    let pageID: String

    var body: some View {
        NavigationStack {
            if pageID.hasSuffix("p01") {
                AgentCreationStartPreview()
            } else {
                AgentCreatorView(prototypePageID: pageID)
            }
        }
    }
}

private struct AgentCreationStartPreview: View {
    @State private var draft = ""
    @State private var quote: QuotedContext?
    @State private var isVoicePressing = false
    @StateObject private var speechService = SpeechRecognizerService()

    var body: some View {
        ZStack {
            QuantumMistBackground()
            VStack(spacing: 0) {
                ChatTopBarView(isGenerating: false, title: "Quantum", onTitleTap: {}, onNewSession: {}, onHistoryTap: {}, onClearTap: {})
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        Text("你好，\n有什么我可以帮助你吗？")
                            .font(.system(.largeTitle, design: .serif, weight: .semibold))
                        previewAction("解答一个学习问题", "magnifyingglass", AppTheme.Colors.quantumBlue)
                        previewAction("总结一篇论文", "doc.text.fill", AppTheme.Colors.statusCompleted)
                        previewAction("帮我创建一个智能体", "cpu.fill", AppTheme.Colors.quantumViolet)
                        Text("帮我创建一个旅行研究智能体")
                            .font(AppTheme.Typography.body)
                            .padding(AppTheme.Spacing.md).background(AppTheme.Colors.selectionTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                            .frame(maxWidth: .infinity, alignment: .trailing)
                        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                            QuantumAvatarView(size: 32)
                            Text("好的！我来帮你创建一个旅行研究智能体。为了更好地满足你的需求，想先了解几个问题。")
                                .font(AppTheme.Typography.body).padding(AppTheme.Spacing.md)
                                .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                        }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                }
                ChatInputBar(inputText: $draft, quotedContext: $quote, isVoicePressing: $isVoicePressing,
                             speechService: speechService, isGenerating: false, dismissKeyboardToken: 0,
                             onSend: {}, onVoicePressChanged: { _ in }, onPlusTap: {})
            }
        }
    }

    private func previewAction(_ title: String, _ icon: String, _ color: Color) -> some View {
        Label(title, systemImage: icon).font(AppTheme.Typography.body)
            .foregroundStyle(AppTheme.Colors.textSecondary)
            .padding(AppTheme.Spacing.md).frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            .overlay(alignment: .leading) { RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 3).padding(.vertical, 10) }
    }
}
#endif

// MARK: - Xcode #Preview

#Preview("AgentCreatorView - Light") {
    AgentCreatorView()
        .environmentObject(AppState())
        .padding()
}

#Preview("AgentCreatorView - Dark") {
    AgentCreatorView()
        .environmentObject(AppState())
        .padding()
}
