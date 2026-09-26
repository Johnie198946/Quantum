import CryptoKit
import Security
import XCTest

final class SignedKeychainAcceptanceTests: XCTestCase {
    func testSecureCredentialRoundTripInSignedHost() throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "com.ailab.acceptance.\(UUID())",
            kSecAttrAccount as String: "noncredential-probe",
            kSecAttrAccessGroup as String: "AALA948YY5.com.ailab.AIPlatformApp"
        ]
        defer { SecItemDelete(query as CFDictionary) }
        let expected = Data("keychain-acceptance-not-a-token".utf8)
        var add = query
        add[kSecValueData as String] = expected
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        XCTAssertEqual(SecItemAdd(add as CFDictionary, nil), errSecSuccess,
                       "Real login acceptance requires a signed test host with Keychain entitlements")
        var read = query
        read[kSecReturnData as String] = true
        var value: AnyObject?
        XCTAssertEqual(SecItemCopyMatching(read as CFDictionary, &value), errSecSuccess)
        XCTAssertEqual(value as? Data, expected)
        XCTAssertEqual(SecItemDelete(query as CFDictionary), errSecSuccess)
        XCTAssertEqual(SecItemCopyMatching(read as CFDictionary, &value), errSecItemNotFound)
    }
}
@testable import AIPlatformApp

@MainActor
final class KnowledgeNoteStoreTests: XCTestCase {
    func testSyncStatusRequiresServerConfirmationOfTheCurrentContent() {
        let synced = KnowledgeNoteSyncStatusDTO(noteId: "n", contentHash: "current", syncStatus: "synced")
        XCTAssertEqual(KnowledgeNoteStatusPolicy.message(for: synced, expectedContentHash: "current"), "已同步")
        XCTAssertEqual(KnowledgeNoteStatusPolicy.message(for: synced, expectedContentHash: "newer"), "已保存到本地，云端同步待确认")
        let pending = KnowledgeNoteSyncStatusDTO(noteId: "n", contentHash: "current", syncStatus: "pending")
        XCTAssertEqual(KnowledgeNoteStatusPolicy.message(for: pending, expectedContentHash: "current"), "已保存到本地，云端同步待确认")
    }

