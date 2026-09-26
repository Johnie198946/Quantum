//
//  MarkdownBlockParser.swift
//  AIPlatformApp
//
//  极简单遍 Markdown 分块解析器（零冗余计算·极速纯原生）。
//

import Foundation

public struct ComicPanel: Hashable {
    public let scene: String
    public let dialogue: String
    public let symbol: String
}

public enum MarkdownBlock: Identifiable, Hashable {
    case heading(level: Int, text: String)
    case callout(label: String, text: String)
    case paragraph(String)
    case bulletList([String])
    case numberedList([String])
    case codeBlock(language: String?, code: String)
    case formula(String)
    case image(url: String, alt: String)
    case quote(String)
    case divider
    case table(TableBlock)
    case chart(ChartBlock)
    case comic(title: String, panels: [ComicPanel])
    case sourceCitations([String])

    public var id: String {
        switch self {
        case .heading(let l, let t): return "h\(l)_\(t.hashValue)"
        case .callout(let l, let t): return "c_\(l)_\(t.hashValue)"
        case .paragraph(let t): return "p_\(t.hashValue)"
        case .bulletList(let i): return "ul_\(i.hashValue)"
        case .numberedList(let i): return "ol_\(i.hashValue)"
        case .codeBlock(let l, let c): return "code_\(l ?? "")_\(c.hashValue)"
        case .formula(let f): return "formula_\(f.hashValue)"
        case .image(let url, let alt): return "image_\(url.hashValue)_\(alt.hashValue)"
        case .quote(let t): return "q_\(t.hashValue)"
        case .divider: return "divider"
        case .table(let t): return "tbl_\(t.id)"
        case .chart(let c): return "chr_\(c.id)"
        case .comic(let title, let panels): return "comic_\(title.hashValue)_\(panels.hashValue)"
        case .sourceCitations(let i): return "src_\(i.hashValue)"
        }
    }
}

public final class MarkdownBlockParser {
    public static let shared = MarkdownBlockParser()

    private final class CacheEntry: NSObject {
        let blocks: [MarkdownBlock]

        init(_ blocks: [MarkdownBlock]) {
            self.blocks = blocks
        }
    }

    private let cache: NSCache<NSString, CacheEntry> = {
        let cache = NSCache<NSString, CacheEntry>()
        cache.countLimit = 256
        cache.totalCostLimit = 8 * 1024 * 1024
        return cache
    }()

