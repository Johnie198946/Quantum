//
//  KnowledgeNoteStore.swift
//  AIPlatformApp
//
//  Local-first Markdown vault used by the Knowledge tab.
//  Markdown files remain readable by Obsidian and any plain-text editor.
//

import Combine
import CryptoKit
import Foundation

public struct KnowledgeNote: Identifiable, Hashable, Sendable {
    public let id: String
    public var title: String
    public var body: String
    public var tags: [String]
    public var aliases: [String]
    public var createdAt: Date
    public var updatedAt: Date
    public var isPinned: Bool
    public var fileURL: URL
    public var outgoingLinks: [String]
    public var archivedAt: Date?
    public var mergedIntoNoteId: String?

    public init(
        id: String, title: String, body: String, tags: [String], aliases: [String],
        createdAt: Date, updatedAt: Date, isPinned: Bool, fileURL: URL,
        outgoingLinks: [String], archivedAt: Date? = nil,
        mergedIntoNoteId: String? = nil
    ) {
        self.id = id
        self.title = title
        self.body = body
        self.tags = tags
        self.aliases = aliases
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.isPinned = isPinned
        self.fileURL = fileURL
        self.outgoingLinks = outgoingLinks
        self.archivedAt = archivedAt
        self.mergedIntoNoteId = mergedIntoNoteId
    }

    public var preview: String {
        var text = body
            .replacingOccurrences(of: #"!\[\[[^\]]+\]\]"#, with: "附件", options: .regularExpression)
        if let expression = try? NSRegularExpression(pattern: #"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]"#) {
            let matches = expression.matches(in: text, range: NSRange(text.startIndex..., in: text))
            for match in matches.reversed() {
                guard let fullRange = Range(match.range(at: 0), in: text),
                      let titleRange = Range(match.range(at: 1), in: text) else { continue }
                let aliasRange = Range(match.range(at: 2), in: text)
                let replacement = aliasRange.map { String(text[$0]) } ?? String(text[titleRange])
                text.replaceSubrange(fullRange, with: replacement)
            }
        }
        return text
            .replacingOccurrences(of: #"[#>*_`=\-\[\]]"#, with: "", options: .regularExpression)
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .prefix(3)
            .joined(separator: " ")
    }

    public var isDailyNote: Bool {
        tags.contains(where: { $0.caseInsensitiveCompare("daily") == .orderedSame })
    }
}

public struct KnowledgeNoteIndex: Sendable {
    public var tags: [String] = []
    public var previewsByNoteID: [String: String] = [:]
    public var backlinkCountsByNoteID: [String: Int] = [:]
}

@MainActor
public final class KnowledgeNoteStore: ObservableObject {
    public static let shared = KnowledgeNoteStore()

    @Published public private(set) var notes: [KnowledgeNote] = []
    @Published public private(set) var archivedNotes: [KnowledgeNote] = []
    @Published public private(set) var trashedNotes: [KnowledgeNote] = []
    @Published public private(set) var index = KnowledgeNoteIndex()
    @Published public private(set) var isLoading = false
    @Published public private(set) var lastError: String?

    @Published var illustrationJobs: [String: NoteIllustrationJob] = [:]
    var activeNoteDrafts: [String: String] = [:]
    private var illustrationTasks: [String: Task<Void, Never>] = [:]
    private let fileManager = FileManager.default
    private var tenantNamespace = "unconfigured"
    private var userNamespace = "unconfigured"
    @Published public private(set) var accountFingerprint = "unconfigured"
    private let isoFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    public var vaultDirectory: URL {
        let documents = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? fileManager.temporaryDirectory
        return documents
            .appendingPathComponent("KnowledgeVault/accounts", isDirectory: true)
            .appendingPathComponent(tenantNamespace, isDirectory: true)
            .appendingPathComponent(userNamespace, isDirectory: true)
    }

    public var allTags: [String] { index.tags }

    public var archiveDirectory: URL {
        vaultDirectory.appendingPathComponent(".archive", isDirectory: true)
    }

    public var actionDirectory: URL {
        vaultDirectory.appendingPathComponent(".actions", isDirectory: true)
    }

    public var authorizationScope: String {
        "\(tenantNamespace.prefix(16)):\(userNamespace.prefix(16))"
    }

    init() {}

    public func activate(tenantKey: String, userId: String) {
        let tenant = Self.namespace(tenantKey)
        let user = Self.namespace(userId)
        guard tenant != tenantNamespace || user != userNamespace else { return }
        illustrationTasks.values.forEach { $0.cancel() }
        illustrationTasks.removeAll()
        illustrationJobs.removeAll()
        activeNoteDrafts.removeAll()
        notes.removeAll()
        archivedNotes.removeAll()
        trashedNotes.removeAll()
        index = KnowledgeNoteIndex()
        tenantNamespace = tenant
        userNamespace = user
        accountFingerprint = "\(tenant):\(user)"
        reload()
        loadIllustrationJobs()
    }

    public func deactivate() {
        illustrationTasks.values.forEach { $0.cancel() }
        illustrationTasks.removeAll()
        illustrationJobs.removeAll()
        activeNoteDrafts.removeAll()
        notes.removeAll()
        archivedNotes.removeAll()
        trashedNotes.removeAll()
        index = KnowledgeNoteIndex()
        tenantNamespace = "unconfigured"
        userNamespace = "unconfigured"
        accountFingerprint = "unconfigured"
        lastError = nil
    }

    private static func namespace(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8)).prefix(10)
            .map { String(format: "%02x", $0) }.joined()
    }

    public func reload() {
        isLoading = true
        defer { isLoading = false }

        do {
            try fileManager.createDirectory(at: vaultDirectory, withIntermediateDirectories: true)
            var loaded: [KnowledgeNote] = []
            var archived: [KnowledgeNote] = []
            var trashed: [KnowledgeNote] = []
            if let enumerator = fileManager.enumerator(
                at: vaultDirectory,
                includingPropertiesForKeys: [.isRegularFileKey, .contentModificationDateKey],
                options: []
            ) {
                for case let url as URL in enumerator where url.pathExtension.lowercased() == "md" {
                    if let note = try parseNote(at: url) {
                        if url.path.contains("/.trash/") {
                            trashed.append(note)
                        } else if url.path.contains("/.archive/") {
                            archived.append(note)
                        } else {
                            loaded.append(note)
                        }
                    }
                }
            }

            notes = sorted(loaded)
            archivedNotes = sorted(archived)
            trashedNotes = sorted(trashed)
            rebuildIndex()
            lastError = nil
        } catch {
            lastError = "无法读取本地笔记：\(error.localizedDescription)"
        }
    }

    public func clearError() {
        lastError = nil
    }

    /// Restore the authenticated account's durable server snapshot after login or reinstall.
    /// Existing local edits only yield to a strictly newer cloud copy.
    public func restoreFromCloud() async {
        guard accountFingerprint != "unconfigured" else { return }
        let expectedFingerprint = accountFingerprint
        do {
            let response = try await APIClient.shared.fetchKnowledgeNotes()
            guard accountFingerprint == expectedFingerprint else { return }
            try restoreFromCloudSnapshot(response)
            lastError = nil
        } catch {
            guard accountFingerprint == expectedFingerprint else { return }
            lastError = "云端笔记暂未同步：\(error.localizedDescription)"
        }
    }

    /// Materialize a server-authenticated snapshot in the local vault so a
    /// server-proposed action can reference notes absent from this device.
    public func restoreFromCloudSnapshot(_ response: CloudKnowledgeNotesResponse) throws {
        for snapshot in response.items {
            try applyCloudSnapshot(snapshot)
        }
        reload()
    }

    private func applyCloudSnapshot(_ snapshot: CloudKnowledgeNoteDTO) throws {
        // A refresh must not undo a deletion on this device. Restore explicitly.
        guard !trashedNotes.contains(where: { $0.id == snapshot.noteId }) else { return }
        let sameState = (snapshot.archived ? archivedNotes : notes).filter { $0.id == snapshot.noteId }
        let oppositeState = (snapshot.archived ? notes : archivedNotes).filter { $0.id == snapshot.noteId }
        if let preferred = sameState.first {
            // One logical note ID may never exist in both active and archived views.
            // Remove stale duplicates even when the preferred copy already matches cloud.
            for duplicate in Array(sameState.dropFirst()) + oppositeState {
                try? fileManager.removeItem(at: duplicate.fileURL)
            }
            let localHash = SHA256.hash(data: Data(markdown(for: preferred).utf8))
                .map { String(format: "%02x", $0) }.joined()
            if localHash == snapshot.contentHash { return }
            let remoteUpdatedAt = snapshot.updatedAt.flatMap(Self.parseServerDate)
            if remoteUpdatedAt == nil || remoteUpdatedAt! <= preferred.updatedAt { return }
            try? fileManager.removeItem(at: preferred.fileURL)
        } else if let existing = oppositeState.first {
            let remoteUpdatedAt = snapshot.updatedAt.flatMap(Self.parseServerDate)
            if remoteUpdatedAt == nil || remoteUpdatedAt! <= existing.updatedAt { return }
            for duplicate in oppositeState {
                try? fileManager.removeItem(at: duplicate.fileURL)
            }
        }

        let directory = snapshot.archived ? archiveDirectory : vaultDirectory
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        let destination = directory.appendingPathComponent("\(snapshot.noteId).md")
        try snapshot.markdown.write(to: destination, atomically: true, encoding: .utf8)
    }