    func testUnchangedSavePreservesContentHashTimestampAndFile() throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "unchanged-\(UUID())", userId: "test")
        defer { try? FileManager.default.removeItem(at: store.vaultDirectory) }
        let original = try XCTUnwrap(store.createNote(title: "Keep order", body: "Read only", tags: ["z", "a"]))
        let bytes = try Data(contentsOf: original.fileURL)
        let modification = try original.fileURL.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate
        let saved = try XCTUnwrap(store.save(id: original.id, title: " Keep order ", body: original.body,
                                             tags: original.tags.reversed(), isPinned: original.isPinned))
        XCTAssertEqual(saved.updatedAt, original.updatedAt)
        XCTAssertEqual(store.contentHash(for: saved), store.contentHash(for: original))
        XCTAssertEqual(try Data(contentsOf: saved.fileURL), bytes)
        XCTAssertEqual(try saved.fileURL.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate, modification)
    }

    func testChineseTagsRoundTripThroughSaveAndReload() throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "tags-\(UUID())", userId: "test")
        defer { try? FileManager.default.removeItem(at: store.vaultDirectory) }
        let tags = KnowledgeNoteStore.parseTags(" #学习，灵感、阅读,学习, ,# ")
        XCTAssertEqual(Set(tags), Set(["学习", "灵感", "阅读"]))
        XCTAssertEqual(KnowledgeNoteStore.parseTags("学习,灵感,阅读"), tags)
        let original = try XCTUnwrap(store.createNote(title: "Tags"))
        _ = try XCTUnwrap(store.save(id: original.id, title: original.title, body: "正文", tags: tags, isPinned: false))
        store.reload()
        XCTAssertEqual(Set(try XCTUnwrap(store.note(id: original.id)).tags), Set(tags))
        XCTAssertEqual(store.search("", tags: ["学习", "灵感"]).map(\.id), [original.id])
    }

    func testTrashSurvivesReloadAndCloudRefreshThenRestoresWithoutOverwritingSameTitle() throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "trash-\(UUID())", userId: "test")
        defer { try? FileManager.default.removeItem(at: store.vaultDirectory) }
        let original = try XCTUnwrap(store.createNote(title: "Same title", body: "Keep this", tags: ["学习"]))
        XCTAssertTrue(store.moveToTrash(id: original.id))
        store.reload()
        XCTAssertNil(store.note(id: original.id))
        XCTAssertEqual(store.trashedNotes.map(\.id), [original.id])
        XCTAssertTrue(store.search("Keep this").isEmpty)
        try store.restoreFromCloudSnapshot(CloudKnowledgeNotesResponse(items: [CloudKnowledgeNoteDTO(
            noteId: original.id, markdown: store.markdown(for: original), contentHash: store.contentHash(for: original),
            updatedAt: ISO8601DateFormatter().string(from: Date().addingTimeInterval(60)),
            archived: false, mergedIntoNoteId: nil
        )], count: 1, compileStatus: "pending"))
        XCTAssertNil(store.note(id: original.id), "Refreshing must not resurrect a local deletion")
        let other = try XCTUnwrap(store.createNote(title: original.title, body: "Another note"))
        let restored = try XCTUnwrap(store.restoreTrashedNote(id: original.id))
        XCTAssertEqual(restored.body, original.body)
        XCTAssertEqual(restored.updatedAt.timeIntervalSince1970, original.updatedAt.timeIntervalSince1970, accuracy: 0.001)
        XCTAssertNotEqual(restored.fileURL, other.fileURL)
        XCTAssertEqual(store.note(id: other.id)?.body, "Another note")
        XCTAssertTrue(store.trashedNotes.isEmpty)
        store.reload()
        XCTAssertEqual(store.search("Keep this").map(\.id), [original.id])
    }

    func testTrashIsIsolatedAcrossAccounts() throws {
        let store = KnowledgeNoteStore()
        let tenant = "trash-isolation-\(UUID())"
        store.activate(tenantKey: tenant, userId: "a")
        let directoryA = store.vaultDirectory
        let note = try XCTUnwrap(store.createNote(title: "Private"))
        XCTAssertTrue(store.moveToTrash(id: note.id))
        store.activate(tenantKey: tenant, userId: "b")
        let directoryB = store.vaultDirectory
        defer {
            try? FileManager.default.removeItem(at: directoryB)
            try? FileManager.default.removeItem(at: directoryA)
        }
        XCTAssertTrue(store.trashedNotes.isEmpty)
        XCTAssertNil(store.restoreTrashedNote(id: note.id))
        store.activate(tenantKey: tenant, userId: "a")
        XCTAssertEqual(store.trashedNotes.map(\.id), [note.id])
        store.deactivate()
        XCTAssertTrue(store.trashedNotes.isEmpty)
    }

    func testFailedSaveKeepsInMemoryContentAndReportsFailure() throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "failed-save-\(UUID())", userId: "test")
        defer { try? FileManager.default.removeItem(at: store.vaultDirectory) }
        let original = try XCTUnwrap(store.createNote(title: "Save failure", body: "Original"))
        try FileManager.default.removeItem(at: original.fileURL)
        try FileManager.default.createDirectory(at: original.fileURL, withIntermediateDirectories: true)
        XCTAssertNil(store.save(id: original.id, title: original.title, body: "New", tags: [], isPinned: false))
        XCTAssertEqual(store.note(id: original.id)?.body, "Original")
        XCTAssertTrue(store.lastError?.hasPrefix("自动保存失败") == true)
    }

    func testArchiveExcludesNoteFromActiveSearchAndCanRestore() throws {
        let store = KnowledgeNoteStore.shared
        store.activate(tenantKey: "archive-tenant-\(UUID())", userId: "archive-user")
        let note = try XCTUnwrap(store.createNote(title: "待合并", body: "超聚变内容"))
        let archived = try XCTUnwrap(store.archive(id: note.id, mergedInto: "merged-id"))
        XCTAssertNil(store.note(id: note.id))
        XCTAssertTrue(store.search("超聚变").isEmpty)
        XCTAssertEqual(store.archivedNotes.first(where: { $0.id == note.id })?.id, archived.id)
        XCTAssertNotNil(store.restoreArchivedNote(id: note.id))
        XCTAssertEqual(store.note(id: note.id)?.body, "超聚变内容")
        store.moveToTrash(id: note.id)
    }

    func testNotesAreIsolatedByTenantAndUser() throws {
        let store = KnowledgeNoteStore.shared
        let tenantA = "tenant-a-\(UUID().uuidString)"
        let tenantB = "tenant-b-\(UUID().uuidString)"
        let user = "same-user"
        store.activate(tenantKey: tenantA, userId: user)
        let note = try XCTUnwrap(store.createNote(title: "租户隔离", body: "只属于 A"))
        store.activate(tenantKey: tenantB, userId: user)
        XCTAssertNil(store.note(id: note.id))
        store.activate(tenantKey: tenantA, userId: user)
        XCTAssertEqual(store.note(id: note.id)?.body, "只属于 A")
        store.moveToTrash(id: note.id)
    }

    func testCreateNoteWritesObsidianCompatibleMarkdown() throws {
        let store = KnowledgeNoteStore.shared
        let title = "双链测试-\(UUID().uuidString.prefix(8))"
        let note = try XCTUnwrap(store.createNote(
            title: title,
            body: "连接 [[欢迎使用知识笔记|开始]] #测试/双链",
            tags: ["spec"]
        ))
        defer { store.moveToTrash(id: note.id) }

        XCTAssertEqual(note.outgoingLinks, ["欢迎使用知识笔记"])
        XCTAssertTrue(note.tags.contains("测试/双链"))

        let markdown = try String(contentsOf: note.fileURL, encoding: .utf8)
        XCTAssertTrue(markdown.hasPrefix("---\n"))
        XCTAssertTrue(markdown.contains("title: \"\(title)\""))
        XCTAssertTrue(markdown.contains("tags:\n"))
        XCTAssertTrue(markdown.contains("[[欢迎使用知识笔记|开始]]"))
    }

    func testMultiTagSearchUsesLogicalAnd() throws {
        let store = KnowledgeNoteStore.shared
        store.activate(tenantKey: "tag-tenant-\(UUID())", userId: "tag-user")
        let both = try XCTUnwrap(store.createNote(title: "双标签", tags: ["旅行", "日本"]))
        let one = try XCTUnwrap(store.createNote(title: "单标签", tags: ["旅行"]))
        defer { store.moveToTrash(id: both.id); store.moveToTrash(id: one.id) }

        XCTAssertEqual(store.search("", tags: ["旅行", "日本"]).map(\.id), [both.id])
        XCTAssertEqual(Set(store.search("", tags: ["旅行"]).map(\.id)), Set([both.id, one.id]))
    }

    func testRenamingNoteUpdatesIncomingWikiLinks() throws {
        let store = KnowledgeNoteStore.shared
        let suffix = UUID().uuidString.prefix(8)
        let originalTitle = "原始页面-\(suffix)"
        let renamedTitle = "重命名页面-\(suffix)"
        let source = try XCTUnwrap(store.createNote(title: originalTitle))
        let linker = try XCTUnwrap(store.createNote(
            title: "引用页面-\(suffix)",
            body: "参见 [[\(originalTitle)|详情]]"
        ))
        defer {
            store.moveToTrash(id: source.id)
            store.moveToTrash(id: linker.id)
        }

        _ = try XCTUnwrap(store.save(
            id: source.id,
            title: renamedTitle,
            body: source.body,
            tags: source.tags,
            isPinned: source.isPinned
        ))

        let updatedLinker = try XCTUnwrap(store.note(id: linker.id))
        XCTAssertTrue(updatedLinker.body.contains("[[\(renamedTitle)|详情]]"))
        XCTAssertEqual(store.backlinks(to: try XCTUnwrap(store.note(id: source.id))).map(\.id), [linker.id])
    }

    func testReloadAndIndexedSearchScaleToOneThousandNotes() throws {
        let store = KnowledgeNoteStore.shared
        let tenantKey = "scale-tenant-\(UUID())"
        let userId = "scale-user"
        store.activate(tenantKey: tenantKey, userId: userId)
        let fm = FileManager.default
        let root = store.vaultDirectory
        for index in 0..<1_000 {
            let url = root.appendingPathComponent("scale-\(index).md")
            try "---\ntitle: Scale \(index)\ntags:\n  - scale\n---\n\n内容 \(index) [[Scale 0]]".write(to: url, atomically: true, encoding: .utf8)
        }
        defer {
            try? fm.removeItem(at: root)
            store.reload()
        }
        measure {
            store.activate(tenantKey: tenantKey, userId: userId)
            store.reload()
            _ = store.search("内容 999")
            if let first = store.notes.first { _ = store.backlinks(to: first) }
        }
        // The host app may publish an account lifecycle notification while the
        // performance block runs. Reassert the test account before verification.
        store.activate(tenantKey: tenantKey, userId: userId)
        store.reload()
        XCTAssertEqual(store.notes.count, 1_000)
    }

    func testKnowledgeMergePrimaryRequiresExplicitTarget() {
        let explicit = KnowledgeActionStep(
            kind: "merge_notes",
            targetNoteId: "note-z",
            sourceNoteIds: ["note-a", "note-z"],
            markdown: "# merged"
        )
        XCTAssertEqual(KnowledgeActionExecutor.mergePrimaryNoteID(step: explicit), "note-z")
        XCTAssertEqual(
            KnowledgeActionExecutor.mergeArchiveSourceIDs(step: explicit, primaryID: "note-z"),
            ["note-a"]
        )
        XCTAssertNil(KnowledgeActionExecutor.mergePrimaryNoteID(step: .init(
            kind: "merge_notes", sourceNoteIds: ["note-a"], markdown: "# merged"
        )))
        XCTAssertNil(KnowledgeActionExecutor.mergePrimaryNoteID(step: .init(
            kind: "merge_notes", targetNoteId: " note-z ", markdown: "# merged"
        )))
    }

    func testLegacyDraftMergeNeverArchivesUpdatedPrimaryOrDuplicates() {
        let candidates = [
            NoteMergeCandidate(id: "source-a", title: "来源 A", snippet: ""),
            NoteMergeCandidate(id: "target", title: "目标", snippet: ""),
            NoteMergeCandidate(id: "source-a", title: "来源 A 重复", snippet: ""),
            NoteMergeCandidate(id: "source-b", title: "来源 B", snippet: "")
        ]

        XCTAssertEqual(
            TenantSessionCoordinator.mergeArchiveCandidateIDs(candidates, primaryNoteID: "target"),
            ["source-a", "source-b"]
        )

        let draft = NoteDraftBlock(
            id: "draft", title: "九州旅行纲要", markdown: "# 九州旅行纲要\n\n完整正文",
            tags: ["九州"], sourceSessionId: nil, sourceMessageIds: [],
            mergeCandidates: candidates, mergedTitle: "九州旅行纲要",
            mergedMarkdown: "（以上为合并后的完整笔记）", mergedTags: ["九州", "交通"],
            operation: "update", targetNoteId: "target", targetNoteTitle: "九州旅行纲要",
            targetContentHash: String(repeating: "a", count: 64)
        )
        let resolved = TenantSessionCoordinator.resolveLegacyNoteDraft(draft, shouldMerge: true)
        XCTAssertEqual(resolved.markdown, draft.markdown)
        XCTAssertEqual(resolved.tags, ["九州", "交通"])
    }

    func testExplicitTargetOnlyMergeUpdatesInPlaceAndPreservesMetadata() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let target = try XCTUnwrap(store.createNote(
            id: "target-only", title: "原标题", body: "旧正文", tags: ["原标签"]
        ))
        store.togglePin(id: target.id)
        let before = try XCTUnwrap(store.note(id: target.id))
        let action = mergeAction(step: .init(
            kind: "merge_notes", targetNoteId: target.id, title: "新标题",
            markdown: "# 新标题\n\n合并草稿", originalContentHash: store.contentHash(for: before)
        ))

        let result = await executor.execute(action)
        let merged = try XCTUnwrap(store.note(id: target.id))
        XCTAssertTrue([KnowledgeActionState.synced, .syncPending].contains(result.state))
        XCTAssertEqual(result.noteIds, [target.id])
        XCTAssertEqual(merged.body, "# 新标题\n\n合并草稿")
        XCTAssertEqual(merged.createdAt, before.createdAt)
        XCTAssertEqual(merged.tags, before.tags)
        XCTAssertEqual(merged.isPinned, before.isPinned)
        XCTAssertEqual(Set(store.notes.map(\.id) + store.archivedNotes.map(\.id)), [target.id])
        XCTAssertFalse(store.notes.contains { $0.id.hasPrefix("ka-") })
    }

    func testExplicitTargetAndSourceMergeNeverCreatesReplacementID() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let target = try XCTUnwrap(store.createNote(id: "merge-target", title: "目标", body: "旧稿"))
        let source = try XCTUnwrap(store.createNote(id: "merge-source", title: "来源", body: "材料"))
        let originalIDs = Set(store.notes.map(\.id))
        let action = mergeAction(step: .init(
            kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id],
            markdown: "合并完成", originalContentHash: store.contentHash(for: target),
            sourceContentHashes: [source.id: store.contentHash(for: source)]
        ))

        let result = await executor.execute(action)
        XCTAssertTrue([KnowledgeActionState.synced, .syncPending].contains(result.state))
        XCTAssertEqual(Set(result.noteIds), originalIDs)
        XCTAssertEqual(store.note(id: target.id)?.body, "合并完成")
        XCTAssertEqual(Set(store.notes.map(\.id) + store.archivedNotes.map(\.id)), originalIDs)
        XCTAssertFalse((store.notes + store.archivedNotes).contains { $0.id.hasPrefix("ka-") })
    }

    func testExecutorUsesAtomicMergeContractWithExactVersions() async throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "merge-contract-\(UUID())", userId: "merge-user")
        defer { removeVault(store) }
        let synchronizer = FakeKnowledgeActionSynchronizer()
        let executor = KnowledgeActionExecutor(store: store, synchronizer: synchronizer)
        let target = try XCTUnwrap(store.createNote(id: "contract-target", title: "目标", body: "旧稿"))
        let source = try XCTUnwrap(store.createNote(id: "contract-source", title: "来源", body: "材料"))
        let targetHash = store.contentHash(for: target)
        let sourceHash = store.contentHash(for: source)
        let action = mergeAction(step: .init(
            kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id],
            markdown: "合并完成", originalContentHash: targetHash,
            sourceContentHashes: [source.id: sourceHash]
        ))

        let result = await executor.execute(action)

        XCTAssertEqual(result.state, .synced)
        XCTAssertEqual(synchronizer.mergeRequests.count, 1)
        let request = try XCTUnwrap(synchronizer.mergeRequests.first)
        XCTAssertEqual(request.operationId, action.id)
        XCTAssertEqual(request.targetNoteId, target.id)
        XCTAssertEqual(request.targetBaseHash, targetHash)
        XCTAssertEqual(request.sourceVersions, [source.id: sourceHash])
        XCTAssertEqual(request.revisedContent, store.markdown(for: try XCTUnwrap(store.note(id: target.id))))
        XCTAssertEqual(synchronizer.legacyMergeMutationCount, 0)
    }

    func testMergeRejectsMissingMalformedHashesAndSourceOnlyLegacyRequestsBeforeMutation() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let target = try XCTUnwrap(store.createNote(id: "hash-target", title: "目标", body: "原文"))
        let source = try XCTUnwrap(store.createNote(id: "hash-source", title: "来源", body: "材料"))
        let targetHash = store.contentHash(for: target)
        let invalidSteps: [KnowledgeActionStep] = [
            .init(kind: "merge_notes", sourceNoteIds: [source.id], markdown: "拒绝"),
            .init(kind: "merge_notes", targetNoteId: target.id, markdown: "拒绝"),
            .init(kind: "merge_notes", targetNoteId: target.id, markdown: "拒绝", originalContentHash: String(repeating: "A", count: 64)),
            .init(kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id], markdown: "拒绝", originalContentHash: targetHash),
            .init(kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id], markdown: "拒绝", originalContentHash: targetHash, sourceContentHashes: [source.id: "bad-hash"]),
        ]

        for step in invalidSteps {
            let result = await executor.execute(mergeAction(step: step))
            XCTAssertEqual(result.state, .stale)
            XCTAssertEqual(store.note(id: target.id)?.body, "原文")
            XCTAssertEqual(store.note(id: source.id)?.body, "材料")
            XCTAssertEqual(Set(store.notes.map(\.id)), [target.id, source.id])
        }
    }

    func testMergeRejectsMissingOrArchivedTargetBeforeMutation() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let target = try XCTUnwrap(store.createNote(id: "archived-target", title: "目标", body: "原文"))
        let hash = store.contentHash(for: target)
        _ = try XCTUnwrap(store.archive(id: target.id, mergedInto: "prior-target"))

        for targetID in [target.id, "missing-target"] {
            let result = await executor.execute(mergeAction(step: .init(
                kind: "merge_notes", targetNoteId: targetID, markdown: "拒绝",
                originalContentHash: hash
            )))
            XCTAssertEqual(result.state, .stale)
        }
        XCTAssertNil(store.note(id: target.id))
        XCTAssertEqual(store.archivedNote(id: target.id)?.body, "原文")
    }

    func testMergeRejectsChangedTargetAndSourceVersionsBeforeMutation() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let target = try XCTUnwrap(store.createNote(id: "changed-target", title: "目标", body: "目标 v1"))
        let source = try XCTUnwrap(store.createNote(id: "changed-source", title: "来源", body: "来源 v1"))
        let originalTargetHash = store.contentHash(for: target)
        let originalSourceHash = store.contentHash(for: source)
        _ = try XCTUnwrap(store.save(id: target.id, title: target.title, body: "目标 v2", tags: target.tags, isPinned: target.isPinned))
        var result = await executor.execute(mergeAction(step: .init(
            kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id], markdown: "拒绝",
            originalContentHash: originalTargetHash, sourceContentHashes: [source.id: originalSourceHash]
        )))
        XCTAssertEqual(result.state, .stale)
        XCTAssertEqual(store.note(id: target.id)?.body, "目标 v2")

        let currentTarget = try XCTUnwrap(store.note(id: target.id))
        _ = try XCTUnwrap(store.save(id: source.id, title: source.title, body: "来源 v2", tags: source.tags, isPinned: source.isPinned))
        result = await executor.execute(mergeAction(step: .init(
            kind: "merge_notes", targetNoteId: target.id, sourceNoteIds: [source.id], markdown: "拒绝",
            originalContentHash: store.contentHash(for: currentTarget), sourceContentHashes: [source.id: originalSourceHash]
        )))
        XCTAssertEqual(result.state, .stale)
        XCTAssertEqual(store.note(id: target.id)?.body, "目标 v2")
        XCTAssertEqual(store.note(id: source.id)?.body, "来源 v2")
    }

    func testSourceOnlySavedReceiptIsRejectedDuringRecoveryWithoutCreatingID() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let source = try XCTUnwrap(store.createNote(id: "legacy-source", title: "来源", body: "原文"))
        let action = mergeAction(step: .init(
            kind: "merge_notes", sourceNoteIds: [source.id], markdown: "旧版合并",
            sourceContentHashes: [source.id: store.contentHash(for: source)]
        ))
        try FileManager.default.createDirectory(at: store.actionDirectory, withIntermediateDirectories: true)
        let receipt = try JSONSerialization.data(withJSONObject: [
            "actionId": action.id,
            "actionDigest": action.actionDigest,
            "accountFingerprint": store.accountFingerprint,
            "status": "local_applied",
            "resultNoteIds": [source.id],
            "updatedAt": 0,
        ])
        try receipt.write(to: store.actionDirectory.appendingPathComponent("\(action.id).json"), options: .atomic)

        let result = await executor.execute(action)
        XCTAssertEqual(result.state, .stale)
        XCTAssertEqual(store.note(id: source.id)?.body, "原文")
        XCTAssertEqual(store.notes.map(\.id), [source.id])
        XCTAssertFalse(store.notes.contains { $0.id.hasPrefix("ka-") })
    }

    func testUpdateCarriesCASAndOrdinaryArchiveHasNoMergeTarget() async throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "cas-archive-\(UUID())", userId: "user")
        defer { removeVault(store) }
        let synchronizer = FakeKnowledgeActionSynchronizer()
        let executor = KnowledgeActionExecutor(store: store, synchronizer: synchronizer)
        let note = try XCTUnwrap(store.createNote(id: "note-a", title: "A", body: "v1"))
        let baseHash = store.contentHash(for: note)
        var result = await executor.execute(KnowledgeActionBlock(
            id: "update-\(UUID())", summary: "更新", steps: [.init(
                kind: "update_note", targetNoteId: note.id,
                markdown: "# A\n\nv2", originalContentHash: baseHash
            )], actionDigest: "update-digest", transientCapability: "capability",
            expiresAt: Int(Date().timeIntervalSince1970) + 3600
        ))
        XCTAssertEqual(result.state, .synced)
        XCTAssertEqual(synchronizer.syncBaseHashes.last!, baseHash)

        let current = try XCTUnwrap(store.note(id: note.id))
        let archiveHash = store.contentHash(for: current)
        result = await executor.execute(KnowledgeActionBlock(
            id: "archive-\(UUID())", summary: "归档", steps: [.init(
                kind: "archive_note", targetNoteId: note.id,
                originalContentHash: archiveHash
            )], actionDigest: "archive-digest", transientCapability: "capability",
            expiresAt: Int(Date().timeIntervalSince1970) + 3600
        ))
        XCTAssertEqual(result.state, .synced)
        XCTAssertNil(synchronizer.archiveMergeTargets.last!)
        XCTAssertEqual(synchronizer.archiveExpectedHashes.last!, archiveHash)
    }

    func testStaleUpdateAndArchiveCASFailBeforeLocalMutation() async throws {
        let (store, executor) = isolatedStoreAndExecutor()
        defer { removeVault(store) }
        let note = try XCTUnwrap(store.createNote(id: "stale-note", title: "A", body: "v1"))
        let staleHash = store.contentHash(for: note)
        _ = try XCTUnwrap(store.save(
            id: note.id, title: note.title, body: "v2", tags: note.tags, isPinned: note.isPinned
        ))

        for step in [
            KnowledgeActionStep(
                kind: "update_note", targetNoteId: note.id,
                markdown: "# A\n\noverwrote", originalContentHash: staleHash
            ),
            KnowledgeActionStep(
                kind: "archive_note", targetNoteId: note.id,
                originalContentHash: staleHash
            ),
        ] {
            let id = UUID().uuidString.lowercased()
            let result = await executor.execute(KnowledgeActionBlock(
                id: id, summary: "CAS", steps: [step], actionDigest: "digest-\(id)",
                transientCapability: "test-capability",
                expiresAt: Int(Date().timeIntervalSince1970) + 3_600
            ))
            XCTAssertEqual(result.state, .stale)
            XCTAssertEqual(store.note(id: note.id)?.body, "v2")
            XCTAssertNil(store.archivedNote(id: note.id))
        }
    }

    func testServerSyncedNotesParticipateInKnowledgeWorkspaceSnapshot() {
        let server = ChatLocalNoteDTO(
            id: "server-only",
            title: "服务端笔记",
            markdown: "# 服务端笔记\n\n正文",
            updatedAt: "2026-09-05T01:00:00Z",
            contentHash: String(repeating: "a", count: 64)
        )
        let local = ChatLocalNoteDTO(
            id: "local-only",
            title: "本地笔记",
            markdown: "# 本地笔记",
            updatedAt: "2026-09-05T02:00:00Z",
            contentHash: String(repeating: "b", count: 64)
        )
        let snapshot = TenantSessionCoordinator.mergeWorkspaceNotes(
            server: [server], local: [local]
        )
        XCTAssertEqual(Set(snapshot.map(\.id)), Set(["server-only", "local-only"]))
        XCTAssertEqual(snapshot.first(where: { $0.id == "server-only" })?.contentHash, server.contentHash)
    }

    func testCloudSnapshotWithoutFrontmatterPreservesServerNoteID() throws {
        let store = KnowledgeNoteStore.shared
        store.activate(tenantKey: "cloud-id-tenant-\(UUID())", userId: "cloud-id-user")
        let snapshot = CloudKnowledgeNoteDTO(
            noteId: "server-stable-id",
            markdown: "# 服务端原始笔记\n\n没有 frontmatter。",
            contentHash: String(repeating: "a", count: 64),
            updatedAt: "2026-09-06T00:00:00Z",
            archived: false,
            mergedIntoNoteId: nil
        )
        try store.restoreFromCloudSnapshot(CloudKnowledgeNotesResponse(
            items: [snapshot], count: 1, compileStatus: "private_index_ready"
        ))
        defer { store.moveToTrash(id: snapshot.noteId) }

        XCTAssertEqual(store.note(id: snapshot.noteId)?.id, snapshot.noteId)
        XCTAssertNil(store.notes.first(where: { $0.fileURL.lastPathComponent == "server-stable-id.md" && $0.id != snapshot.noteId }))
    }

    func testCloudRestoreRemovesArchivedDuplicateOfActiveNoteID() throws {
        let store = KnowledgeNoteStore.shared
        store.activate(tenantKey: "cloud-dedupe-tenant-\(UUID())", userId: "cloud-dedupe-user")
        let note = try XCTUnwrap(store.createNote(id: "dedupe-id", title: "九州旅行纲要", body: "完整正文"))
        defer { store.moveToTrash(id: note.id) }
        try FileManager.default.createDirectory(at: store.archiveDirectory, withIntermediateDirectories: true)
        let duplicate = store.archiveDirectory.appendingPathComponent("stale-copy.md")
        try store.markdown(for: note).write(to: duplicate, atomically: true, encoding: .utf8)
        store.reload()
        XCTAssertNotNil(store.archivedNote(id: note.id))

        let markdown = store.markdown(for: try XCTUnwrap(store.note(id: note.id)))
        let hash = SHA256.hash(data: Data(markdown.utf8)).map { String(format: "%02x", $0) }.joined()
        try store.restoreFromCloudSnapshot(CloudKnowledgeNotesResponse(
            items: [.init(
                noteId: note.id, markdown: markdown, contentHash: hash,
                updatedAt: "2099-09-06T00:00:00Z", archived: false, mergedIntoNoteId: nil
            )],
            count: 1,
            compileStatus: "private_index_ready"
        ))

        XCTAssertNotNil(store.note(id: note.id))
        XCTAssertNil(store.archivedNote(id: note.id))
        XCTAssertFalse(FileManager.default.fileExists(atPath: duplicate.path))
    }

    func testNewerLocalEditWinsOverServerSnapshotOfSameNote() {
        let server = ChatLocalNoteDTO(
            id: "same",
            title: "服务端",
            markdown: "old",
            updatedAt: "2026-09-05T01:00:00Z",
            contentHash: String(repeating: "a", count: 64)
        )
        let local = ChatLocalNoteDTO(
            id: "same",
            title: "本地",
            markdown: "new",
            updatedAt: "2026-09-05T02:00:00Z",
            contentHash: String(repeating: "b", count: 64)
        )
        let snapshot = TenantSessionCoordinator.mergeWorkspaceNotes(
            server: [server], local: [local]
        )
        XCTAssertEqual(snapshot.map(\.markdown), ["new"])
    }

    func testSaveIntentRequiresProposalButUnrelatedSaveQuestionDoesNot() {
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("保存"))
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("把这段整理成笔记并保存"))
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("合并这两篇笔记"))
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("以上所有关于采尔马特的都帮我保存"))
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("关于伊斯坦布尔交通信息，帮我保存"))
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeActionProposal("把刚才的内容都记下来"))
        XCTAssertFalse(TenantSessionCoordinator.requiresKnowledgeActionProposal("iOS 如何保存图片到相册？"))
        XCTAssertFalse(TenantSessionCoordinator.requiresKnowledgeActionProposal("解释一下这段内容"))
        XCTAssertFalse(TenantSessionCoordinator.shouldAttachClientSessionContext(
            userText: "解释一下这段内容", hasRecoveryContext: false, hasLocalNotes: false
        ))
        XCTAssertTrue(TenantSessionCoordinator.shouldAttachClientSessionContext(
            userText: "保存为笔记", hasRecoveryContext: false, hasLocalNotes: false
        ))
        XCTAssertTrue(TenantSessionCoordinator.shouldAttachClientSessionContext(
            userText: "继续", hasRecoveryContext: true, hasLocalNotes: false
        ))
        XCTAssertTrue(TenantSessionCoordinator.shouldShowKnowledgeProposalRetry(
            userText: "保存为笔记", hasProposal: false
        ))
        XCTAssertFalse(TenantSessionCoordinator.shouldShowKnowledgeProposalRetry(
            userText: "保存为笔记", hasProposal: true
        ))
    }
    func testTextPresentationProposalPreservesRegistryInput() throws {
        let data = Data(#"{"proposal_id":"ppt-text-1","capability_id":"presentation.create_from_text","input":{"title":"因特拉肯旅行攻略","text_material":"湖泊、雪山与少女峰路线","intended_use":"travel_guide","layout_style":"editorial_16_9","slide_count":10,"clarification_strategy":"use_defaults_unless_blocked"},"summary":"Create deck","risk":"medium","state":"awaiting_confirmation"}"#.utf8)
        let proposal = try JSONDecoder().decode(CapabilityProposalBlock.self, from: data)
        XCTAssertEqual(proposal.capabilityId, QCPCapabilityID.presentationCreateFromText)
        XCTAssertEqual(proposal.input.textMaterial, "湖泊、雪山与少女峰路线")
        XCTAssertEqual(proposal.input.intendedUse, "travel_guide")
        XCTAssertEqual(proposal.input.layoutStyle, "editorial_16_9")
        XCTAssertEqual(proposal.input.slideCount, 10)
    }

    private func isolatedStoreAndExecutor() -> (KnowledgeNoteStore, KnowledgeActionExecutor) {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "merge-tenant-\(UUID())", userId: "merge-user")
        return (store, KnowledgeActionExecutor(store: store, synchronizer: FakeKnowledgeActionSynchronizer()))
    }

    private func removeVault(_ store: KnowledgeNoteStore) {
        try? FileManager.default.removeItem(at: store.vaultDirectory)
        store.reload()
    }

    private func mergeAction(step: KnowledgeActionStep) -> KnowledgeActionBlock {
        let id = UUID().uuidString.lowercased()
        return KnowledgeActionBlock(
            id: id, summary: "合并", steps: [step], actionDigest: "digest-\(id)",
            transientCapability: "test-capability",
            expiresAt: Int(Date().timeIntervalSince1970) + 3_600
        )
    }
}