    public func parse(_ content: String, messageId: String = "") -> [MarkdownBlock] {
        guard !content.isEmpty else { return [] }
        let cacheKey = messageId as NSString
        if !messageId.isEmpty, let cached = cache.object(forKey: cacheKey) {
            return cached.blocks
        }
        let lines = content.components(separatedBy: "\n")
        var blocks: [MarkdownBlock] = []
        var index = 0
        var inCode = false, codeLang: String?, codeLines: [String] = []
        var formulaEnd: String?, formulaLines: [String] = []
        var pBuf: [String] = [], bBuf: [String] = [], nBuf: [String] = []

        func flushP() { if !pBuf.isEmpty { blocks.append(.paragraph(pBuf.joined(separator: "\n"))); pBuf.removeAll() } }
        func flushB() { if !bBuf.isEmpty { blocks.append(.bulletList(bBuf)); bBuf.removeAll() } }
        func flushN() { if !nBuf.isEmpty { blocks.append(.numberedList(nBuf)); nBuf.removeAll() } }
        func flushAll() { flushP(); flushB(); flushN() }

        while index < lines.count {
            let line = lines[index], trimmed = line.trimmingCharacters(in: .whitespaces)
            if let end = formulaEnd {
                if trimmed == end {
                    blocks.append(.formula(formulaLines.joined(separator: "\n")))
                    formulaEnd = nil; formulaLines.removeAll()
                } else { formulaLines.append(line) }
                index += 1; continue
            }
            if inCode {
                if trimmed.hasPrefix("```") {
                    let code = codeLines.joined(separator: "\n")
                    if ["math", "latex", "tex"].contains(codeLang?.lowercased() ?? "") {
                        blocks.append(.formula(code))
                    } else {
                        blocks.append(
                            Self.comic(language: codeLang, code: code)
                            ?? Self.chart(language: codeLang, code: code)
                            ?? .codeBlock(language: codeLang, code: code)
                        )
                    }
                    codeLines.removeAll(); codeLang = nil; inCode = false
                } else { codeLines.append(line) }
                index += 1; continue
            }
            if let formula = Self.singleLineFormula(trimmed) {
                flushAll(); blocks.append(.formula(formula)); index += 1; continue
            }
            if trimmed == "$$" || trimmed == #"\["# {
                flushAll(); formulaEnd = trimmed == "$$" ? "$$" : #"\]"#
                formulaLines.removeAll(); index += 1; continue
            }
            if trimmed.hasPrefix("```") {
                flushAll(); codeLang = trimmed.drop(while: { $0 == "`" }).trimmingCharacters(in: .whitespaces)
                if codeLang?.isEmpty == true { codeLang = nil }
                codeLines = []; inCode = true; index += 1; continue
            }
            if let image = Self.parseImage(trimmed) {
                flushAll(); blocks.append(image); index += 1; continue
            }
            if let (table, nextIdx) = Self.tryTable(lines: lines, start: index) {
                flushAll(); blocks.append(.table(table)); index = nextIdx; continue
            }
            if Self.isSource(trimmed) {
                flushAll(); var c: [String] = [], next = index + 1
                while next < lines.count {
                    let nt = lines[next].trimmingCharacters(in: .whitespaces)
                    if nt.isEmpty { next += 1; continue }
                    if let item = Self.parseBullet(nt) { c.append(item); next += 1 }
                    else if nt.hasPrefix("wiki/") || nt.hasPrefix("knowledge/") || nt.hasPrefix("raw/") || nt.hasPrefix("`") { c.append(nt); next += 1 }
                    else { break }
                }
                if !c.isEmpty { blocks.append(.sourceCitations(c)); index = next; continue }
            }
            if trimmed == "---" || trimmed == "***" || trimmed == "___" {
                flushAll(); blocks.append(.divider); index += 1; continue
            }
            if let (title, detail) = Self.parseLabeledSection(trimmed) {
                flushAll()
                blocks.append(.heading(level: 2, text: title))
                if !detail.isEmpty { blocks.append(.paragraph(detail)) }
                index += 1; continue
            }
            if let heading = Self.parseHeading(trimmed) {
                flushAll(); blocks.append(heading); index += 1; continue
            }
            if let callout = Self.parseCallout(trimmed) {
                flushAll(); blocks.append(callout); index += 1; continue
            }
            if trimmed.hasPrefix(">") {
                flushAll(); blocks.append(.quote(String(trimmed.dropFirst()).trimmingCharacters(in: .whitespaces))); index += 1; continue
            }
            if let item = Self.parseBullet(trimmed) {
                flushP(); flushN(); bBuf.append(item); index += 1; continue
            }
            if let item = Self.parseNumbered(trimmed) {
                flushP(); flushB(); nBuf.append(item); index += 1; continue
            }
            if trimmed.isEmpty { flushAll(); index += 1; continue }
            flushB(); flushN(); pBuf.append(line); index += 1
        }
        if inCode {
            let code = codeLines.joined(separator: "\n")
            blocks.append(["math", "latex", "tex"].contains(codeLang?.lowercased() ?? "") ? .formula(code) : .codeBlock(language: codeLang, code: code))
        }
        if formulaEnd != nil, !formulaLines.isEmpty { blocks.append(.formula(formulaLines.joined(separator: "\n"))) }
        flushAll()
        if !messageId.isEmpty {
            cache.setObject(
                CacheEntry(blocks),
                forKey: cacheKey,
                cost: min(content.utf8.count, 1_000_000)
            )
        }
        return blocks
    }

    private static func isSource(_ s: String) -> Bool {
        let c = s.trimmingCharacters(in: CharacterSet(charactersIn: "*_` "))
        return c.hasPrefix("来源条目") || c.hasPrefix("知识库来源") || c.hasPrefix("参考条目") || c.hasPrefix("引用条目") || c.hasPrefix("来源：") || c.hasPrefix("Sources:")
    }
    private static func parseHeading(_ s: String) -> MarkdownBlock? {
        if s.hasPrefix("#") {
            let l = s.prefix(while: { $0 == "#" }).count
            return .heading(level: min(max(l, 1), 6), text: s.dropFirst(l).trimmingCharacters(in: .whitespaces))
        }
        let cn = ["一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、"]
        return cn.contains(where: { s.hasPrefix($0) }) ? .heading(level: 2, text: s) : nil
    }
    private static func parseLabeledSection(_ s: String) -> (String, String)? {
        guard let marker = s.firstIndex(where: { $0 == "." || $0 == "、" }),
              Int(s[..<marker]) != nil else { return nil }
        let remainder = s[s.index(after: marker)...].trimmingCharacters(in: .whitespaces)
        guard remainder.first == "「", let close = remainder.firstIndex(of: "」") else { return nil }
        let title = String(remainder[remainder.index(after: remainder.startIndex)..<close])
        var detail = remainder[remainder.index(after: close)...].trimmingCharacters(in: .whitespaces)
        guard !title.isEmpty, detail.isEmpty || detail.first == "：" || detail.first == ":" else { return nil }
        if !detail.isEmpty { detail.removeFirst() }
        return (title, detail.trimmingCharacters(in: .whitespaces))
    }
    private static func parseCallout(_ s: String) -> MarkdownBlock? {
        guard s.hasPrefix("【"), let close = s.firstIndex(of: "】") else { return nil }
        return .callout(label: String(s[s.index(after: s.startIndex)..<close]), text: String(s[s.index(after: close)...]).trimmingCharacters(in: .whitespaces))
    }
    private static func singleLineFormula(_ s: String) -> String? {
        let pairs = [("$$", "$$"), (#"\["#, #"\]"#), (#"\("#, #"\)"#)]
        for (start, end) in pairs where s.hasPrefix(start) && s.hasSuffix(end) && s.count > start.count + end.count {
            return String(s.dropFirst(start.count).dropLast(end.count)).trimmingCharacters(in: .whitespaces)
        }
        guard s.hasPrefix("$"), s.hasSuffix("$"), s.count > 2, !s.hasPrefix("$$") else { return nil }
        return String(s.dropFirst().dropLast()).trimmingCharacters(in: .whitespaces)
    }
    private static func parseBullet(_ s: String) -> String? {
        (s.hasPrefix("- ") || s.hasPrefix("* ") || s.hasPrefix("+ ")) ? String(s.dropFirst(2)).trimmingCharacters(in: .whitespaces) : nil
    }
    private static func parseImage(_ s: String) -> MarkdownBlock? {
        guard s.hasPrefix("!["), s.hasSuffix(")"),
              let split = s.range(of: "]("), split.lowerBound > s.startIndex else { return nil }
        let alt = String(s[s.index(s.startIndex, offsetBy: 2)..<split.lowerBound])
        let url = String(s[split.upperBound..<s.index(before: s.endIndex)])
        guard !url.isEmpty else { return nil }
        return .image(url: url, alt: alt)
    }
    private static func parseNumbered(_ s: String) -> String? {
        guard let dot = s.firstIndex(where: { $0 == "." || $0 == "、" }), Int(s[..<dot]) != nil else { return nil }
        let contentStart = s.index(after: dot)
        guard s[dot] != "." || (contentStart < s.endIndex && s[contentStart].isWhitespace) else { return nil }
        return "\(s[..<dot]). \(s[contentStart...].trimmingCharacters(in: .whitespaces))"
    }
    private static func tryTable(lines: [String], start: Int) -> (TableBlock, Int)? {
        guard start + 1 < lines.count else { return nil }
        let hLine = lines[start].trimmingCharacters(in: .whitespaces), sLine = lines[start + 1].trimmingCharacters(in: .whitespaces)
        guard hLine.hasPrefix("|") && sLine.hasPrefix("|") && sLine.contains("-") else { return nil }
        let headers = tableCells(hLine)
        guard headers.count >= 2 else { return nil }
        var rows: [[String]] = [], curr = start + 2
        while curr < lines.count {
            let rLine = lines[curr].trimmingCharacters(in: .whitespaces)
            guard rLine.hasPrefix("|") else { break }
            rows.append(tableCells(rLine)); curr += 1
        }
        let title: String
        if headers.first?.contains("确认维度") == true
            || headers.contains(where: { $0.contains("已确认需求") }) {
            title = "需求确认单"
        } else {
            title = "数据统计表格"
        }
        return (TableBlock(title: title, headers: headers, rows: rows), curr)
    }
    private static func tableCells(_ line: String) -> [String] {
        var body = line
        if body.first == "|" { body.removeFirst() }
        if body.last == "|" { body.removeLast() }
        var cells = [""]
        var escaped = false
        for character in body {
            if character == "|", !escaped {
                cells.append("")
            } else {
                cells[cells.count - 1].append(character)
            }
            escaped = character == "\\" ? !escaped : false
        }
        return cells.map { $0.trimmingCharacters(in: .whitespaces) }
    }
    public static func chart(language lang: String?, code: String) -> MarkdownBlock? {
        guard let l = lang?.lowercased(), (l.contains("chart") || l == "json"), let d = code.data(using: .utf8),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return nil }
        let title = j["title"] as? String ?? "数据趋势图", summary = j["summary"] as? String ?? "", isBar = (j["type"] as? String ?? "") == "bar"
        var pts: [ChartPoint] = []
        if let raw = j["points"] as? [[String: Any]] {
            for p in raw { pts.append(ChartPoint(label: p["label"] as? String ?? "", value: (p["value"] as? Double) ?? Double(p["value"] as? Int ?? 0))) }
        }
        return pts.isEmpty ? nil : .chart(ChartBlock(title: title, chartType: isBar ? .bar : .line, series: [ChartSeries(name: "默认", points: pts)], summary: summary))
    }

    private static func comic(language: String?, code: String) -> MarkdownBlock? {
        guard ["comic", "json"].contains(language?.lowercased() ?? ""), let data = code.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let rawPanels = json["panels"] as? [[String: Any]], rawPanels.count == 3 else { return nil }
        let allowedSymbols: Set<String> = [
            "questionmark.circle.fill", "lightbulb.fill", "checkmark.seal.fill",
            "person.fill", "graduationcap.fill", "books.vertical.fill", "doc.text.fill", "puzzlepiece.fill"
        ]
        let panels = rawPanels.compactMap { raw -> ComicPanel? in
            guard let scene = raw["scene"] as? String, !scene.isEmpty,
                  let dialogue = raw["dialogue"] as? String, !dialogue.isEmpty else { return nil }
            let requested = raw["symbol"] as? String ?? ""
            return ComicPanel(
                scene: String(scene.prefix(120)), dialogue: String(dialogue.prefix(100)),
                symbol: allowedSymbols.contains(requested) ? requested : "books.vertical.fill"
            )
        }
        guard panels.count == 3 else { return nil }
        let title = String((json["title"] as? String ?? "三格漫画说明").prefix(48))
        return .comic(title: title, panels: panels)
    }
}