    private static func parseServerDate(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) { return date }
        return ISO8601DateFormatter().date(from: value)
    }

    public func markdown(for note: KnowledgeNote) -> String {
        encode(note)
    }

    public func contentHash(for note: KnowledgeNote) -> String {
        SHA256.hash(data: Data(encode(note).utf8))
            .map { String(format: "%02x", $0) }
            .joined()
    }

    @discardableResult
    public func createNote(id: String = UUID().uuidString.lowercased(), title: String = "无标题", body: String = "", tags: [String] = []) -> KnowledgeNote? {
        if let existing = note(id: id) { return existing }
        guard !trashedNotes.contains(where: { $0.id == id }) else { return nil }
        let now = Date()
        let note = KnowledgeNote(
            id: id,
            title: title,
            body: body,
            tags: normalized(tags + extractInlineTags(from: body)),
            aliases: [],
            createdAt: now,
            updatedAt: now,
            isPinned: false,
            fileURL: uniqueURL(for: title),
            outgoingLinks: extractWikiLinks(from: body)
        )
        do {
            try write(note)
            notes.insert(note, at: 0)
            notes = sorted(notes)
            rebuildIndex()
            lastError = nil
            return note
        } catch {
            lastError = "无法创建笔记：\(error.localizedDescription)"
            return nil
        }
    }

    @discardableResult
    public func dailyNote(for date: Date = Date()) -> KnowledgeNote? {
        let calendar = Calendar.current
        if let existing = notes.first(where: { $0.isDailyNote && calendar.isDate($0.createdAt, inSameDayAs: date) }) {
            return existing
        }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_Hans_CN")
        formatter.dateFormat = "yyyy-MM-dd"
        let title = formatter.string(from: date)
        let body = """
        ## 今日重点

        - [ ] 

        ## 记录

        
        """
        return createNote(title: title, body: body, tags: ["daily"])
    }

    @discardableResult
    public func save(
        id: String,
        title: String,
        body: String,
        tags: [String],
        isPinned: Bool
    ) -> KnowledgeNote? {
        guard let index = notes.firstIndex(where: { $0.id == id }) else { return nil }
        let oldTitle = notes[index].title
        var note = notes[index]
        let cleanedTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        note.title = cleanedTitle.isEmpty ? "无标题" : cleanedTitle
        note.body = body
        note.tags = normalized(tags + extractInlineTags(from: body))
        if Set(note.tags) == Set(notes[index].tags) { note.tags = notes[index].tags }
        note.isPinned = isPinned
        note.outgoingLinks = extractWikiLinks(from: body)
        guard note != notes[index] else { return notes[index] }
        note.updatedAt = Date()

        if oldTitle != note.title {
            note.fileURL = uniqueURL(for: note.title, excluding: note.fileURL)
        }

        do {
            try write(note)
            if notes[index].fileURL != note.fileURL, fileManager.fileExists(atPath: notes[index].fileURL.path) {
                try fileManager.removeItem(at: notes[index].fileURL)
            }
            notes[index] = note
            if oldTitle != note.title {
                try updateIncomingLinks(from: oldTitle, to: note.title, excluding: note.id)
            }
            notes = sorted(notes)
            rebuildIndex()
            lastError = nil
            return notes.first(where: { $0.id == id })
        } catch {
            lastError = "自动保存失败：\(error.localizedDescription)"
            return nil
        }
    }

    public func togglePin(id: String) {
        guard let note = note(id: id) else { return }
        _ = save(id: id, title: note.title, body: note.body, tags: note.tags, isPinned: !note.isPinned)
    }

    /// Recoverable deletion: notes are moved into KnowledgeVault/.trash.
    @discardableResult
    public func moveToTrash(id: String) -> Bool {
        guard var note = note(id: id) else { return false }
        do {
            let trash = vaultDirectory.appendingPathComponent(".trash", isDirectory: true)
            try fileManager.createDirectory(at: trash, withIntermediateDirectories: true)
            var destination = trash.appendingPathComponent(note.fileURL.lastPathComponent)
            if fileManager.fileExists(atPath: destination.path) {
                destination = trash.appendingPathComponent("\(UUID().uuidString)-\(note.fileURL.lastPathComponent)")
            }
            try fileManager.moveItem(at: note.fileURL, to: destination)
            note.fileURL = destination
            notes.removeAll { $0.id == id }
            trashedNotes = sorted(trashedNotes + [note])
            rebuildIndex()
            lastError = nil
            return true
        } catch {
            lastError = "无法移到废纸篓：\(error.localizedDescription)"
            return false
        }
    }

    /// Restores this device's copy without overwriting another note or changing its edit time.
    @discardableResult
    public func restoreTrashedNote(id: String) -> KnowledgeNote? {
        guard let index = trashedNotes.firstIndex(where: { $0.id == id }) else { return nil }
        guard anyNote(id: id) == nil else {
            lastError = "已有同一篇笔记，未覆盖现有内容。"
            return nil
        }
        var note = trashedNotes[index]
        do {
            let destination = uniqueURL(for: note.title)
            try fileManager.moveItem(at: note.fileURL, to: destination)
            note.fileURL = destination
            trashedNotes.remove(at: index)
            notes = sorted(notes + [note])
            rebuildIndex()
            lastError = nil
            return note
        } catch {
            lastError = "无法恢复笔记：\(error.localizedDescription)"
            return nil
        }
    }

    public static func parseTags(_ text: String) -> [String] {
        Array(Set(text.split(whereSeparator: { ",，、".contains($0) })
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines)
                .trimmingCharacters(in: CharacterSet(charactersIn: "#")) }
            .filter { !$0.isEmpty })).sorted()
    }

    /// Merged source notes remain recoverable but are excluded from active search and sync.
    @discardableResult
    public func archive(id: String, mergedInto: String? = nil) -> KnowledgeNote? {
        guard let index = notes.firstIndex(where: { $0.id == id }) else {
            return archivedNotes.first { $0.id == id }
        }
        var note = notes[index]
        do {
            try fileManager.createDirectory(at: archiveDirectory, withIntermediateDirectories: true)
            var destination = archiveDirectory.appendingPathComponent(note.fileURL.lastPathComponent)
            if fileManager.fileExists(atPath: destination.path) {
                destination = archiveDirectory.appendingPathComponent("\(note.id)-\(note.fileURL.lastPathComponent)")
            }
            try fileManager.moveItem(at: note.fileURL, to: destination)
            note.fileURL = destination
            note.archivedAt = Date()
            note.mergedIntoNoteId = mergedInto
            try write(note)
            notes.remove(at: index)
            archivedNotes = sorted(archivedNotes + [note])
            rebuildIndex()
            lastError = nil
            return note
        } catch {
            lastError = "无法归档笔记：\(error.localizedDescription)"
            return nil
        }
    }

    @discardableResult
    public func restoreArchivedNote(id: String) -> KnowledgeNote? {
        guard let index = archivedNotes.firstIndex(where: { $0.id == id }) else { return nil }
        var note = archivedNotes[index]
        do {
            let destination = uniqueURL(for: note.title)
            try fileManager.moveItem(at: note.fileURL, to: destination)
            note.fileURL = destination
            note.archivedAt = nil
            note.mergedIntoNoteId = nil
            try write(note)
            archivedNotes.remove(at: index)
            notes = sorted(notes + [note])
            rebuildIndex()
            lastError = nil
            return note
        } catch {
            lastError = "无法恢复归档笔记：\(error.localizedDescription)"
            return nil
        }
    }

    public func note(id: String) -> KnowledgeNote? {
        notes.first { $0.id == id }
    }

    public func archivedNote(id: String) -> KnowledgeNote? {
        archivedNotes.first { $0.id == id }
    }

    public func anyNote(id: String) -> KnowledgeNote? {
        note(id: id) ?? archivedNote(id: id)
    }

    public func note(matchingLink link: String) -> KnowledgeNote? {
        let target = link.trimmingCharacters(in: .whitespacesAndNewlines)
        return notes.first { note in
            note.title.caseInsensitiveCompare(target) == .orderedSame
                || note.fileURL.deletingPathExtension().lastPathComponent.caseInsensitiveCompare(target) == .orderedSame
                || note.aliases.contains(where: { $0.caseInsensitiveCompare(target) == .orderedSame })
        }
    }

    public func backlinks(to note: KnowledgeNote) -> [KnowledgeNote] {
        notes.filter { candidate in
            candidate.id != note.id && candidate.outgoingLinks.contains { link in
                link.caseInsensitiveCompare(note.title) == .orderedSame
                    || note.aliases.contains(where: { $0.caseInsensitiveCompare(link) == .orderedSame })
            }
        }
    }

    public func unresolvedLinks(in note: KnowledgeNote) -> [String] {
        note.outgoingLinks.filter { self.note(matchingLink: $0) == nil }
    }

    public func search(_ query: String, tag: String? = nil) -> [KnowledgeNote] {
        search(query, tags: tag.map { Set([$0]) } ?? [])
    }

    /// Every selected tag must be present (logical AND), matching the knowledge
    /// workspace's multi-tag filtering contract.
    public func search(_ query: String, tags: Set<String>) -> [KnowledgeNote] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return notes.filter { note in
            let noteTags = Set(note.tags.map { $0.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current) })
            let requestedTags = Set(tags.map { $0.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current) })
            let tagMatches = requestedTags.isSubset(of: noteTags)
            let queryMatches = trimmed.isEmpty
                || note.title.localizedCaseInsensitiveContains(trimmed)
                || note.body.localizedCaseInsensitiveContains(trimmed)
                || note.tags.contains(where: { $0.localizedCaseInsensitiveContains(trimmed) })
            return tagMatches && queryMatches
        }
    }

    private func rebuildIndex() {
        var previews: [String: String] = [:]
        var titleOwners: [String: String] = [:]
        var backlinks = Dictionary(uniqueKeysWithValues: notes.map { ($0.id, 0) })

        for note in notes {
            previews[note.id] = note.preview
            for title in [note.title] + note.aliases {
                titleOwners[normalizedLinkKey(title)] = note.id
            }
        }
        for source in notes {
            for link in source.outgoingLinks {
                guard let targetID = titleOwners[normalizedLinkKey(link)], targetID != source.id else { continue }
                backlinks[targetID, default: 0] += 1
            }
        }

        index = KnowledgeNoteIndex(
            tags: Array(Set(notes.flatMap(\.tags))).sorted {
                $0.localizedStandardCompare($1) == .orderedAscending
            },
            previewsByNoteID: previews,
            backlinkCountsByNoteID: backlinks
        )
    }

    private func normalizedLinkKey(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
            .folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
    }

    private func parseNote(at url: URL) throws -> KnowledgeNote? {
        let content = try String(contentsOf: url, encoding: .utf8)
        let lines = content.components(separatedBy: .newlines)
        var metadata: [String: String] = [:]
        var listValues: [String: [String]] = [:]
        var bodyStart = 0

        if lines.first?.trimmingCharacters(in: .whitespaces) == "---",
           let closing = lines.dropFirst().firstIndex(where: { $0.trimmingCharacters(in: .whitespaces) == "---" }) {
            var activeListKey: String?
            for line in lines[1..<closing] {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("- "), let key = activeListKey {
                    listValues[key, default: []].append(unquote(String(trimmed.dropFirst(2))))
                } else if let separator = trimmed.firstIndex(of: ":") {
                    let key = String(trimmed[..<separator]).trimmingCharacters(in: .whitespaces)
                    let value = String(trimmed[trimmed.index(after: separator)...]).trimmingCharacters(in: .whitespaces)
                    metadata[key] = unquote(value)
                    activeListKey = value.isEmpty ? key : nil
                    if value.hasPrefix("[") && value.hasSuffix("]") {
                        listValues[key] = value.dropFirst().dropLast().split(separator: ",").map {
                            unquote(String($0).trimmingCharacters(in: .whitespaces))
                        }
                    }
                }
            }
            bodyStart = closing + 1
        }

        let body = lines.dropFirst(bodyStart).joined(separator: "\n").trimmingCharacters(in: .newlines)
        let attributes = try? url.resourceValues(forKeys: [.contentModificationDateKey, .creationDateKey])
        let fallbackDate = attributes?.contentModificationDate ?? Date()
        let title = metadata["title"].flatMap { $0.isEmpty ? nil : $0 }
            ?? url.deletingPathExtension().lastPathComponent
        let frontmatterTags = listValues["tags"] ?? metadata["tags"].map { [$0] } ?? []
        let created = metadata["created"].flatMap(isoFormatter.date(from:))
            ?? attributes?.creationDate
            ?? fallbackDate
        let updated = metadata["updated"].flatMap(isoFormatter.date(from:)) ?? fallbackDate

        return KnowledgeNote(
            id: metadata["id"].flatMap { $0.isEmpty ? nil : $0 }
                ?? url.deletingPathExtension().lastPathComponent,
            title: title,
            body: body,
            tags: normalized(frontmatterTags + extractInlineTags(from: body)),
            aliases: normalized(listValues["aliases"] ?? []),
            createdAt: created,
            updatedAt: updated,
            isPinned: metadata["pinned"] == "true",
            fileURL: url,
            outgoingLinks: extractWikiLinks(from: body),
            archivedAt: metadata["archived_at"].flatMap(isoFormatter.date(from:)),
            mergedIntoNoteId: metadata["merged_into"].flatMap { $0.isEmpty ? nil : $0 }
        )
    }

    private func write(_ note: KnowledgeNote) throws {
        try fileManager.createDirectory(
            at: note.fileURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let content = encode(note)
        try content.write(to: note.fileURL, atomically: true, encoding: .utf8)
    }

    private func encode(_ note: KnowledgeNote) -> String {
        var lines = [
            "---",
            "id: \(yamlString(note.id))",
            "title: \(yamlString(note.title))",
            "created: \(isoFormatter.string(from: note.createdAt))",
            "updated: \(isoFormatter.string(from: note.updatedAt))",
            "pinned: \(note.isPinned ? "true" : "false")",
            note.archivedAt.map { "archived_at: \(isoFormatter.string(from: $0))" } ?? "archived_at:",
            note.mergedIntoNoteId.map { "merged_into: \(yamlString($0))" } ?? "merged_into:",
            note.tags.isEmpty ? "tags: []" : "tags:",
        ]
        lines.append(contentsOf: note.tags.map { "  - \(yamlString($0))" })
        lines.append(note.aliases.isEmpty ? "aliases: []" : "aliases:")
        lines.append(contentsOf: note.aliases.map { "  - \(yamlString($0))" })
        lines.append("---")
        lines.append("")
        lines.append(note.body)
        lines.append("")
        return lines.joined(separator: "\n")
    }

    private func updateIncomingLinks(from oldTitle: String, to newTitle: String, excluding id: String) throws {
        guard !oldTitle.isEmpty, oldTitle != newTitle else { return }
        let escaped = NSRegularExpression.escapedPattern(for: oldTitle)
        let pattern = #"\[\[("# + escaped + #")((?:#[^\]|]+)?(?:\|[^\]]+)?)\]\]"#
        let regex = try NSRegularExpression(pattern: pattern, options: [.caseInsensitive])

        for index in notes.indices where notes[index].id != id {
            let body = notes[index].body
            let range = NSRange(body.startIndex..., in: body)
            let replaced = regex.stringByReplacingMatches(in: body, range: range, withTemplate: "[[\(newTitle)$2]]")
            guard replaced != body else { continue }
            notes[index].body = replaced
            notes[index].outgoingLinks = extractWikiLinks(from: replaced)
            notes[index].updatedAt = Date()
            try write(notes[index])
        }
    }

    private func extractWikiLinks(from text: String) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: #"!?\[\[([^\]|#]+)"#) else { return [] }
        let range = NSRange(text.startIndex..., in: text)
        return normalized(regex.matches(in: text, range: range).compactMap { match in
            guard let swiftRange = Range(match.range(at: 1), in: text) else { return nil }
            return String(text[swiftRange]).trimmingCharacters(in: .whitespacesAndNewlines)
        })
    }

    private func extractInlineTags(from text: String) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: #"#([\p{L}_][\p{L}\p{N}_/-]*)"#) else { return [] }
        let range = NSRange(text.startIndex..., in: text)
        return normalized(regex.matches(in: text, range: range).compactMap { match in
            guard let swiftRange = Range(match.range(at: 1), in: text) else { return nil }
            return String(text[swiftRange])
        })
    }

    private func uniqueURL(for title: String, excluding currentURL: URL? = nil) -> URL {
        let base = safeFilename(title)
        var candidate = vaultDirectory.appendingPathComponent(base).appendingPathExtension("md")
        var suffix = 2
        while fileManager.fileExists(atPath: candidate.path) && candidate != currentURL {
            candidate = vaultDirectory.appendingPathComponent("\(base)-\(suffix)").appendingPathExtension("md")
            suffix += 1
        }
        return candidate
    }

    private func safeFilename(_ title: String) -> String {
        let invalid = CharacterSet(charactersIn: "/\\:*?\"<>|#[]")
        let cleaned = title
            .components(separatedBy: invalid)
            .joined(separator: "-")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return String((cleaned.isEmpty ? "无标题" : cleaned).prefix(80))
    }

    private func sorted(_ values: [KnowledgeNote]) -> [KnowledgeNote] {
        values.sorted {
            if $0.isPinned != $1.isPinned { return $0.isPinned }
            if $0.updatedAt != $1.updatedAt { return $0.updatedAt > $1.updatedAt }
            return $0.title.localizedStandardCompare($1.title) == .orderedAscending
        }
    }

    private func normalized(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.compactMap { raw in
            let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty else { return nil }
            let key = value.lowercased()
            guard seen.insert(key).inserted else { return nil }
            return value
        }
    }

    private func yamlString(_ value: String) -> String {
        "\"\(value.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\""))\""
    }

    private func unquote(_ value: String) -> String {
        guard value.count >= 2,
              (value.hasPrefix("\"") && value.hasSuffix("\"") || value.hasPrefix("'") && value.hasSuffix("'"))
        else { return value }
        return String(value.dropFirst().dropLast())
            .replacingOccurrences(of: "\\\"", with: "\"")
            .replacingOccurrences(of: "\\\\", with: "\\")
    }

    private func seedStarterNotes() throws {
        let welcome = KnowledgeNote(
            id: UUID().uuidString.lowercased(),
            title: "欢迎使用知识笔记",
            body: """
            这里是你的本地 Markdown 笔记空间。每篇笔记都是普通的 `.md` 文件，可以使用 Obsidian 或其他文本编辑器打开。

            ## 从这里开始

            - 创建一篇新笔记
            - 输入 `[[灵感收集]]` 建立双向链接
            - 使用 `#项目/示例` 添加层级标签
            - 打开每日笔记记录今天

            > [!tip] 本地优先
            > 笔记默认保存在设备的 `KnowledgeVault` 文件夹中。

            继续阅读 [[灵感收集]]。
            """,
            tags: ["入门"],
            aliases: ["开始"],
            createdAt: Date(),
            updatedAt: Date(),
            isPinned: true,
            fileURL: uniqueURL(for: "欢迎使用知识笔记"),
            outgoingLinks: ["灵感收集"]
        )
        let ideas = KnowledgeNote(
            id: UUID().uuidString.lowercased(),
            title: "灵感收集",
            body: """
            随手记下想法，再把它们连接到相关页面。

            ## Inbox

            - [ ] 尝试创建第一篇项目笔记
            - [ ] 在正文里输入 `[[欢迎使用知识笔记]]`

            返回 [[欢迎使用知识笔记]]。
            """,
            tags: ["inbox"],
            aliases: [],
            createdAt: Date(),
            updatedAt: Date(),
            isPinned: false,
            fileURL: uniqueURL(for: "灵感收集"),
            outgoingLinks: ["欢迎使用知识笔记"]
        )
        try write(welcome)
        try write(ideas)
    }
}