@MainActor
private final class FakeKnowledgeActionSynchronizer: KnowledgeActionSynchronizing {
    var afterSync: (() -> Void)?
    private(set) var illustrationRequests: [(String, KnowledgeActionStep, String)] = []
    func enqueueIllustrations(store: KnowledgeNoteStore, id: String, step: KnowledgeActionStep, requestID: String) {
        illustrationRequests.append((id, step, requestID))
    }
    private var notes: [String: CloudKnowledgeNoteDTO] = [:]
    private(set) var mergeRequests: [KnowledgeNoteMergeRequestDTO] = []
    private(set) var legacyMergeMutationCount = 0
    private(set) var syncBaseHashes: [String?] = []
    private(set) var archiveMergeTargets: [String?] = []
    private(set) var archiveExpectedHashes: [String?] = []

    func fetchKnowledgeNotes(includeArchived: Bool) async throws -> CloudKnowledgeNotesResponse {
        let items = notes.values.filter { includeArchived || !$0.archived }
        return .init(items: items, count: items.count, compileStatus: "ready")
    }

    func syncKnowledgeNote(id: String, markdown: String, updatedAt: Date, baseHash: String?, credentialGeneration: UInt64) async throws {
        legacyMergeMutationCount += 1
        syncBaseHashes.append(baseHash)
        let hash = SHA256.hash(data: Data(markdown.utf8)).map { String(format: "%02x", $0) }.joined()
        notes[id] = .init(
            noteId: id, markdown: markdown, contentHash: hash, updatedAt: nil,
            archived: false, mergedIntoNoteId: nil
        )
        afterSync?()
    }

