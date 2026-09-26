//
//  MarkdownCards.swift
//  AIPlatformApp
//
//  Markdown 卡片渲染组件：极简 SwiftUI 原生流式卡片容器。
//

import SwiftUI

public struct MarkdownText: View {
    public let text: String, font: Font, color: Color
    public init(_ text: String, font: Font = .system(size: 15), color: Color = AppTheme.Colors.textPrimary) {
        self.text = text; self.font = font; self.color = color
    }
    public var body: some View {
        Group {
            if text.contains("==") {
                Text(highlightedMarkdown)
            } else {
                InlineMathPresentation.segments(in: text)
                    .reduce(Text("")) { result, segment in
                        result + (segment.isMath
                            ? Text(verbatim: MathFormulaPresentation.displayText(segment.text)).italic()
                            : Text(LocalizedStringKey(segment.text)))
                    }
            }
        }
        .font(font)
        .foregroundColor(color)
    }

    private var highlightedMarkdown: AttributedString {
        var result = AttributedString()
        for (index, part) in text.components(separatedBy: "==").enumerated() {
            var segment = (try? AttributedString(markdown: part)) ?? AttributedString(part)
            if index.isMultiple(of: 2) == false {
                segment.backgroundColor = Color(red: 0.78, green: 0.96, blue: 0.88)
            }
            result += segment
        }
        return result
    }
}

enum InlineMathPresentation {
    struct Segment: Equatable {
        let text: String
        let isMath: Bool
    }

    static func segments(in source: String) -> [Segment] {
        let characters = Array(source)
        var result: [Segment] = []
        var plain = ""
        var index = 0

        func flushPlain() {
            guard !plain.isEmpty else { return }
            result.append(.init(text: plain, isMath: false))
            plain = ""
        }

        while index < characters.count {
            let opener: [Character]
            let closer: [Character]
            if characters[index] == "$", index == 0 || characters[index - 1] != "\\" {
                opener = ["$"]; closer = ["$"]
            } else if characters[index] == "\\", index + 1 < characters.count,
                      characters[index + 1] == "(" || characters[index + 1] == "[" {
                opener = ["\\", characters[index + 1]]
                closer = ["\\", characters[index + 1] == "(" ? ")" : "]"]
            } else {
                plain.append(characters[index]); index += 1; continue
            }

            let contentStart = index + opener.count
            guard let contentEnd = closingIndex(of: closer, in: characters, after: contentStart) else {
                plain.append(contentsOf: opener); index = contentStart; continue
            }
            let math = String(characters[contentStart..<contentEnd])
            guard !math.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                plain.append(contentsOf: opener); index = contentStart; continue
            }
            flushPlain()
            result.append(.init(text: math, isMath: true))
            index = contentEnd + closer.count
        }
        flushPlain()
        return result
    }

    private static func closingIndex(
        of token: [Character], in characters: [Character], after start: Int
    ) -> Int? {
        guard !token.isEmpty, start < characters.count else { return nil }
        for index in start..<characters.count where index + token.count <= characters.count {
            if Array(characters[index..<(index + token.count)]) == token,
               index == 0 || characters[index - 1] != "\\" || token.count > 1 {
                return index
            }
        }
        return nil
    }
}

public struct MarkdownBlockCard: View {
    public let block: MarkdownBlock
    public init(block: MarkdownBlock) { self.block = block }