public struct KnowledgeActionExecutionResult: Sendable {
    public let state: KnowledgeActionState
    public let noteIds: [String]
    public let message: String?
}

private struct KnowledgeActionReceipt: Codable {
    let actionId: String
    let actionDigest: String
    let accountFingerprint: String
    var status: KnowledgeActionState
    var resultNoteIds: [String]
    var updatedAt: Date
}

@MainActor
protocol KnowledgeActionSynchronizing: AnyObject {
    func enqueueIllustrations(store: KnowledgeNoteStore, id: String, step: KnowledgeActionStep, requestID: String)
    func fetchKnowledgeNotes(includeArchived: Bool) async throws -> CloudKnowledgeNotesResponse
    func syncKnowledgeNote(id: String, markdown: String, updatedAt: Date, baseHash: String?, credentialGeneration: UInt64) async throws
    func archiveKnowledgeNote(id: String, mergedIntoNoteId: String?, expectedContentHash: String?) async throws
    func mergeKnowledgeNotes(_ body: KnowledgeNoteMergeRequestDTO) async throws -> KnowledgeNoteMergeResponseDTO
    func restoreKnowledgeNote(id: String) async throws
    func trashKnowledgeNote(id: String) async throws
    func commitKnowledgeAction(id: String, capability: String, actionDigest: String, status: String, resultNoteIds: [String], errorCode: String?) async throws
    func resumeKnowledgeActionSync(id: String, actionDigest: String, status: String, resultNoteIds: [String], errorCode: String?) async throws
    func discardKnowledgeAction(id: String, capability: String, actionDigest: String) async throws
}