    func archiveKnowledgeNote(id: String, mergedIntoNoteId: String?, expectedContentHash: String?) async throws {
        legacyMergeMutationCount += 1
        archiveMergeTargets.append(mergedIntoNoteId)
        archiveExpectedHashes.append(expectedContentHash)
        guard let note = notes[id] else { return }
        notes[id] = .init(
            noteId: note.noteId, markdown: note.markdown, contentHash: note.contentHash,
            updatedAt: note.updatedAt, archived: true, mergedIntoNoteId: mergedIntoNoteId
        )
    }

    func mergeKnowledgeNotes(_ body: KnowledgeNoteMergeRequestDTO) async throws -> KnowledgeNoteMergeResponseDTO {
        mergeRequests.append(body)
        let hash = SHA256.hash(data: Data(body.revisedContent.utf8)).map { String(format: "%02x", $0) }.joined()
        notes[body.targetNoteId] = .init(
            noteId: body.targetNoteId, markdown: body.revisedContent, contentHash: hash,
            updatedAt: nil, archived: false, mergedIntoNoteId: nil
        )
        for (id, version) in body.sourceVersions {
            notes[id] = .init(
                noteId: id, markdown: "", contentHash: version, updatedAt: nil,
                archived: true, mergedIntoNoteId: body.targetNoteId
            )
        }
        return .init(
            operationId: body.operationId, targetNoteId: body.targetNoteId,
            status: "completed", revisedHash: hash
        )
    }