public struct ReadingSectionContent: Equatable {
    public let series: String?
    public let learningObjective: String?
    public let blocks: [MarkdownBlock]

    public static func parse(_ markdown: String) -> Self {
        let source = markdown.trimmingCharacters(in: .whitespacesAndNewlines)
        let seriesLabels = ["**连载：**", "**连载:**", "连载：", "连载:", "**Series:**", "Series:"]
        let objectiveLabels = [
            "**学习目标：**", "**学习目标:**", "学习目标：", "学习目标:",
            "**Learning objectives:**", "**Learning objective:**", "Learning objectives:", "Learning objective:"
        ]
        guard let objectiveRange = objectiveLabels.compactMap({ source.range(of: $0) }).min(by: {
            $0.lowerBound < $1.lowerBound
        }) else {
            return Self(series: nil, learningObjective: nil, blocks: MarkdownBlockParser.shared.parse(source))
        }

        var seriesText = String(source[..<objectiveRange.lowerBound])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        for label in seriesLabels where seriesText.hasPrefix(label) {
            seriesText.removeFirst(label.count)
            break
        }
        seriesText = seriesText.trimmingCharacters(in: CharacterSet(charactersIn: "* \n\t"))

        let remainder = String(source[objectiveRange.upperBound...])
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let objectiveEnd: String.Index
        if let paragraphEnd = remainder.range(of: "\n\n")?.lowerBound {
            objectiveEnd = paragraphEnd
        } else if let sentenceEnd = remainder.firstIndex(of: "。") {
            objectiveEnd = remainder.index(after: sentenceEnd)
        } else if let sentenceEnd = remainder.firstIndex(of: ".") {
            objectiveEnd = remainder.index(after: sentenceEnd)
        } else {
            objectiveEnd = remainder.endIndex
        }
        let objective = String(remainder[..<objectiveEnd]).trimmingCharacters(in: .whitespacesAndNewlines)
        let body = String(remainder[objectiveEnd...]).trimmingCharacters(in: .whitespacesAndNewlines)
        return Self(
            series: seriesText.isEmpty ? nil : seriesText,
            learningObjective: objective.isEmpty ? nil : objective,
            blocks: MarkdownBlockParser.shared.parse(body)
        )
    }
}