@MainActor
private final class LiveKnowledgeActionSynchronizer: KnowledgeActionSynchronizing {
    static let shared = LiveKnowledgeActionSynchronizer()

    func enqueueIllustrations(store: KnowledgeNoteStore, id: String, step: KnowledgeActionStep, requestID: String) {
        let explicit = step.kind == "illustrate_note"
        let anchor = step.illustrationAnchor ?? ""
        store.startIllustrations(id: id, mode: anchor.isEmpty ? "auto" : "manual", anchor: anchor,
            brief: step.illustrationBrief ?? "", retry: step.illustrationAction == "retry",
            insert: explicit ? (step.illustrationAction == "retry" ? step.illustrationInsert : step.illustrationInsert ?? false) : nil, requestID: requestID, explicit: explicit)
    }

    func fetchKnowledgeNotes(includeArchived: Bool) async throws -> CloudKnowledgeNotesResponse {
        try await APIClient.shared.fetchKnowledgeNotes(includeArchived: includeArchived)
    }

    func syncKnowledgeNote(id: String, markdown: String, updatedAt: Date, baseHash: String?, credentialGeneration: UInt64) async throws {
        try await APIClient.shared.syncKnowledgeNote(
            id: id, markdown: markdown, updatedAt: updatedAt, baseHash: baseHash,
            credentialGeneration: credentialGeneration
        )
    }

    func archiveKnowledgeNote(id: String, mergedIntoNoteId: String?, expectedContentHash: String?) async throws {
        try await APIClient.shared.archiveKnowledgeNote(id: id, mergedIntoNoteId: mergedIntoNoteId, expectedContentHash: expectedContentHash)
    }

    func mergeKnowledgeNotes(_ body: KnowledgeNoteMergeRequestDTO) async throws -> KnowledgeNoteMergeResponseDTO {
        try await APIClient.shared.mergeKnowledgeNotes(body)
    }

    func restoreKnowledgeNote(id: String) async throws {
        try await APIClient.shared.restoreKnowledgeNote(id: id)
    }

    func trashKnowledgeNote(id: String) async throws {
        try await APIClient.shared.trashKnowledgeNote(id: id)
    }

    func commitKnowledgeAction(id: String, capability: String, actionDigest: String, status: String, resultNoteIds: [String], errorCode: String?) async throws {
        _ = try await APIClient.shared.commitKnowledgeAction(
            id: id, capability: capability, actionDigest: actionDigest,
            status: status, resultNoteIds: resultNoteIds, errorCode: errorCode
        )
    }

    func resumeKnowledgeActionSync(id: String, actionDigest: String, status: String, resultNoteIds: [String], errorCode: String?) async throws {
        _ = try await APIClient.shared.resumeKnowledgeActionSync(
            id: id, actionDigest: actionDigest, status: status,
            resultNoteIds: resultNoteIds, errorCode: errorCode
        )
    }

    func discardKnowledgeAction(id: String, capability: String, actionDigest: String) async throws {
        try await APIClient.shared.discardKnowledgeAction(
            id: id, capability: capability, actionDigest: actionDigest
        )
    }
}

/// The only client component allowed to mutate the personal knowledge vault.
/// Hermes proposes typed steps; this executor validates, journals and applies them locally.
@MainActor
public final class KnowledgeActionExecutor {
    public static let shared = KnowledgeActionExecutor()
    private let store: KnowledgeNoteStore
    private let synchronizer: KnowledgeActionSynchronizing
    private let fileManager = FileManager.default

    private convenience init() {
        self.init(store: .shared, synchronizer: LiveKnowledgeActionSynchronizer.shared)
    }

    init(store: KnowledgeNoteStore, synchronizer: KnowledgeActionSynchronizing) {
        self.store = store
        self.synchronizer = synchronizer
    }

    public func execute(_ action: KnowledgeActionBlock) async -> KnowledgeActionExecutionResult {
        guard action.accountScope == nil || action.accountScope == store.authorizationScope else {
            return .init(state: .stale, noteIds: [], message: "账号已切换，请重新生成操作")
        }
        guard validateMergeTargets(action.steps, requireOriginalTargetVersion: false) else {
            return .init(state: .stale, noteIds: [], message: "合并目标或版本无效，请重新生成操作")
        }
        let expectedFingerprint = store.accountFingerprint
        if let receipt = loadReceipt(action.id), receipt.actionDigest == action.actionDigest,
           [.localApplied, .syncPending, .synced].contains(receipt.status) {
            if receipt.status != .synced {
                return await synchronize(
                    action,
                    capability: validCapability(for: action),
                    noteIds: receipt.resultNoteIds,
                    expectedFingerprint: expectedFingerprint
                )
            }
            return .init(state: .synced, noteIds: receipt.resultNoteIds, message: nil)
        }
        guard let capability = validCapability(for: action) else {
            return .init(state: .stale, noteIds: [], message: "确认凭证已失效，请重新生成操作")
        }
        guard action.steps.filter({ $0.kind == "illustrate_note" }).isEmpty || action.steps.count == 1,
              action.steps.allSatisfy({ $0.kind != "illustrate_note" || store.canApplyIllustrationStep($0) }),
              validateTargets(action.steps) else {
            return .init(state: .stale, noteIds: [], message: "笔记已变化，请重新生成修改方案")
        }

        let backup = backupDirectory(action.id)
        do {
            try prepareBackup(at: backup)
            saveReceipt(.init(
                actionId: action.id, actionDigest: action.actionDigest,
                accountFingerprint: store.accountFingerprint, status: .applying,
                resultNoteIds: [], updatedAt: Date()
            ))
            let ids = try applySteps(action.steps, actionId: action.id)
            saveReceipt(.init(
                actionId: action.id, actionDigest: action.actionDigest,
                accountFingerprint: store.accountFingerprint, status: .localApplied,
                resultNoteIds: ids, updatedAt: Date()
            ))
            try? fileManager.removeItem(at: backup)
            return await synchronize(action, capability: capability, noteIds: ids, expectedFingerprint: expectedFingerprint)
        } catch {
            try? restoreBackup(from: backup)
            store.reload()
            saveReceipt(.init(
                actionId: action.id, actionDigest: action.actionDigest,
                accountFingerprint: store.accountFingerprint, status: .failed,
                resultNoteIds: [], updatedAt: Date()
            ))
            return .init(state: .failed, noteIds: [], message: error.localizedDescription)
        }
    }

