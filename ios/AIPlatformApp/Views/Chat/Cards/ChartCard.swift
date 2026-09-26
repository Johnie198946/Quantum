//
//  ChartCard.swift
//  AIPlatformApp
//
//  图表卡片：Swift Charts 原生渲染，仅支持 line / bar，
//  Quantum Spectrum 序列（Cyan → Blue → Violet），不挪用红黄绿警示色。
//

import SwiftUI
import Charts

public struct ChartCard: View {
    public let block: ChartBlock

    public init(block: ChartBlock) {
        self.block = block
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: block.chartType == .line ? "chart.xyaxis.line" : "chart.bar.fill")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.Colors.quantumViolet)
                    .frame(width: 34, height: 34)
                    .background(AppTheme.Colors.mistLilac, in: Circle())
                VStack(alignment: .leading, spacing: 2) {
                    Text("数据观察")
                        .font(AppTheme.Typography.micro.weight(.bold))
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                    Text(block.title)
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundColor(AppTheme.Colors.textPrimary)
                }
                Spacer()
            }

            if block.series.count > 1 {
                HStack(spacing: AppTheme.Spacing.md) {
                    ForEach(Array(block.series.enumerated()), id: \.element.id) { index, series in
                        HStack(spacing: 5) {
                            Circle().fill(seriesColor(index)).frame(width: 7, height: 7)
                            Text(series.name)
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                    }
                }
            }

            chartContent
                .frame(height: 150)
                .padding(AppTheme.Spacing.sm)
                .background(Color.white.opacity(0.68), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))

            if !block.summary.isEmpty {
                HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                    Image(systemName: "sparkles")
                        .foregroundStyle(AppTheme.Colors.emberOrange)
                    Text(block.summary)
                        .font(AppTheme.Typography.supporting)
                        .foregroundColor(AppTheme.Colors.textSecondary)
                        .lineSpacing(2)
                }
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.Colors.bentoAmber.opacity(0.56), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            }
        }
        .padding(AppTheme.Spacing.lg)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(
                colors: [AppTheme.Colors.mistSky.opacity(0.72), AppTheme.Colors.cardBackground],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                .stroke(Color.white.opacity(0.84), lineWidth: 0.8)
        )
        .shadow(color: AppTheme.Colors.primary.opacity(0.08), radius: 16, y: 7)
    }

    @ViewBuilder
    private var chartContent: some View {
        Chart {
            ForEach(Array(block.series.enumerated()), id: \.element.id) { index, series in
                ForEach(series.points) { point in
                    if block.chartType == .line {
                        LineMark(
                            x: .value("时间", point.label),
                            y: .value("数值", point.value)
                        )
                        .foregroundStyle(seriesColor(index))
                        .symbol(Circle().strokeBorder(lineWidth: 2))
                        .interpolationMethod(.catmullRom)
                    } else {
                        BarMark(
                            x: .value("时间", point.label),
                            y: .value("数值", point.value)
                        )
                        .foregroundStyle(seriesColor(index))
                        .cornerRadius(AppTheme.Radius.xs)
                    }
                }
            }
        }
        .chartYScale(domain: 0...max(1, maxValue(block.series) * 1.2))
        .chartYAxis {
            AxisMarks(position: .leading) { _ in
                AxisGridLine().foregroundStyle(AppTheme.Colors.border.opacity(0.6))
                AxisValueLabel().foregroundStyle(AppTheme.Colors.textTertiary)
            }
        }
        .chartXAxis {
            AxisMarks { _ in
                AxisValueLabel().foregroundStyle(AppTheme.Colors.textTertiary)
            }
        }
    }

    /// Quantum Spectrum 序列：Cyan → Blue → Violet（严禁红黄绿警示色）
    private func seriesColor(_ index: Int) -> Color {
        switch index {
        case 0: return AppTheme.Colors.quantumCyan
        case 1: return AppTheme.Colors.quantumBlue
        default: return AppTheme.Colors.quantumViolet
        }
    }

    private func maxValue(_ series: [ChartSeries]) -> Double {
        let all = series.flatMap(\.points).map(\.value)
        return all.max() ?? 100
    }
}

// MARK: - Xcode #Preview

#Preview("ChartCard - Light") {
    ChartCard(
        block: ChartBlock(
            title: "近 6 月热度",
            chartType: .line,
            series: [
                ChartSeries(name: "A", points: [
                    ChartPoint(label: "1月", value: 10),
                    ChartPoint(label: "2月", value: 20),
                    ChartPoint(label: "3月", value: 30)
                ]),
                ChartSeries(name: "B", points: [
                    ChartPoint(label: "1月", value: 5),
                    ChartPoint(label: "2月", value: 15),
                    ChartPoint(label: "3月", value: 25)
                ])
            ],
            summary: "摘要行"
        )
    )
    .padding()
    .background(AppTheme.Colors.groupedBackground)
}