    public var body: some View {
        switch block {
        case .heading(let level, let text):
            HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(AppTheme.Colors.interactiveBlue)
                    .frame(width: 3, height: level <= 2 ? 21 : 17)
                    .padding(.top, 3)
                    .accessibilityHidden(true)
                MarkdownText(
                    text,
                    font: level == 1 ? .title2.bold() : (level == 2 ? .headline : .subheadline.weight(.semibold))
                )
                .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.top, level <= 2 ? AppTheme.Spacing.lg : AppTheme.Spacing.sm)
            .accessibilityAddTraits(.isHeader)
        case .callout(let label, let text):
            HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(AppTheme.Colors.quantumBlue)
                    .frame(width: 3)
                VStack(alignment: .leading, spacing: 3) {
                    Text(label).font(.system(size: 11, weight: .bold)).foregroundColor(AppTheme.Colors.quantumBlue)
                    MarkdownText(text, font: .system(size: 14, weight: .medium)).fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.vertical, AppTheme.Spacing.sm)
            .padding(.horizontal, AppTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.mistMint.opacity(0.42))
        case .paragraph(let text):
            MarkdownText(text, font: .system(size: 15.5)).fixedSize(horizontal: false, vertical: true).lineSpacing(5)
        case .bulletList(let items):
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                        Circle().fill(AppTheme.Colors.quantumCyan).frame(width: 5, height: 5).padding(.top, 7)
                        MarkdownText(item, font: .system(size: 14.5)).fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        case .numberedList(let items):
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    let marker = item.prefix(while: { !$0.isWhitespace })
                    HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                        Text(marker).font(.system(size: 13, weight: .semibold)).foregroundColor(AppTheme.Colors.quantumBlue).frame(minWidth: 22, alignment: .leading)
                        MarkdownText(String(item.dropFirst(marker.count)).trimmingCharacters(in: .whitespaces), font: .system(size: 14.5)).fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        case .codeBlock(let lang, let code):
            CodeBlockCard(snippet: CodeSnippet(language: lang ?? "text", code: code))
        case .formula(let formula):
            FormulaCard(formula: formula)
        case .image(let url, let alt):
            if let remote = URL(string: url), remote.scheme?.lowercased() == "https" {
                AsyncImage(url: remote) { phase in
                    switch phase {
                    case .success(let image): image.resizable().scaledToFit()
                    case .failure: Label(alt.isEmpty ? "图片暂时无法加载" : alt, systemImage: "photo")
                    default: ProgressView()
                    }
                }
                .frame(maxWidth: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .accessibilityLabel(alt.isEmpty ? "回答图片" : alt)
            } else {
                ImageCard(block: ImageBlock(assetName: url, caption: alt))
            }
        case .quote(let text):
            HighlightCard(text: text)
        case .divider:
            Rectangle().fill(AppTheme.Colors.border.opacity(0.5)).frame(height: 0.5).padding(.vertical, AppTheme.Spacing.xs)
        case .table(let t):
            TableCard(block: t)
        case .chart(let c):
            ChartCard(block: c)
        case .comic(let title, let panels):
            ComicCard(title: title, panels: panels)
        case .sourceCitations(let items):
            SourceCitationsCard(items: items)
        }
    }
}

private struct ComicCard: View {
    let title: String
    let panels: [ComicPanel]

    private let colors: [Color] = [
        Color(red: 0.95, green: 0.94, blue: 1.0),
        Color(red: 0.89, green: 0.98, blue: 0.96),
        Color(red: 1.0, green: 0.96, blue: 0.88)
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: "rectangle.3.group.bubble.left.fill")
                .font(.system(size: 17, weight: .bold, design: .rounded))
                .foregroundStyle(AppTheme.Colors.textPrimary)
            ForEach(Array(panels.enumerated()), id: \.offset) { index, panel in
                HStack(alignment: .top, spacing: 14) {
                    Image(systemName: panel.symbol)
                        .font(.system(size: 23, weight: .medium))
                        .foregroundStyle(AppTheme.Colors.quantumBlue)
                        .frame(width: 50, height: 50)
                        .background(.white.opacity(0.8), in: RoundedRectangle(cornerRadius: 16))
                    VStack(alignment: .leading, spacing: 7) {
                        Text("第 \(index + 1) 格 · \(panel.scene)")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                        Text("“\(panel.dialogue)”")
                            .font(.system(size: 14))
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 0)
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(colors[index], in: RoundedRectangle(cornerRadius: 18))
                .accessibilityElement(children: .combine)
            }
            Text("示意漫画 · 用类比帮助理解，不代替原文事实")
                .font(.system(size: 11))
                .foregroundStyle(AppTheme.Colors.textSecondary)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.white, in: RoundedRectangle(cornerRadius: 20))
        .accessibilityIdentifier("reading-comic-card")
    }
}

public struct HighlightCard: View {
    public let text: String