    public func discard(_ action: KnowledgeActionBlock) async -> KnowledgeActionExecutionResult {
        guard let capability = action.transientCapability else {
            return .init(state: .stale, noteIds: [], message: "确认凭证已失效")
        }
        do {
            try await synchronizer.discardKnowledgeAction(
                id: action.id, capability: capability, actionDigest: action.actionDigest
            )
            saveReceipt(.init(
                actionId: action.id, actionDigest: action.actionDigest,
                accountFingerprint: store.accountFingerprint, status: .discarded,
                resultNoteIds: [], updatedAt: Date()
            ))
            return .init(state: .discarded, noteIds: [], message: nil)
        } catch {
            return .init(state: .failed, noteIds: [], message: error.localizedDescription)
        }
    }

    private func validateTargets(_ steps: [KnowledgeActionStep]) -> Bool {
        guard validateMergeTargets(steps, requireOriginalTargetVersion: true) else { return false }
        for step in steps {
            if step.kind == "merge_notes" { continue }
            let ids = ([step.targetNoteId].compactMap { $0 } + step.sourceNoteIds)
            for id in ids {
                guard let note = store.anyNote(id: id) else { return false }
                if id == step.targetNoteId, let expected = step.originalContentHash,
                   !expected.isEmpty, store.contentHash(for: note) != expected { return false }
                if let expected = step.sourceContentHashes?[id] ?? nil,
                   !expected.isEmpty, store.contentHash(for: note) != expected { return false }
            }
        }
        return true
    }

    private func validateMergeTargets(
        _ steps: [KnowledgeActionStep],
        requireOriginalTargetVersion: Bool
    ) -> Bool {
        for step in steps where step.kind == "merge_notes" {
            guard let targetID = Self.mergePrimaryNoteID(step: step),
                  let targetHash = step.originalContentHash,
                  Self.isValidContentHash(targetHash),
                  let target = store.note(id: targetID),
                  !requireOriginalTargetVersion || store.contentHash(for: target) == targetHash
            else { return false }

            for sourceID in step.sourceNoteIds {
                guard sourceID != targetID,
                      let sourceHash = step.sourceContentHashes?[sourceID] ?? nil,
                      Self.isValidContentHash(sourceHash)
                else { return false }
                if let source = store.note(id: sourceID) {
                    guard store.contentHash(for: source) == sourceHash else { return false }
                } else {
                    guard !requireOriginalTargetVersion,
                          store.archivedNote(id: sourceID)?.mergedIntoNoteId == targetID
                    else { return false }
                }
            }
        }
        return true
    }

    private func applySteps(_ steps: [KnowledgeActionStep], actionId: String) throws -> [String] {
        var changed: [String] = []
        for (index, step) in steps.enumerated() {
            let stableID = Self.stableNoteID(actionId: actionId, index: index)
            switch step.kind {
            case "create_note", "create_daily_note":
                let presentation = NoteIllustrationPlacement.presented(body: markdownBody(step.markdown ?? ""), tags: step.kind == "create_daily_note" ? step.tags + ["daily"] : step.tags, layout: step.layout)
                let body = presentation.body, tags = presentation.tags
                guard let note = store.createNote(id: stableID, title: step.title ?? inferredTitle(step.markdown), body: body, tags: tags) else { throw ActionError.writeFailed }
                if let enabled = step.automaticIllustrations { store.setAutomaticIllustrations(enabled, id: note.id) }
                changed.append(note.id)
            case "update_note", "rename_note", "set_tags", "set_pinned", "add_wikilink", "remove_wikilink":
                guard let id = step.targetNoteId, let note = store.note(id: id) else { throw ActionError.targetMissing }
                var body = step.markdown.map(markdownBody) ?? note.body
                if step.kind == "add_wikilink", let link = step.linkTitle, !body.contains("[[\(link)]]") {
                    body += "\n\n[[\(link)]]"
                } else if step.kind == "remove_wikilink", let link = step.linkTitle {
                    body = body.replacingOccurrences(of: "[[\(link)]]", with: link)
                }
                let presentation = NoteIllustrationPlacement.presented(body: body,
                    tags: step.kind == "set_tags" ? step.tags : (step.tags.isEmpty ? note.tags : step.tags), layout: step.layout)
                guard store.save(
                    id: id, title: step.title ?? note.title, body: presentation.body,
                    tags: presentation.tags,
                    isPinned: step.pinned ?? note.isPinned
                ) != nil else { throw ActionError.writeFailed }
                if let enabled = step.automaticIllustrations { store.setAutomaticIllustrations(enabled, id: id) }
                changed.append(id)
            case "illustrate_note":
                guard let id = step.targetNoteId else { throw ActionError.targetMissing }
                switch step.illustrationAction {
                case "generate", "retry": break // enqueue only after the confirmed receipt is durable
                case "cancel": store.cancelIllustrations(id: id)
                case "configure": store.setAutomaticIllustrations(step.automaticIllustrations!, id: id)
                case "apply": guard store.applyIllustrations(id: id, synchronize: false) else { throw ActionError.targetChanged }
                case "undo": guard store.undoIllustrations(id: id, synchronize: false) else { throw ActionError.targetChanged }
                default: throw ActionError.unsupported
                }
                changed.append(id)
            case "merge_notes":
                let body = markdownBody(step.markdown ?? "")
                guard let primaryID = Self.mergePrimaryNoteID(step: step),
                      let note = store.note(id: primaryID)
                else { throw ActionError.targetMissing }
                let merged = store.save(
                    id: primaryID,
                    title: step.title ?? note.title,
                    body: body,
                    tags: step.tags.isEmpty ? note.tags : step.tags,
                    isPinned: note.isPinned
                )
                guard let merged else { throw ActionError.writeFailed }
                // Sources stay active until the primary has passed server CAS and
                // read-back verification. A retry can therefore resume safely.
                changed.append(merged.id)
                changed.append(contentsOf: Self.mergeArchiveSourceIDs(step: step, primaryID: merged.id))
            case "archive_note":
                guard let id = step.targetNoteId, store.archive(id: id) != nil else { throw ActionError.writeFailed }
                changed.append(id)
            case "restore_note":
                guard let id = step.targetNoteId, store.restoreArchivedNote(id: id) != nil else { throw ActionError.writeFailed }
                changed.append(id)
            case "move_to_trash":
                guard let id = step.targetNoteId, store.note(id: id) != nil else { throw ActionError.targetMissing }
                store.moveToTrash(id: id)
                changed.append(id)
            default:
                throw ActionError.unsupported
            }
        }
        var seen = Set<String>()
        return changed.filter { seen.insert($0).inserted }
    }

    private func validCapability(for action: KnowledgeActionBlock) -> String? {
        guard action.expiresAt > Int(Date().timeIntervalSince1970),
              let capability = action.transientCapability,
              !capability.isEmpty else { return nil }
        return capability
    }