    func restoreKnowledgeNote(id: String) async throws {}
    func trashKnowledgeNote(id: String) async throws {}
    func commitKnowledgeAction(id: String, capability: String, actionDigest: String, status: String, resultNoteIds: [String], errorCode: String?) async throws {}
    func resumeKnowledgeActionSync(id: String, actionDigest: String, status: String, resultNoteIds: [String], errorCode: String?) async throws {}
    func discardKnowledgeAction(id: String, capability: String, actionDigest: String) async throws {}
}

@MainActor
final class NoteIllustrationTests: XCTestCase {
    private func asset(anchor: String) -> NoteIllustrationAsset {
        .init(runId: String(repeating: "a", count: 32), index: 0, anchor: anchor,
              alt: "AI 插图：学习", sha256: String(repeating: "b", count: 64), provider: "fixture", model: "fixture")
    }
    func testUnicodeCursorAndUnsafeLocations() {
        let body = "开头🌿\n\n这一段讲学习。\n\n结尾"
        let position = (body as NSString).range(of: "讲学习").location
        XCTAssertEqual(NoteIllustrationPlacement.anchor(in: body, selection: NSRange(location: position, length: 0)), "这一段讲学习。")
        XCTAssertNil(NoteIllustrationPlacement.anchor(in: "```swift\nlet x = 1\n```", selection: NSRange(location: 12, length: 0)))
        XCTAssertEqual(NoteIllustrationPlacement.anchor(in: "> [!note] 重点\n> 内容", selection: NSRange(location: 17, length: 0)), "> [!note] 重点\n> 内容")
        XCTAssertNil(NoteIllustrationPlacement.anchor(in: "重复\n\n重复", selection: NSRange(location: 1, length: 0)))
    }
    func testInsertionPreservesSourceAndIsIdempotent() throws {
        let body = "开头\n\n学习方法\n\n结尾"
        let image = asset(anchor: "学习方法")
        let inserted = try XCTUnwrap(NoteIllustrationPlacement.inserting([image], into: body, travel: false))
        XCTAssertTrue(inserted.hasPrefix("开头\n\n学习方法\n\n!["))
        XCTAssertTrue(inserted.hasSuffix("\n\n结尾"))
        XCTAssertEqual(NoteIllustrationPlacement.inserting([image], into: inserted, travel: false), inserted)
        XCTAssertNil(NoteIllustrationPlacement.inserting([asset(anchor: "不存在")], into: body, travel: false))
    }
    func testTravelIllustrationsPreserveAllExistingFields() throws {
        let body = "{\"stops\":[],\"destination\":\"杭州\",\"journal\":\"真实记录\",\"custom\":42}"
        let result = try XCTUnwrap(NoteIllustrationPlacement.inserting([asset(anchor: "overview")], into: body, travel: true))
        let object = try XCTUnwrap(NoteIllustrationPlacement.travelObject(result))
        XCTAssertEqual(object["destination"] as? String, "杭州")
        XCTAssertEqual(object["journal"] as? String, "真实记录")
        XCTAssertEqual(object["custom"] as? Int, 42)
        XCTAssertEqual((object["illustrations"] as? [[String: String]])?.count, 1)
        XCTAssertNotNil(TravelPlanDocument.decode(result))
        XCTAssertNil(NoteIllustrationPlacement.inserting([asset(anchor: "overview")], into: "普通游记", travel: true))
    }
    func testTravelJournalCodeFencesSurviveOuterJSONFence() throws {
        let journal = "```swift\nlet day = 1\n```"
        let body = try XCTUnwrap(NoteIllustrationPlacement.json(["stops": [], "journal": journal, "dateRange": "Oct 1"]))
        let wrapped = "```json\n" + body + "\n```"
        XCTAssertEqual(NoteIllustrationPlacement.travelObject(wrapped)?["journal"] as? String, journal)
        XCTAssertEqual(TravelPlanDocument.decode(wrapped)?.dateRange, "Oct 1")
    }
    func testUnsavedDraftPreventsAutomaticOverwrite() throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "illustration-test-\(UUID())", userId: "test")
        defer { try? FileManager.default.removeItem(at: store.vaultDirectory) }
        let note = try XCTUnwrap(store.createNote(title: "学习", body: "原始段落"))
        let request = NoteIllustrationRequest(noteId: note.id, requestId: "test-request", title: note.title, content: note.body,
                                              sourceHash: NoteIllustrationPlacement.hash(note.body), mode: "auto", anchor: "", brief: "", travel: false)
        store.illustrationJobs[note.id] = .init(request: request, originalBody: note.body,
            response: .init(runId: String(repeating: "a", count: 32), status: "completed", message: "", assets: [asset(anchor: note.body)], failedIndices: [], errorCode: ""), message: "")
        store.activeNoteDrafts[note.id] = "正在输入的新内容"
        XCTAssertFalse(store.applyIllustrations(id: note.id))
        XCTAssertEqual(store.note(id: note.id)?.body, "原始段落")
        XCTAssertTrue(store.illustrationJobs[note.id]?.message.contains("正文已变化") == true)
    }
    func testCompletedManualJobResumesCachedPreviewWithoutRegenerating() async throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "illustration-resume-\(UUID())", userId: "test")
        defer { try? FileManager.default.removeItem(at: store.vaultDirectory) }
        let note = try XCTUnwrap(store.createNote(title: "学习", body: "学习方法"))
        let data = Data("cached-image-fixture".utf8)
        var image = asset(anchor: note.body)
        image.sha256 = NoteIllustrationPlacement.hashData(data)
        let path = store.vaultDirectory.appendingPathComponent(image.relativePath)
        try FileManager.default.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: path)
        let request = NoteIllustrationRequest(noteId: note.id, requestId: "resume-test", title: note.title, content: note.body,
                                              sourceHash: NoteIllustrationPlacement.hash(note.body), mode: "manual", anchor: note.body, brief: "学习场景", travel: false)
        store.illustrationJobs[note.id] = .init(request: request, originalBody: note.body,
            response: .init(runId: image.runId, status: "completed", message: "", assets: [image], failedIndices: [], errorCode: ""), message: "恢复中")
        store.resumeIllustrations(id: note.id)
        for _ in 0..<50 where store.illustrationIsRunning(note.id) { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(store.illustrationJobs[note.id]?.message, "插图已生成，待插入")
        XCTAssertEqual(store.note(id: note.id)?.body, note.body)
        store.illustrationJobs[note.id]?.cancelled = true
        XCTAssertFalse(store.applyIllustrations(id: note.id))
    }
    private func confirmedAction(_ step: KnowledgeActionStep) -> KnowledgeActionBlock {
        .init(id: "ka-" + UUID().uuidString, summary: "笔记操作", steps: [step], actionDigest: UUID().uuidString,
              transientCapability: "test-capability", expiresAt: Int(Date().timeIntervalSince1970) + 3600)
    }

    func testConfirmedTravelSaveQueuesOnceAfterSyncAndPreservesPreference() async throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "chat-travel-\(UUID())", userId: "test")
        defer { try? FileManager.default.removeItem(at: store.vaultDirectory) }
        let sync = FakeKnowledgeActionSynchronizer()
        let executor = KnowledgeActionExecutor(store: store, synchronizer: sync)
        let action = confirmedAction(.init(kind: "create_note", title: "杭州之旅", markdown: "原始游记", tags: ["大学生活"], layout: "travel", automaticIllustrations: false))
        let result = await executor.execute(action)
        XCTAssertEqual(result.state, .synced)
        let note = try XCTUnwrap(result.noteIds.first.flatMap { store.note(id: $0) })
        XCTAssertEqual(NoteIllustrationPlacement.travelObject(note.body)?["journal"] as? String, "原始游记")
        XCTAssertTrue(note.tags.contains("旅行"))
        XCTAssertTrue(note.tags.contains("大学生活"))
        XCTAssertFalse(store.automaticIllustrationsEnabled(note.id))
        XCTAssertEqual(sync.illustrationRequests.count, 1)
        _ = await executor.execute(action)
        XCTAssertEqual(sync.illustrationRequests.count, 1, "Replaying a completed receipt must not enqueue another paid generation")
    }

    func testConfirmedGenerationKeepsBodyAndRejectsChangedSnapshot() async throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "chat-image-\(UUID())", userId: "test")
        defer { try? FileManager.default.removeItem(at: store.vaultDirectory) }
        let note = try XCTUnwrap(store.createNote(title: "夜读", body: "宿舍里一起读书。"))
        let sync = FakeKnowledgeActionSynchronizer()
        let executor = KnowledgeActionExecutor(store: store, synchronizer: sync)
        let step = KnowledgeActionStep(kind: "illustrate_note", targetNoteId: note.id, originalContentHash: store.contentHash(for: note),
            illustrationAction: "generate", illustrationAnchor: note.body, illustrationBrief: "暖灯与同学", illustrationInsert: false)
        let result = await executor.execute(confirmedAction(step))
        XCTAssertEqual(result.state, .synced)
        XCTAssertEqual(store.note(id: note.id)?.body, note.body)
        XCTAssertEqual(sync.illustrationRequests.count, 1)
        XCTAssertEqual(sync.illustrationRequests[0].1.illustrationBrief, "暖灯与同学")
        _ = store.save(id: note.id, title: note.title, body: "后来修改了正文", tags: [], isPinned: false)
        let stale = await executor.execute(confirmedAction(step))
        XCTAssertEqual(stale.state, .stale)
        XCTAssertEqual(sync.illustrationRequests.count, 1)
    }

    func testChangedBodyDuringSyncDoesNotStartPaidGeneration() async throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "chat-race-\(UUID())", userId: "test")
        defer { try? FileManager.default.removeItem(at: store.vaultDirectory) }
        let note = try XCTUnwrap(store.createNote(title: "夜读", body: "一起读书。"))
        let sync = FakeKnowledgeActionSynchronizer()
        sync.afterSync = { _ = store.save(id: note.id, title: note.title, body: "同步期间编辑的正文", tags: [], isPinned: false) }
        let executor = KnowledgeActionExecutor(store: store, synchronizer: sync)
        let step = KnowledgeActionStep(kind: "illustrate_note", targetNoteId: note.id, originalContentHash: store.contentHash(for: note), illustrationAction: "generate")
        let result = await executor.execute(confirmedAction(step))
        XCTAssertEqual(result.state, .stale)
        XCTAssertTrue(sync.illustrationRequests.isEmpty)
        XCTAssertEqual(store.note(id: note.id)?.body, "同步期间编辑的正文")
    }

    func testChatApplyAndUndoKeepLaterWritingAndBindRun() async throws {
        let store = KnowledgeNoteStore()
        store.activate(tenantKey: "chat-apply-\(UUID())", userId: "test")
        defer { try? FileManager.default.removeItem(at: store.vaultDirectory) }
        let note = try XCTUnwrap(store.createNote(title: "阅读", body: "学习方法"))
        let image = asset(anchor: note.body)
        let request = NoteIllustrationRequest(noteId: note.id, requestId: "chat-test", title: note.title, content: note.body,
            sourceHash: NoteIllustrationPlacement.hash(note.body), mode: "manual", anchor: note.body, brief: "读书", travel: false)
        store.illustrationJobs[note.id] = .init(request: request, originalBody: note.body,
            response: .init(runId: image.runId, status: "completed", message: "", assets: [image], failedIndices: [], errorCode: ""), message: "")
        let executor = KnowledgeActionExecutor(store: store, synchronizer: FakeKnowledgeActionSynchronizer())
        let bad = KnowledgeActionStep(kind: "illustrate_note", targetNoteId: note.id, originalContentHash: store.contentHash(for: note), illustrationAction: "apply", illustrationRunId: String(repeating: "c", count: 32))
        XCTAssertFalse(store.canApplyIllustrationStep(bad))
        let apply = KnowledgeActionStep(kind: "illustrate_note", targetNoteId: note.id, originalContentHash: store.contentHash(for: note), illustrationAction: "apply", illustrationRunId: image.runId)
        let applied = await executor.execute(confirmedAction(apply))
        XCTAssertEqual(applied.state, .synced)
        let withImage = try XCTUnwrap(store.note(id: note.id))
        XCTAssertTrue(withImage.body.contains(image.relativePath))
        let changed = try XCTUnwrap(store.save(id: note.id, title: note.title, body: withImage.body + "\n\n后续文字", tags: [], isPinned: false))
        let undo = KnowledgeActionStep(kind: "illustrate_note", targetNoteId: note.id, originalContentHash: store.contentHash(for: changed), illustrationAction: "undo", illustrationRunId: image.runId)
        let undone = await executor.execute(confirmedAction(undo))
        XCTAssertEqual(undone.state, .synced)
        XCTAssertEqual(store.note(id: note.id)?.body, "学习方法\n\n后续文字")
        XCTAssertEqual(store.illustrationJobs[note.id]?.undone, true)
    }

    func testChatProposalPreservesIllustrationFields() throws {
        let event: [String: Any] = ["type": "knowledge_action_draft", "action_id": "image-action", "steps": [[
            "kind": "illustrate_note", "target_note_id": "note-a", "illustration_action": "generate",
            "illustration_anchor": "宿舍夜读。", "illustration_brief": "清新暖灯", "illustration_insert": false,
            "automatic_illustrations": false, "layout": "travel"
        ]]]
        guard case .knowledgeActionDraft(let action) = APIClient.StreamEvent.parse(event) else {
            return XCTFail("Expected a signed note proposal event")
        }
        let step = try XCTUnwrap(action.steps.first)
        XCTAssertEqual(step.illustrationAnchor, "宿舍夜读。")
        XCTAssertEqual(step.illustrationBrief, "清新暖灯")
        XCTAssertEqual(step.illustrationInsert, false)
        XCTAssertEqual(step.automaticIllustrations, false)
        XCTAssertEqual(step.layout, "travel")
        let restored = try JSONDecoder().decode(KnowledgeActionStep.self, from: JSONEncoder().encode(step))
        XCTAssertEqual(restored, step)
    }

    func testGeneratedAssetFilenameIsStrict() {
        let image = asset(anchor: "x")
        XCTAssertEqual(NoteIllustrationPlacement.asset(from: (image.relativePath as NSString).lastPathComponent)?.sha256, image.sha256)
        XCTAssertNil(NoteIllustrationPlacement.asset(from: "../../secret.jpg"))
        XCTAssertNil(NoteIllustrationPlacement.asset(from: "ai-user-9-bad.jpg"))
    }
}