    public init(text: String) { self.text = text }

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            Image(systemName: "highlighter")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(AppTheme.Colors.emberOrange)
                .frame(width: 34, height: 34)
                .background(Color.white.opacity(0.72), in: Circle())
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text("高亮片段")
                    .font(AppTheme.Typography.micro.weight(.bold))
                    .foregroundStyle(AppTheme.Colors.emberOrange)
                MarkdownText(text, font: .system(.body, design: .serif), color: AppTheme.Colors.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .lineSpacing(4)
            }
        }
        .padding(AppTheme.Spacing.lg)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(
                colors: [AppTheme.Colors.bentoAmber.opacity(0.92), AppTheme.Colors.mistRose.opacity(0.54)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        .overlay(alignment: .topTrailing) {
            Text("“")
                .font(.system(size: 46, weight: .bold, design: .serif))
                .foregroundStyle(Color.white.opacity(0.62))
                .padding(.trailing, AppTheme.Spacing.md)
                .accessibilityHidden(true)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("高亮片段，\(text)")
    }
}

/// Groups a long answer by its authored structure without changing the server
/// block contract. Unheaded prose stays continuous instead of being cut by an
/// arbitrary block count.
public struct ReadingCardDeck: View {
    public let blocks: [MarkdownBlock]

    public init(blocks: [MarkdownBlock]) { self.blocks = blocks }

    static func answerBlocks(from answer: String, isStreaming: Bool = false) -> [MarkdownBlock] {
        MarkdownBlockParser.shared.parse(answer).compactMap { block in
            guard case .codeBlock(let language, let code) = block else { return block }
            let kind = language?.lowercased() ?? ""
            if kind == "json" && isStreaming { return nil }
            if kind == "comic" || kind == "chart"
                || (kind == "json" && (code.contains("\"panels\"") || code.contains("\"points\""))) {
                return isStreaming ? nil : .paragraph(kind == "chart" ? "图表暂时无法显示，请重试。" : "图解暂时无法显示，请重试。")
            }
            let codeLanguages: Set<String> = [
                "swift", "python", "javascript", "js", "typescript", "ts", "java", "kotlin",
                "go", "rust", "c", "cpp", "csharp", "sql", "bash", "sh", "html", "css", "json"
            ]
            return codeLanguages.contains(kind) ? block : .paragraph(code)
        }
    }

    public var body: some View {
        LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
            ForEach(Array(Self.pages(from: blocks).enumerated()), id: \.offset) { index, page in
                readingPage(page, index: index)
            }
        }
    }

    static func pages(from blocks: [MarkdownBlock]) -> [[MarkdownBlock]] {
        guard !blocks.isEmpty else { return [] }
        var pages: [[MarkdownBlock]] = []
        var current: [MarkdownBlock] = []

        func flush() {
            guard !current.isEmpty else { return }
            pages.append(current)
            current.removeAll(keepingCapacity: true)
        }

        for block in blocks {
            if block.isStandaloneReadingCard {
                flush()
                pages.append([block])
                continue
            }
            if case .heading = block, !current.isEmpty { flush() }
            current.append(block)
            if case .divider = block {
                flush()
            }
        }
        flush()
        return pages
    }

    private func readingPage(_ page: [MarkdownBlock], index: Int) -> some View {
        Group {
            if page.count == 1, page[0].isStandaloneReadingCard {
                MarkdownBlockCard(block: page[0])
            } else {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    ForEach(Array(page.enumerated()), id: \.offset) { _, block in
                        MarkdownBlockCard(block: block)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, index == 0 ? 0 : AppTheme.Spacing.sm)
                .overlay(alignment: .top) {
                    if index > 0 {
                        Divider().opacity(0.5)
                    }
                }
            }
        }
    }
}

private extension MarkdownBlock {
    var isStandaloneReadingCard: Bool {
        switch self {
        case .formula, .codeBlock, .table, .chart, .quote, .sourceCitations: true
        default: false
        }
    }
}

public struct SourceCitationsCard: View {
    public let items: [String]
    public init(items: [String]) { self.items = items }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                Image(systemName: "books.vertical.fill").font(.system(size: 11, weight: .semibold)).foregroundColor(AppTheme.Icons.live)
                Text("来源条目").font(.system(size: 11, weight: .bold)).foregroundColor(AppTheme.Colors.quantumCyan)
            }
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: "doc.text.magnifyingglass").font(.system(size: 10)).foregroundColor(AppTheme.Icons.tertiary).padding(.top, 2)
                    Text(item.trimmingCharacters(in: CharacterSet(charactersIn: "`*- "))).font(.system(size: 12, design: .monospaced)).foregroundColor(AppTheme.Colors.textSecondary).lineLimit(2)
                }
            }
        }
        .padding(AppTheme.Spacing.sm).frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.quantumCyan.opacity(0.06)).clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous).stroke(AppTheme.Colors.quantumCyan.opacity(0.25), lineWidth: 0.5))
        .pressBorderGlow(cornerRadius: AppTheme.Radius.md)
    }
}