    private func synchronize(_ action: KnowledgeActionBlock, capability: String?, noteIds: [String], expectedFingerprint: String) async -> KnowledgeActionExecutionResult {
        let credentialGeneration = APIClient.shared.currentCredentialGeneration()
        do {
            var mergeHandledIDs = Set<String>()
            for step in action.steps {
                guard store.accountFingerprint == expectedFingerprint else { throw ActionError.accountChanged }
                if step.kind == "move_to_trash", let id = step.targetNoteId {
                    try await synchronizer.trashKnowledgeNote(id: id)
                } else if step.kind == "archive_note", let id = step.targetNoteId {
                    if let archived = store.archivedNote(id: id) {
                        try await synchronizer.syncKnowledgeNote(id: id, markdown: store.markdown(for: archived), updatedAt: archived.updatedAt, baseHash: step.originalContentHash, credentialGeneration: credentialGeneration)
                    }
                    try await synchronizer.archiveKnowledgeNote(id: id, mergedIntoNoteId: nil, expectedContentHash: step.originalContentHash)
                } else if step.kind == "restore_note", let id = step.targetNoteId {
                    try await synchronizer.restoreKnowledgeNote(id: id)
                } else if step.kind == "merge_notes" {
                    guard let primaryID = Self.mergePrimaryNoteID(step: step) else {
                        throw ActionError.targetMissing
                    }
                    try await synchronizeMerge(
                        step, operationID: action.id, primaryID: primaryID,
                        expectedFingerprint: expectedFingerprint
                    )
                    mergeHandledIDs.insert(primaryID)
                    mergeHandledIDs.formUnion(
                        Self.mergeArchiveSourceIDs(step: step, primaryID: primaryID)
                    )
                }
            }
            for id in noteIds where !mergeHandledIDs.contains(id) {
                guard store.accountFingerprint == expectedFingerprint else { throw ActionError.accountChanged }
                if let note = store.note(id: id) {
                    let baseHash = action.steps.first(where: { $0.targetNoteId == id })?.originalContentHash
                    try await synchronizer.syncKnowledgeNote(id: id, markdown: store.markdown(for: note), updatedAt: note.updatedAt, baseHash: baseHash, credentialGeneration: credentialGeneration)
                }
            }
            for step in action.steps where step.kind == "illustrate_note" && ["generate", "retry"].contains(step.illustrationAction ?? "") {
                guard store.canApplyIllustrationStep(step) else { throw ActionError.targetChanged }
            }
            try await finalizeLedger(
                action, capability: capability, status: "synced", noteIds: noteIds
            )
            for (index, step) in action.steps.enumerated() {
                let creates = ["create_note", "create_daily_note"].contains(step.kind)
                let explicit = step.kind == "illustrate_note" && ["generate", "retry"].contains(step.illustrationAction ?? "")
                if creates || step.kind == "update_note" || explicit {
                    let id = creates ? Self.stableNoteID(actionId: action.id, index: index) : step.targetNoteId ?? ""
                    if store.note(id: id) != nil {
                        synchronizer.enqueueIllustrations(store: store, id: id, step: step, requestID: "action-" + action.id + "-" + String(index))
                    }
                }
            }
            updateReceipt(action, state: .synced, ids: noteIds)
            return .init(state: .synced, noteIds: noteIds, message: nil)
        } catch ActionError.targetChanged where action.steps.contains(where: { $0.kind == "illustrate_note" }) {
            try? await finalizeLedger(action, capability: capability, status: "failed", noteIds: noteIds, errorCode: "note_version_changed")
            updateReceipt(action, state: .stale, ids: noteIds)
            return .init(state: .stale, noteIds: noteIds, message: "正文已变化，配图尚未开始，请重新确认。")
        } catch {
            guard store.accountFingerprint == expectedFingerprint else {
                return .init(state: .stale, noteIds: noteIds, message: "账号已切换，旧账号同步已取消")
            }
            try? await finalizeLedger(
                action, capability: capability, status: "sync_pending",
                noteIds: noteIds, errorCode: "sync_failed"
            )
            updateReceipt(action, state: .syncPending, ids: noteIds)
            return .init(state: .syncPending, noteIds: noteIds, message: "已保存合并进度，可重试完成同步与归档")
        }
    }

    /// Server order is deliberate: verify the primary content first, then archive
    /// each non-primary source. Every check is idempotent so a partial failure can resume.
    private func synchronizeMerge(
        _ step: KnowledgeActionStep,
        operationID: String,
        primaryID: String,
        expectedFingerprint: String
    ) async throws {
        guard let primary = store.note(id: primaryID) else { throw ActionError.targetMissing }
        let primaryMarkdown = store.markdown(for: primary)
        let desiredHash = store.contentHash(for: primary)
        guard let expectedBaseHash = step.originalContentHash,
              Self.isValidContentHash(expectedBaseHash)
        else { throw ActionError.targetChanged }

        let sourceIDs = Self.mergeArchiveSourceIDs(step: step, primaryID: primaryID)
        let sourceVersions = Dictionary(uniqueKeysWithValues: sourceIDs.compactMap { sourceID in
            (step.sourceContentHashes?[sourceID] ?? nil).map { (sourceID, $0) }
        })
        guard sourceVersions.count == sourceIDs.count,
              store.accountFingerprint == expectedFingerprint else { throw ActionError.accountChanged }
        _ = try await synchronizer.mergeKnowledgeNotes(.init(
            operationId: operationID, targetNoteId: primaryID,
            targetBaseHash: expectedBaseHash, sourceVersions: sourceVersions,
            revisedContent: primaryMarkdown
        ))
        guard store.accountFingerprint == expectedFingerprint else { throw ActionError.accountChanged }
        let cloud = try await synchronizer.fetchKnowledgeNotes(includeArchived: true)
        guard cloud.items.contains(where: {
            $0.noteId == primaryID && !$0.archived && $0.contentHash == desiredHash
        }) else { throw ActionError.readBackFailed }
        for sourceID in sourceIDs {
            guard cloud.items.contains(where: {
                $0.noteId == sourceID && $0.archived && $0.mergedIntoNoteId == primaryID
            }) else { throw ActionError.readBackFailed }
            guard store.archive(id: sourceID, mergedInto: primaryID) != nil,
                  store.note(id: sourceID) == nil,
                  store.archivedNote(id: sourceID)?.mergedIntoNoteId == primaryID
            else { throw ActionError.readBackFailed }
        }
        guard store.note(id: primaryID) != nil,
              store.archivedNote(id: primaryID) == nil
        else { throw ActionError.primaryArchived }
    }

    private func finalizeLedger(
        _ action: KnowledgeActionBlock,
        capability: String?,
        status: String,
        noteIds: [String],
        errorCode: String? = nil
    ) async throws {
        if let capability {
            do {
                try await synchronizer.commitKnowledgeAction(
                    id: action.id, capability: capability, actionDigest: action.actionDigest,
                    status: status, resultNoteIds: noteIds, errorCode: errorCode
                )
                return
            } catch {
                // The local transaction is already durable. A token may expire while
                // the app is syncing, so fall through to the JWT-owned ledger resume.
            }
        }
        try await synchronizer.resumeKnowledgeActionSync(
            id: action.id, actionDigest: action.actionDigest,
            status: status, resultNoteIds: noteIds, errorCode: errorCode
        )
    }

    static func mergePrimaryNoteID(step: KnowledgeActionStep) -> String? {
        if let target = step.targetNoteId?.trimmingCharacters(in: .whitespacesAndNewlines),
           !target.isEmpty, target == step.targetNoteId {
            return target
        }
        return nil
    }

    private static func isValidContentHash(_ value: String) -> Bool {
        value.utf8.count == 64 && value.utf8.allSatisfy {
            (48...57).contains($0) || (97...102).contains($0)
        }
    }

    static func mergeArchiveSourceIDs(
        step: KnowledgeActionStep,
        primaryID: String
    ) -> [String] {
        Array(Set(step.sourceNoteIds.filter { !$0.isEmpty && $0 != primaryID })).sorted()
    }

    private static func stableNoteID(actionId: String, index: Int) -> String {
        let digest = SHA256.hash(data: Data("\(actionId):\(index)".utf8)).map { String(format: "%02x", $0) }.joined()
        return "ka-\(digest.prefix(32))"
    }

    private func inferredTitle(_ markdown: String?) -> String {
        markdown?.split(separator: "\n").first.map { String($0).replacingOccurrences(of: #"^#{1,6}\s*"#, with: "", options: .regularExpression) } ?? "无标题"
    }

    private func markdownBody(_ markdown: String) -> String {
        var lines = markdown.components(separatedBy: .newlines)
        if lines.first?.trimmingCharacters(in: .whitespaces) == "---",
           let closing = lines.dropFirst().firstIndex(where: { $0.trimmingCharacters(in: .whitespaces) == "---" }) {
            lines.removeSubrange(0...closing)
        }
        return lines.joined(separator: "\n").trimmingCharacters(in: .newlines)
    }

    private func receiptURL(_ actionId: String) -> URL {
        store.actionDirectory.appendingPathComponent("\(actionId).json")
    }

    private func loadReceipt(_ actionId: String) -> KnowledgeActionReceipt? {
        guard let data = try? Data(contentsOf: receiptURL(actionId)) else { return nil }
        return try? JSONDecoder().decode(KnowledgeActionReceipt.self, from: data)
    }

    private func saveReceipt(_ receipt: KnowledgeActionReceipt) {
        try? fileManager.createDirectory(at: store.actionDirectory, withIntermediateDirectories: true)
        if let data = try? JSONEncoder().encode(receipt) {
            try? data.write(to: receiptURL(receipt.actionId), options: .atomic)
        }
    }

    private func updateReceipt(_ action: KnowledgeActionBlock, state: KnowledgeActionState, ids: [String]) {
        saveReceipt(.init(actionId: action.id, actionDigest: action.actionDigest, accountFingerprint: store.accountFingerprint, status: state, resultNoteIds: ids, updatedAt: Date()))
    }

    private func backupDirectory(_ actionId: String) -> URL {
        store.actionDirectory.appendingPathComponent("rollback-\(actionId)", isDirectory: true)
    }

    private func markdownFiles(at root: URL, excludingActions: Bool = false) -> [URL] {
        guard let enumerator = fileManager.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey], options: []) else { return [] }
        return enumerator.compactMap { $0 as? URL }.filter {
            $0.pathExtension == "md" && (!excludingActions || !$0.path.contains("/.actions/"))
        }
    }

    private func prepareBackup(at backup: URL) throws {
        try? fileManager.removeItem(at: backup)
        try fileManager.createDirectory(at: backup, withIntermediateDirectories: true)
        for source in markdownFiles(at: store.vaultDirectory, excludingActions: true) {
            let relative = source.path.replacingOccurrences(of: store.vaultDirectory.path + "/", with: "")
            let destination = backup.appendingPathComponent(relative)
            try fileManager.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            try fileManager.copyItem(at: source, to: destination)
        }
    }

    private func restoreBackup(from backup: URL) throws {
        for current in markdownFiles(at: store.vaultDirectory, excludingActions: true) { try fileManager.removeItem(at: current) }
        for source in markdownFiles(at: backup) {
            let relative = source.path.replacingOccurrences(of: backup.path + "/", with: "")
            let destination = store.vaultDirectory.appendingPathComponent(relative)
            try fileManager.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            try fileManager.copyItem(at: source, to: destination)
        }
        try? fileManager.removeItem(at: backup)
    }