public struct ReadingResumeTarget: Equatable {
    public let blockIndex: Int
    public let characterOffset: Int

    static func attributedText(_ markdown: String) -> AttributedString {
        let rendered = InlineMathPresentation.segments(in: markdown)
            .map { $0.isMath ? MathFormulaPresentation.displayText($0.text) : $0.text }.joined()
        return (try? AttributedString(markdown: rendered)) ?? AttributedString(rendered)
    }

    public static func find(_ excerpt: String, in blocks: [MarkdownBlock]) -> Self? {
        let needle = excerpt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !needle.isEmpty else { return nil }
        var matches: [Self] = []
        for (index, block) in blocks.enumerated() {
            let text: String
            switch block {
            case .paragraph(let value), .quote(let value): text = value
            default: continue
            }
            let rendered = String(attributedText(text).characters)
            let range = (rendered as NSString).range(of: needle)
            if range.location != NSNotFound {
                let remaining = NSRange(location: NSMaxRange(range), length: (rendered as NSString).length - NSMaxRange(range))
                guard (rendered as NSString).range(of: needle, range: remaining).location == NSNotFound else { return nil }
                matches.append(Self(blockIndex: index, characterOffset: range.location))
            }
        }
        return matches.count == 1 ? matches[0] : nil
    }
}

