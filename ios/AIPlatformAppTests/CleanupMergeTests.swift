import XCTest
@testable import AIPlatformApp

final class CleanupMergeTests: XCTestCase {
    @MainActor
    func testNaturalConfirmationIsExplicitAndScopedToOneSession() {
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeWorkspace("帮我清理"))
        XCTAssertTrue(TenantSessionCoordinator.requiresKnowledgeWorkspace("比较这两篇笔记"))
        XCTAssertFalse(TenantSessionCoordinator.requiresKnowledgeWorkspace("今天天气怎么样"))
        XCTAssertEqual(TenantSessionCoordinator.naturalConfirmationVerb(" 确认合并 "), "apply")
        XCTAssertEqual(TenantSessionCoordinator.naturalConfirmationVerb("取消这次操作"), "discard")
        XCTAssertNil(TenantSessionCoordinator.naturalConfirmationVerb("好的"))
        XCTAssertNil(TenantSessionCoordinator.naturalConfirmationVerb("先不要确认合并"))
        func message(_ session: String, _ id: String, state: KnowledgeActionState = .proposed) -> ChatMessage {
            var message = ChatMessage(sessionId: session, role: .assistant, content: "")
            message.blocks = [.knowledgeAction(.init(id: id, summary: "", steps: [], actionDigest: "digest", transientCapability: nil, expiresAt: 0, state: state))]
            return message
        }
        let messages = [message("current", "a"), message("other", "b"), message("current", "old", state: .discarded)]
        XCTAssertEqual(TenantSessionCoordinator.pendingConfirmationActions(in: messages, sessionID: "current").map(\.actionID), ["a"])
        XCTAssertTrue(TenantSessionCoordinator.pendingConfirmationActions(in: messages, sessionID: "missing").isEmpty)
        XCTAssertEqual(TenantSessionCoordinator.pendingConfirmationActions(in: messages + [message("current", "c")], sessionID: "current").count, 2)
    }

    func testUnavailableOrEmptyTasksDoNotExposeATab() {
        XCTAssertEqual(CleanupFilterPolicy.domains(taskAvailable: false, taskCount: 3), [0, 1, 2])
        XCTAssertEqual(CleanupFilterPolicy.domains(taskAvailable: true, taskCount: 0), [0, 1, 2])
        XCTAssertEqual(CleanupFilterPolicy.domains(taskAvailable: true, taskCount: 2), [0, 1, 2, 3])
    }

    func testEmptyBodyCannotBeAccepted() {
        let preview = KnowledgeMergePreview(targetNoteId: "a", sourceNoteId: "b", targetHash: "a", sourceHash: "b", coarse: false, segments: [])
        XCTAssertNil(preview.mergedMarkdown(choices: [:]))
    }

    func testMergeRequiresEveryConflictChoiceAndKeepsUnsharedContent() {
        let preview = KnowledgeMergePreview(targetNoteId: "a", sourceNoteId: "b", targetHash: "a", sourceHash: "b", coarse: false, segments: [
            .init(id: "0", kind: "equal", before: "相同\n\n", after: "相同\n\n", beforeRuns: [], afterRuns: [], targetBlocks: 1, sourceBlocks: 1),
            .init(id: "1", kind: "replace", before: "300\n\n", after: "500\n\n", beforeRuns: [], afterRuns: [], targetBlocks: 1, sourceBlocks: 1),
            .init(id: "2", kind: "delete", before: "仅保留项有\n\n", after: "", beforeRuns: [], afterRuns: [], targetBlocks: 1, sourceBlocks: 0),
            .init(id: "3", kind: "insert", before: "", after: "来源新增🙂", beforeRuns: [], afterRuns: [], targetBlocks: 0, sourceBlocks: 1),
        ])
        XCTAssertNil(preview.mergedMarkdown(choices: [:]))
        XCTAssertNil(preview.mergedMarkdown(choices: ["1": "unrecognized"]))
        XCTAssertEqual(preview.mergedMarkdown(choices: ["1": "both"]), "相同\n\n300\n\n500\n\n仅保留项有\n\n来源新增🙂")
        XCTAssertEqual(preview.mergedMarkdown(choices: ["1": "source"]), "相同\n\n500\n\n仅保留项有\n\n来源新增🙂")
        XCTAssertEqual(preview.mergedMarkdown(choices: ["1": "target"]), "相同\n\n300\n\n仅保留项有\n\n来源新增🙂")
    }
}