    private enum ActionError: LocalizedError {
        case targetMissing, targetChanged, writeFailed, unsupported, accountChanged
        case readBackFailed, archiveConflict, primaryArchived
        var errorDescription: String? {
            switch self {
            case .targetMissing: return "目标笔记不存在"
            case .targetChanged: return "来源笔记已变化，请重新生成合并方案"
            case .writeFailed: return "本地笔记写入失败"
            case .unsupported: return "暂不支持该知识操作"
            case .accountChanged: return "账号已切换，旧账号同步已取消"
            case .readBackFailed: return "服务端读回校验失败，可重试继续"
            case .archiveConflict: return "来源笔记已归档到其他主笔记"
            case .primaryArchived: return "主笔记不能被归档"
            }
        }
    }
}

struct NoteIllustrationJob: Codable {
    var request: NoteIllustrationRequest
    var originalBody: String
    var response: NoteIllustrationResponse?
    var message: String
    var applied = false
    var appliedBody: String?
    var cancelled = false
    var automaticDisabled = false
    var insertsAutomatically: Bool?
    var userRequested: Bool?
    var undone: Bool?
}

enum NoteIllustrationPlacement {
    static func presented(body: String, tags: [String], layout: String?) -> (body: String, tags: [String]) {
        guard let layout else { return (body, tags) }
        var updated = tags.filter { !["旅行", "travel", "trip"].contains($0.lowercased()) }
        if layout == "travel" {
            updated.append("旅行")
            let content = travelObject(body) == nil ? json(["stops": [], "journal": body]) ?? body : body
            return (content, updated)
        }
        return (body, updated)
    }
    static func hash(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }
    static func travelPayload(_ body: String) -> String {
        let clean = body.trimmingCharacters(in: .whitespacesAndNewlines)
        guard clean.hasPrefix("```"), clean.hasSuffix("```"), let newline = clean.firstIndex(of: "\n") else { return clean }
        return String(clean[clean.index(after: newline)...].dropLast(3)).trimmingCharacters(in: .whitespacesAndNewlines)
    }
    static func travelObject(_ body: String) -> [String: Any]? {
        let clean = travelPayload(body)
        guard let data = clean.data(using: .utf8), let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any], value["stops"] is [[String: Any]] else { return nil }
        return value
    }
    static func json(_ value: [String: Any]) -> String? {
        guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]) else { return nil }
        return String(data: data, encoding: .utf8)
    }
    static func anchor(in body: String, selection: NSRange) -> String? {
        let text = body as NSString
        guard text.length > 0,
              let expression = try? NSRegularExpression(pattern: #"(?s)(?:^|\n[ \t]*\n)(.+?)(?=\n[ \t]*\n|$)"#) else { return nil }
        let location = min(max(0, selection.location), text.length - 1)
        guard let match = expression.matches(in: body, range: NSRange(location: 0, length: text.length)).first(where: { NSLocationInRange(location, $0.range(at: 1)) }) else { return nil }
        let range = match.range(at: 1)
        let anchor = text.substring(with: range).trimmingCharacters(in: .whitespacesAndNewlines)
        let prefix = text.substring(to: range.location)
        let fences = prefix.components(separatedBy: .newlines).filter { $0.trimmingCharacters(in: .whitespaces).hasPrefix("```") || $0.trimmingCharacters(in: .whitespaces).hasPrefix("~~~") }.count
        guard fences % 2 == 0, !anchor.isEmpty, !anchor.contains("```"), !anchor.contains("~~~"),
              !anchor.hasPrefix("!["), body.components(separatedBy: anchor).count == 2 else { return nil }
        return anchor
    }
    static func inserting(_ assets: [NoteIllustrationAsset], into body: String, travel: Bool) -> String? {
        if travel {
            guard var object = travelObject(body) else { return nil }
            var images = object["illustrations"] as? [[String: String]] ?? []
            for asset in assets where !images.contains(where: { $0["path"] == asset.relativePath }) {
                images.append(["anchor": asset.anchor, "path": asset.relativePath, "alt": asset.alt])
            }
            object["illustrations"] = images
            return json(object)
        }
        var result = body
        for asset in assets {
            if result.contains(asset.relativePath) { continue }
            guard !asset.anchor.isEmpty, result.components(separatedBy: asset.anchor).count == 2,
                  let range = result.range(of: asset.anchor) else { return nil }
            let alt = asset.alt.replacingOccurrences(of: "[", with: "（").replacingOccurrences(of: "]", with: "）").replacingOccurrences(of: "\n", with: " ")
            result.insert(contentsOf: "\n\n![\(alt)](\(asset.relativePath))", at: range.upperBound)
        }
        return result
    }
}