extension LearningResumeDTO {
    /// Use the reader's own coordinates: backend Markdown tokens are not UI blocks.
    func visiblePoints(in section: KnowledgeBookSectionDTO, contentVersion: String) -> [LearningResumePointDTO] {
        guard section.id == sectionId,
              subscription.contentVersion == contentVersion,
              self.contentVersion == nil || self.contentVersion == contentVersion,
              let blockIndex, let characterOffset else { return [] }
        let blocks = ReadingSectionContent.parse(section.markdown).blocks
        let eligible = (candidates ?? keyPoints).compactMap { point -> (LearningResumePointDTO, ReadingResumeTarget)? in
            // Legacy responses only have detail. Accept it only when the reader
            // independently verifies a unique, already-reached source location.
            let excerpt = point.sourceExcerpt ?? (candidates == nil ? point.detail : "")
            guard point.sectionId == nil || point.sectionId == section.id,
                  let target = ReadingResumeTarget.find(excerpt, in: blocks),
                  target.blockIndex <= blockIndex,
                  target.blockIndex < blockIndex || target.characterOffset + (excerpt as NSString).length <= characterOffset
            else { return nil }
            return (point, target)
        }.sorted {
            let leftDistance = blockIndex - $0.1.blockIndex
            let rightDistance = blockIndex - $1.1.blockIndex
            if leftDistance != rightDistance { return leftDistance < rightDistance }
            if $0.0.score != $1.0.score { return ($0.0.score ?? 0) > ($1.0.score ?? 0) }
            return $0.1.characterOffset > $1.1.characterOffset
        }
        guard let first = eligible.first else { return [] }
        func bigrams(_ text: String) -> Set<String> {
            let chars = Array(text.lowercased().filter { !$0.isWhitespace && !$0.isPunctuation })
            return Set(zip(chars, chars.dropFirst()).map { String([$0.0, $0.1]) })
        }
        let firstWords = bigrams(first.0.detail)
        let distinct = eligible.dropFirst().filter {
            let words = bigrams($0.0.detail)
            let overlap = Double(firstWords.intersection(words).count) / Double(max(1, min(firstWords.count, words.count)))
            return overlap < 0.65
        }
        // Prefer a connection, but a second verified concept is also useful.
        let second = distinct.first { $0.0.kind == "connection" } ?? distinct.first
        return [first.0] + (second.map { [$0.0] } ?? [])
    }
}
