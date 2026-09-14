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
    public var onClarifySubmit: ((String) -> Void)? = nil
    public var onNoteDraftAction: ((String, String) -> Void)? = nil
    public var onKnowledgeAction: ((String, String) -> Void)? = nil
    public var onCapabilityProposal: ((String, String) -> Void)? = nil

    public init(
        block: MessageBlock,
        isStreaming: Bool = false,
        onClarifySubmit: ((String) -> Void)? = nil,
        onNoteDraftAction: ((String, String) -> Void)? = nil,
        onKnowledgeAction: ((String, String) -> Void)? = nil,
        onCapabilityProposal: ((String, String) -> Void)? = nil
    ) {
        self.block = block
        self.isStreaming = isStreaming
        self.onClarifySubmit = onClarifySubmit
        self.onNoteDraftAction = onNoteDraftAction
        self.onKnowledgeAction = onKnowledgeAction
        self.onCapabilityProposal = onCapabilityProposal
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
            ReasoningCard(steps: steps, isStreaming: isStreaming)

        case .clarify(let clarifyBlock):
            ClarifyCard(block: clarifyBlock, onSubmit: onClarifySubmit)

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
        }
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