extension KnowledgeNoteStore {
    private var illustrationLedger: URL { vaultDirectory.appendingPathComponent(".illustrations.json") }
    private func persistIllustrationJobs() {
        do {
            try fileManager.createDirectory(at: vaultDirectory, withIntermediateDirectories: true)
            try JSONEncoder().encode(illustrationJobs).write(to: illustrationLedger, options: [.atomic, .completeFileProtection])
        } catch { lastError = "配图进度保存失败，请检查存储空间。" }
    }
    func loadIllustrationJobs() {
        if let data = try? Data(contentsOf: illustrationLedger), let values = try? JSONDecoder().decode([String: NoteIllustrationJob].self, from: data) { illustrationJobs = values }
        for id in illustrationJobs.keys where note(id: id) != nil { resumeIllustrations(id: id) }
    }
    func illustrationIsRunning(_ id: String) -> Bool { illustrationTasks[id] != nil }
    func automaticIllustrationsEnabled(_ id: String) -> Bool { !(illustrationJobs[id]?.automaticDisabled ?? false) }
    func setAutomaticIllustrations(_ enabled: Bool, id: String) {
        guard let note = note(id: id) else { return }
        if illustrationJobs[id] == nil {
            var preference = makeIllustrationJob(note, mode: "auto", anchor: "", brief: "")
            preference.cancelled = true
            preference.message = ""
            illustrationJobs[id] = preference
        }
        illustrationJobs[id]?.automaticDisabled = !enabled
        if !enabled && illustrationJobs[id]?.request.mode == "auto" && illustrationTasks[id] != nil { cancelIllustrations(id: id) }
        persistIllustrationJobs()
    }
    private func makeIllustrationJob(_ note: KnowledgeNote, mode: String, anchor: String, brief: String) -> NoteIllustrationJob {
        let travel = note.tags.contains { ["旅行", "travel", "trip"].contains($0.lowercased()) }
        let content = travel ? NoteIllustrationPlacement.travelObject(note.body).flatMap(NoteIllustrationPlacement.json) ?? note.body : note.body
        let hash = NoteIllustrationPlacement.hash(content)
        return NoteIllustrationJob(request: .init(noteId: note.id, requestId: mode == "auto" ? "auto-" + hash : UUID().uuidString,
            title: note.title, content: content, sourceHash: hash, mode: mode, anchor: anchor, brief: brief, travel: travel),
            originalBody: note.body, message: "正在挑选配图位置")
    }
    func startIllustrations(id: String, mode: String = "auto", anchor: String = "", brief: String = "", retry: Bool = false, insert: Bool? = nil, requestID: String? = nil, explicit: Bool = false) {
        guard let note = note(id: id), !note.body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, illustrationTasks[id] == nil else { return }
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("-knowledgeHomePreview") { return }
        #endif
        if mode == "auto" && !explicit && !automaticIllustrationsEnabled(id) { return }
        if let requestID, illustrationJobs[id]?.request.requestId == requestID { resumeIllustrations(id: id); return }
        var job = makeIllustrationJob(note, mode: mode, anchor: anchor, brief: brief)
        if job.request.travel && NoteIllustrationPlacement.travelObject(note.body) == nil { return }
        if note.body.count > 48000 {
            job.message = "笔记超过配图长度上限，请先拆分章节。"
            illustrationJobs[id] = job; persistIllustrationJobs(); return
        }
        if retry, let previous = illustrationJobs[id] {
            job = previous
            job.request.retryRunId = previous.response?.runId
            job.request.requestId = UUID().uuidString
            job.response = nil
            job.applied = false
            job.cancelled = false
            job.originalBody = note.body
            job.message = "正在重试配图"
        } else if mode == "auto", !explicit, let previous = illustrationJobs[id],
                  (previous.response != nil && previous.request.sourceHash == job.request.sourceHash) || previous.appliedBody == note.body || previous.applied && previous.originalBody == note.body { return }
        if let requestID { job.request.requestId = requestID }
        if !retry || insert != nil { job.insertsAutomatically = insert }
        job.userRequested = explicit
        job.automaticDisabled = illustrationJobs[id]?.automaticDisabled ?? false
        illustrationJobs[id] = job
        persistIllustrationJobs()
        resumeIllustrations(id: id)
    }
    func resumeIllustrations(id: String) {
        guard illustrationTasks[id] == nil, let job = illustrationJobs[id], !job.applied, !job.cancelled,
              job.response?.status != "cancelled" else { return }
        if job.request.mode == "auto" && job.automaticDisabled && job.userRequested != true { return }
        let account = accountFingerprint
        let generation = APIClient.shared.currentCredentialGeneration()
        illustrationTasks[id] = Task { @MainActor in
            defer { if self.accountFingerprint == account && APIClient.shared.currentCredentialGeneration() == generation && self.illustrationJobs[id]?.request.requestId == job.request.requestId { self.illustrationTasks[id] = nil; self.objectWillChange.send() } }
            do {
                var response = job.response
                if response == nil { response = try await APIClient.shared.generateNoteIllustrations(job.request, generation: generation) }
                while let current = response {
                    try Task.checkCancellation()
                    guard self.accountFingerprint == account, APIClient.shared.currentCredentialGeneration() == generation, self.note(id: id) != nil else { return }
                    self.illustrationJobs[id]?.response = current
                    self.illustrationJobs[id]?.message = current.message
                    self.persistIllustrationJobs()
                    if ["completed", "failed", "cancelled"].contains(current.status) { break }
                    try await Task.sleep(nanoseconds: 2_000_000_000)
                    response = try await APIClient.shared.noteIllustrations(runId: current.runId, generation: generation)
                }
                guard let result = response, self.accountFingerprint == account, self.note(id: id) != nil else { return }
                for asset in result.assets {
                    _ = try await self.illustrationImage(asset, account: account)
                }
                try Task.checkCancellation()
                guard self.accountFingerprint == account, APIClient.shared.currentCredentialGeneration() == generation else { return }
                if result.status == "completed" {
                    self.illustrationJobs[id]?.message = result.assets.isEmpty && result.failedIndices.isEmpty ? "当前内容无需配图" : result.failedIndices.isEmpty ? "插图已生成，待插入" : "部分插图未完成，可重试"
                    if (job.insertsAutomatically ?? (job.request.mode == "auto")) && !result.assets.isEmpty { _ = self.applyIllustrations(id: id) }
                } else {
                    self.illustrationJobs[id]?.message = result.status == "cancelled" ? "已停止配图" : "配图未完成，请重试"
                }
                self.persistIllustrationJobs()
            } catch is CancellationError { } catch {
                guard self.accountFingerprint == account else { return }
                self.illustrationJobs[id]?.message = "配图连接未完成，正文已保存。可重试继续。"
                self.persistIllustrationJobs()
            }
        }
    }
    func cancelIllustrations(id: String) {
        illustrationTasks[id]?.cancel(); illustrationTasks[id] = nil
        if let runId = illustrationJobs[id]?.response?.runId {
            let generation = APIClient.shared.currentCredentialGeneration()
            Task { _ = try? await APIClient.shared.noteIllustrations(runId: runId, generation: generation, cancel: true) }
        }
        illustrationJobs[id]?.cancelled = true
        illustrationJobs[id]?.response?.status = "cancelled"
        illustrationJobs[id]?.message = "已停止配图"
        persistIllustrationJobs()
    }
    @discardableResult
    func applyIllustrations(id: String, synchronize: Bool = true) -> Bool {
        guard var job = illustrationJobs[id], let note = note(id: id), let response = job.response,
              !job.applied, !job.cancelled, response.status == "completed", !response.assets.isEmpty else { return false }
        guard note.body == job.originalBody, activeNoteDrafts[id].map({ $0 == note.body }) ?? true,
              let body = NoteIllustrationPlacement.inserting(response.assets, into: note.body, travel: job.request.travel) else {
            illustrationJobs[id]?.message = "正文已变化，插图已保留。请在配图面板重新选择位置。"
            persistIllustrationJobs(); return false
        }
        guard let saved = save(id: id, title: note.title, body: body, tags: note.tags, isPinned: note.isPinned) else { return false }
        job.applied = true
        job.appliedBody = body
        job.message = "已添加 \(response.assets.count) 张插图" + (response.failedIndices.isEmpty ? "" : "，其余可重试")
        illustrationJobs[id] = job
        persistIllustrationJobs()
        if synchronize { syncIllustratedNote(saved) }
        return true
    }
    func relocateIllustrations(id: String, anchor: String) -> Bool {
        guard let note = note(id: id), var job = illustrationJobs[id], !job.applied else { return false }
        job.originalBody = note.body
        let relocated: [NoteIllustrationAsset] = (job.response?.assets ?? []).map { asset in
            var value = asset
            value.anchor = anchor
            return value
        }
        job.response?.assets = relocated
        illustrationJobs[id] = job
        return applyIllustrations(id: id)
    }
    @discardableResult
    func undoIllustrations(id: String, synchronize: Bool = true) -> Bool {
        guard let job = illustrationJobs[id], job.applied, job.undone != true, let note = note(id: id), let assets = job.response?.assets else { return false }
        var body = note.body
        if job.request.travel, var object = NoteIllustrationPlacement.travelObject(body) {
            object["illustrations"] = (object["illustrations"] as? [[String: String]] ?? []).filter { item in !assets.contains { $0.relativePath == item["path"] } }
            body = NoteIllustrationPlacement.json(object) ?? body
        } else {
            for asset in assets {
                let pattern = #"\n*\!\[[^\]]*\]\("# + NSRegularExpression.escapedPattern(for: asset.relativePath) + #"\)"#
                body = body.replacingOccurrences(of: pattern, with: "", options: .regularExpression)
            }
        }
        if let saved = save(id: id, title: note.title, body: body, tags: note.tags, isPinned: note.isPinned) {
            illustrationJobs[id]?.message = "已撤销本批配图"
            illustrationJobs[id]?.undone = true
            persistIllustrationJobs()
            if synchronize { syncIllustratedNote(saved) }
            return true
        }
        return false
    }
    private func syncIllustratedNote(_ note: KnowledgeNote) {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("-noteIllustrationChatPreview") { return }
        #endif
        let account = accountFingerprint, generation = APIClient.shared.currentCredentialGeneration(), markdown = markdown(for: note)
        Task { @MainActor in
            do { _ = try await APIClient.shared.syncKnowledgeNote(id: note.id, markdown: markdown, updatedAt: note.updatedAt, credentialGeneration: generation) }
            catch { if accountFingerprint == account { illustrationJobs[note.id]?.message = "插图已存本机，云端同步待重试"; persistIllustrationJobs() } }
        }
    }
    func canApplyIllustrationStep(_ step: KnowledgeActionStep) -> Bool {
        guard let id = step.targetNoteId, let note = note(id: id), let version = step.originalContentHash,
              contentHash(for: note) == version,
              activeNoteDrafts[id].map({ $0 == note.body }) ?? true else { return false }
        switch step.illustrationAction {
        case "configure": return step.automaticIllustrations != nil
        case "generate":
            guard !illustrationIsRunning(id), !note.body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, note.body.count <= 48000 else { return false }
            if note.tags.contains(where: { ["旅行", "travel", "trip"].contains($0.lowercased()) }), NoteIllustrationPlacement.travelObject(note.body) == nil { return false }
            let anchor = step.illustrationAnchor ?? ""
            if anchor.isEmpty { return true }
            guard !(step.illustrationBrief ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
            if let travel = NoteIllustrationPlacement.travelObject(note.body) {
                let stops = travel["stops"] as? [[String: Any]] ?? []
                return anchor == "overview" || stops.indices.contains(where: { "stop:\($0)" == anchor })
            }
            let position = (note.body as NSString).range(of: anchor)
            return position.location != NSNotFound && NoteIllustrationPlacement.anchor(in: note.body, selection: position) == anchor
        case "retry", "cancel", "apply", "undo":
            guard let job = illustrationJobs[id], let run = step.illustrationRunId,
                  job.response?.runId == run else { return false }
            if step.illustrationAction == "apply" { return !job.applied && !job.cancelled && job.response?.status == "completed" && job.originalBody == note.body && !(job.response?.assets.isEmpty ?? true) }
            if step.illustrationAction == "undo" { return job.applied && job.undone != true }
            if step.illustrationAction == "retry" { return !illustrationIsRunning(id) && (note.body == job.originalBody || note.body == job.appliedBody) }
            return true
        default: return false
        }
    }
    func illustrationImage(_ asset: NoteIllustrationAsset, account: String) async throws -> Data {
        let path = vaultDirectory.appendingPathComponent(asset.relativePath)
        if let data = try? Data(contentsOf: path), NoteIllustrationPlacement.hashData(data) == asset.sha256 { return data }
        let generation = APIClient.shared.currentCredentialGeneration()
        let data = try await APIClient.shared.downloadAuthenticated(path: asset.downloadPath, expectedHash: asset.sha256)
        guard generation == APIClient.shared.currentCredentialGeneration(), accountFingerprint == account else { throw CancellationError() }
        try fileManager.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: path, options: [.atomic, .completeFileProtection])
        return data
    }
}

extension NoteIllustrationPlacement {
    static func hashData(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    static func asset(from filename: String) -> NoteIllustrationAsset? {
        guard let match = filename.wholeMatch(of: /ai-([a-f0-9]{32})-([0-2])-([a-f0-9]{64})\.jpg/) else { return nil }
        return .init(runId: String(match.1), index: Int(match.2)!, anchor: "", alt: "AI 插图", sha256: String(match.3), provider: "unknown", model: "unknown")
    }
}
