//
//  BlockCardDispatcher.swift
//  AIPlatformApp
//
//  Zero-AnyView Static Card Dispatcher for Message Blocks
//  Strictly adheres to DeepSeek Harness / Cordis plugin dispatch principles.
//  Preserves SwiftUI Structural Identity to prevent list drop-frame and state loss.
//

import SwiftUI

public struct BlockCardDispatcher: View {
    public let block: MessageBlock
    public var isStreaming: Bool = false
    public var reasoningDuration: Int? = nil
    public var reasoningInitiallyExpanded: Bool = false
    public var reasoningSummary: String? = nil
    public var onClarifySubmit: ((String) -> Void)? = nil
    public var onNoteDraftAction: ((String, String) -> Void)? = nil
    public var onKnowledgeAction: ((String, String) -> Void)? = nil
    public var onCapabilityProposal: ((String, String) -> Void)? = nil
    public var onWorkflowOpen: ((String) -> Void)? = nil
    public var onKnowledgeNavigation: ((KnowledgeNavigationTarget) -> Void)? = nil

    public init(
        block: MessageBlock,
        isStreaming: Bool = false,
        reasoningDuration: Int? = nil,
        reasoningInitiallyExpanded: Bool = false,
        reasoningSummary: String? = nil,
        onClarifySubmit: ((String) -> Void)? = nil,
        onNoteDraftAction: ((String, String) -> Void)? = nil,
        onKnowledgeAction: ((String, String) -> Void)? = nil,
        onCapabilityProposal: ((String, String) -> Void)? = nil,
        onWorkflowOpen: ((String) -> Void)? = nil,
        onKnowledgeNavigation: ((KnowledgeNavigationTarget) -> Void)? = nil
    ) {
        self.block = block
        self.isStreaming = isStreaming
        self.reasoningDuration = reasoningDuration
        self.reasoningInitiallyExpanded = reasoningInitiallyExpanded
        self.reasoningSummary = reasoningSummary
        self.onClarifySubmit = onClarifySubmit
        self.onNoteDraftAction = onNoteDraftAction
        self.onKnowledgeAction = onKnowledgeAction
        self.onCapabilityProposal = onCapabilityProposal
        self.onWorkflowOpen = onWorkflowOpen
        self.onKnowledgeNavigation = onKnowledgeNavigation
    }

    public var body: some View {
        dispatchView(for: block)
    }

    @ViewBuilder
    private func dispatchView(for block: MessageBlock) -> some View {
        switch block {
        case .code(let snippet):
            CodeBlockCard(snippet: snippet)

        case .formula(let formula):
            FormulaCard(formula: formula)

        case .chart(let chartBlock):
            ChartCard(block: chartBlock)

        case .image(let imageBlock):
            ImageCard(block: imageBlock)

        case .table(let tableBlock):
            TableCard(block: tableBlock)

        case .attachment(let attachmentBlock):
            AttachmentCard(block: attachmentBlock)

        case .reasoning(let steps):
            ReasoningCard(
                steps: steps,
                durationSeconds: reasoningDuration,
                isStreaming: isStreaming,
                initiallyExpanded: reasoningInitiallyExpanded,
                summaryTitle: reasoningSummary
            )

        case .clarify(let clarifyBlock):
            if clarifyBlock.source == "note_organization" {
                NoteOrganizationClarifyView(block: clarifyBlock, onSubmit: onClarifySubmit)
            } else {
                ClarifyCard(block: clarifyBlock, onSubmit: onClarifySubmit)
            }

        case .noteDraft(let draft):
            NoteDraftCard(
                draft: draft,
                onSave: { onNoteDraftAction?(draft.id, "save") },
                onMerge: { onNoteDraftAction?(draft.id, "merge") },
                onEdit: { onNoteDraftAction?(draft.id, "edit") },
                onDiscard: { onNoteDraftAction?(draft.id, "discard") }
            )
        case .knowledgeAction(let action):
            KnowledgeActionCard(
                action: action,
                onApply: { onKnowledgeAction?(action.id, "apply") },
                onDiscard: { onKnowledgeAction?(action.id, "discard") },
                onOpenResult: { onKnowledgeAction?(action.id, "open") }
            )
        case .capabilityProposal(let proposal):
            CapabilityProposalCard(
                proposal: proposal,
                onConfirm: { onCapabilityProposal?(proposal.id, "confirm") },
                onDiscard: { onCapabilityProposal?(proposal.id, "discard") }
            )
        case .artifactConsumption(let receipt):
            ArtifactConsumptionCard(receipt: receipt)
        case .workflow(let workflow):
            Button { onWorkflowOpen?(workflow.id) } label: {
                WorkflowSummaryCard(workflow: workflow)
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityHint("打开工作流详情")
        case .knowledgeNavigation(let target):
            Button { onKnowledgeNavigation?(target) } label: {
                KnowledgeNavigationMessageCard(target: target)
            }
            .buttonStyle(SoftButtonStyle())
            .accessibilityHint("打开知识库")
        }
    }
}

private struct KnowledgeNavigationMessageCard: View {
    let target: KnowledgeNavigationTarget

    var body: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: target.destination == "note" ? "note.text" : "books.vertical.fill")
                .font(.system(size: 19, weight: .semibold))
                .foregroundStyle(AppTheme.Colors.leaf)
                .frame(width: 44, height: 44)
                .background(Color.white.opacity(0.76), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            VStack(alignment: .leading, spacing: 3) {
                Text(target.destination == "note" ? "继续阅读笔记" : "打开知识书架")
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text(target.query?.isEmpty == false ? target.query! : "相关内容已经整理到你的知识空间")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineLimit(2)
            }
            Spacer(minLength: 0)
            Image(systemName: "arrow.up.right")
                .foregroundStyle(AppTheme.Icons.tertiary)
        }
        .padding(AppTheme.Spacing.lg)
        .background(
            LinearGradient(
                colors: [AppTheme.Colors.mistMint.opacity(0.74), AppTheme.Colors.cardBackground],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: AppTheme.Radius.xl)
        )
        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.xl).stroke(Color.white.opacity(0.86), lineWidth: 0.8) }
        .accessibilityElement(children: .combine)
    }
}

private struct ArtifactConsumptionCard: View {
    let receipt: ArtifactConsumptionBlock

    private var hashSummary: String {
        let hash = receipt.artifactContentHash
        guard hash.count > 16 else { return hash }
        return "\(hash.prefix(8))…\(hash.suffix(8))"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(AppTheme.Icons.success)
                Text(receipt.status == "completed" ? "已消费" : receipt.status)
                    .font(.headline)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Spacer()
                Text("回执")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.primary)
            }
            Text(receipt.structuredPreview)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .lineLimit(6)
                .textSelection(.enabled)
            VStack(alignment: .leading, spacing: 4) {
                Text("工件  \(receipt.artifactId)")
                Text("Hash  \(hashSummary)")
                Text("Schema  \(receipt.schemaVersion)")
                Text("时间  \(receipt.consumedAt)")
                Text("回执  \(receipt.receiptId)")
            }
            .font(.caption2)
            .foregroundStyle(AppTheme.Colors.textTertiary)
            .textSelection(.enabled)
        }
        .padding(14)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(AppTheme.Colors.border, lineWidth: 0.5)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("工件已消费回执")
    }
}
