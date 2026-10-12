import AppIntents
import CryptoKit
import Foundation

/// User-spoken drafts are scoped to an owned note, and removed only after its cloud receipt.
@MainActor enum TravelExpenseDraftQueue {
    struct Draft: Codable { let id: String; let text: String; let date: String }
    static func bind(noteID: String) {
        let owner = KnowledgeNoteStore.shared.accountFingerprint
        guard owner != "unconfigured", !noteID.isEmpty else { return }
        UserDefaults.standard.set(["owner": owner, "note": noteID], forKey: "travel.expense.active-note.v1")
    }
    static func activeNote() throws -> String {
        let owner = KnowledgeNoteStore.shared.accountFingerprint
        guard owner != "unconfigured", let context = UserDefaults.standard.dictionary(forKey: "travel.expense.active-note.v1"),
              context["owner"] as? String == owner, let noteID = context["note"] as? String else {
            throw APIError.network("请先在 Quantum 打开要记录的旅行笔记")
        }
        return noteID
    }
    private static func path(_ noteID: String) throws -> URL {
        guard KnowledgeNoteStore.shared.accountFingerprint != "unconfigured", let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { throw APIError.invalidURL }
        let directory = folder.appendingPathComponent("TravelExpenseDrafts", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let identity = KnowledgeNoteStore.shared.accountFingerprint + "\u{0}" + noteID
        let hash = SHA256.hash(data: Data(identity.utf8)).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(hash + ".json")
    }
    static func read(noteID: String) throws -> [Draft] {
        let file = try path(noteID)
        guard FileManager.default.fileExists(atPath: file.path) else { return [] }
        let bytes = try Data(contentsOf: file)
        guard bytes.count <= 3 * 1024 * 1024 else { throw APIError.network("快捷指令草稿过大") }
        return try JSONDecoder().decode([Draft].self, from: bytes)
    }
    static func append(text: String, noteID: String) throws {
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, value.count <= 4000 else { throw APIError.network("请说一句不超过4000字的花费") }
        var drafts = try read(noteID: noteID)
        guard drafts.count < 500 else { throw APIError.network("请先打开旅行账本核对待同步记录") }
        drafts.append(.init(id: UUID().uuidString, text: value, date: ISO8601DateFormatter().string(from: Date())))
        try JSONEncoder().encode(drafts).write(to: path(noteID), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }
    static func acknowledge(noteID: String, document: [String: Any]) throws {
        let client = document["client_state"] as? [String: Any] ?? [:]
        let profile = client["profile"] as? [String: Any] ?? [:]
        let ledger = profile["budgetLedger"] as? [String: Any] ?? [:]
        let entries = ledger["entries"] as? [[String: Any]] ?? []
        let sources = entries.compactMap { $0["sourceId"] as? String }
        let remaining = try read(noteID: noteID).filter { draft in
            !sources.contains { $0 == "siri-" + draft.id || $0.hasPrefix("siri-" + draft.id + "-") }
        }
        try JSONEncoder().encode(remaining).write(to: path(noteID), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }
}

struct RecordTravelExpenseIntent: AppIntent {
    static var title: LocalizedStringResource = "记录旅行花费"
    static var description = IntentDescription("把一句花费保留为当前旅行笔记的待核对草稿，打开旅行账本后确认金额、币种和分账。")
    static var openAppWhenRun = true
    @Parameter(title: "花费内容") var expenseText: String
    @MainActor func perform() async throws -> some IntentResult & ProvidesDialog {
        let owner = KnowledgeNoteStore.shared.accountFingerprint
        let generation = APIClient.shared.currentCredentialGeneration()
        let noteID = try TravelExpenseDraftQueue.activeNote()
        _ = try await APIClient.shared.readTravelNotebook(id: noteID)
        guard owner == KnowledgeNoteStore.shared.accountFingerprint, generation == APIClient.shared.currentCredentialGeneration(), try TravelExpenseDraftQueue.activeNote() == noteID else { throw APIError.network("账号或笔记已切换，请重新记录") }
        try TravelExpenseDraftQueue.append(text: expenseText, noteID: noteID)
        return .result(dialog: "已保留这句花费。请在旅行账本核对金额、币种和分账后保存。")
    }
}

struct TravelExpenseShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: RecordTravelExpenseIntent(), phrases: ["用\(.applicationName)记一笔旅行花费"], shortTitle: "旅行记账", systemImageName: "wallet.pass")
    }
}
