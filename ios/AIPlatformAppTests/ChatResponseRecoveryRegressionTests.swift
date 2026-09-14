import XCTest
@testable import AIPlatformApp

@MainActor
final class ChatResponseRecoveryRegressionTests: XCTestCase {
    func testRunningBeforeFirstDeltaDoesNotLookEmpty() {
        let message = ChatMessage(
            id: "running", sessionId: "session", role: .assistant,
            content: "", isStreaming: true, pending: true
        )

        XCTAssertFalse(message.shouldShowEmptyResponseError)
        XCTAssertTrue(TenantSessionCoordinator.shouldPresentAutomaticRecovery(
            message,
            activeInFlightMessageID: nil,
            reconcilingMessageIDs: [message.id],
            backgroundProcessingSessionIDs: []
        ))
    }

    func testCompletedToolBeforeFirstDeltaDoesNotLookEmpty() {
        let message = ChatMessage(
            role: .assistant, content: "", isStreaming: true,
            blocks: [.reasoning([ReasoningStep(
                type: .toolCall, title: "搜索", detail: "已完成", status: "done"
            )])]
        )

        XCTAssertFalse(message.shouldShowEmptyResponseError)
    }

    func testKnowledgeActionWithoutBodyIsAValidResult() {
        let action = KnowledgeActionBlock(
            id: "action", summary: "保存研究", steps: [], actionDigest: "digest",
            transientCapability: nil, expiresAt: 0
        )
        let message = ChatMessage(
            role: .assistant, content: "", blocks: [.knowledgeAction(action)]
        )

        XCTAssertTrue(message.hasRenderableAssistantResult)
        XCTAssertFalse(message.shouldShowEmptyResponseError)
    }

    func testCompletedDurableRunRestoresSameRunAnswer() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionID = manager.createSession()
        manager.setMessages([
            ChatMessage(sessionId: sessionID, role: .user, content: "研究一人公司"),
            ChatMessage(
                id: "output", sessionId: sessionID, role: .assistant,
                content: "", runId: "run-existing"
            )
        ], for: sessionID)
        let fetched = expectation(description: "same durable run fetched")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { runID, _ in
                XCTAssertEqual(runID, "run-existing")
                fetched.fulfill()
                return DurableChatReplayDTO(
                    run: DurableChatRunDTO(
                        runId: runID, status: "completed", eventSequence: 92,
                        partialAnswer: nil, finalAnswer: "完整研究答案",
                        queuePosition: 0, attempt: 1, errorCode: "",
                        answerProjection: nil
                    ),
                    droppedEventCount: 0
                )
            }
        )

        XCTAssertTrue(coordinator.messages[1].needsDurableResultRecovery)
        coordinator.reconcileActiveRun()
        await fulfillment(of: [fetched], timeout: 1)
        for _ in 0..<20 where coordinator.messages[1].content.isEmpty { await Task.yield() }

        XCTAssertEqual(coordinator.messages[1].content, "完整研究答案")
        XCTAssertFalse(coordinator.messages[1].degraded)
    }

    func testDurableReplayRestoresKnowledgeActionCard() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionID = manager.createSession()
        manager.setMessages([
            ChatMessage(sessionId: sessionID, role: .user, content: "保存"),
            ChatMessage(
                id: "output", sessionId: sessionID, role: .assistant,
                content: "", runId: "run-save"
            )
        ], for: sessionID)
        let action = KnowledgeActionBlock(
            id: "action-save", summary: "保存复利笔记",
            steps: [.init(kind: "create_note", title: "复利", markdown: "# 复利")],
            actionDigest: "digest", transientCapability: "capability", expiresAt: 999
        )
        let fetched = expectation(description: "durable action fetched")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { _, _ in
                fetched.fulfill()
                return DurableChatReplayDTO(
                    run: DurableChatRunDTO(
                        runId: "run-save", status: "completed", eventSequence: 9,
                        partialAnswer: nil, finalAnswer: "等待确认",
                        queuePosition: 0, attempt: 1, errorCode: "",
                        answerProjection: nil
                    ),
                    droppedEventCount: 0,
                    events: [.knowledgeActionDraft(action)]
                )
            }
        )

        coordinator.reconcileActiveRun()
        await fulfillment(of: [fetched], timeout: 1)
        for _ in 0..<20 where !coordinator.messages[1].blocks.contains(where: {
            if case .knowledgeAction = $0 { return true }
            return false
        }) {
            await Task.yield()
        }

        let recovered = coordinator.messages[1].blocks.compactMap { block -> KnowledgeActionBlock? in
            if case .knowledgeAction(let action) = block { return action }
            return nil
        }.first
        XCTAssertEqual(recovered?.id, "action-save")
        XCTAssertEqual(recovered?.transientCapability, "capability")
    }

    func testDurableReplayDispatchesArtifactConsumptionBeforeAdvancingCursor() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionID = manager.createSession()
        manager.setMessages([
            ChatMessage(sessionId: sessionID, role: .user, content: "消费工件"),
            ChatMessage(
                id: "output", sessionId: sessionID, role: .assistant,
                content: "", runId: "run-consume", lastEventSequence: 3
            )
        ], for: sessionID)
        let fetched = expectation(description: "artifact event replayed")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { _, after in
                XCTAssertEqual(after, 3)
                fetched.fulfill()
                return DurableChatReplayDTO(
                    run: DurableChatRunDTO(
                        runId: "run-consume", status: "completed", eventSequence: 4,
                        partialAnswer: nil, finalAnswer: "已消费",
                        queuePosition: 0, attempt: 1, errorCode: "",
                        answerProjection: nil
                    ),
                    droppedEventCount: 0,
                    events: [.capability(QCPStreamEvent(
                        type: "artifact.consumed", version: 1,
                        payload: Data(#"{"structured_payload":{"value":"ok"},"receipt":{"receipt_id":"acr-1","artifact_id":"artifact-1","artifact_content_hash":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","schema_version":"json-schema-draft-2020-12-restricted","consumed_at":"2026-09-14T08:00:00Z","status":"completed"}}"#.utf8)
                    ))]
                )
            }
        )

        coordinator.reconcileActiveRun()
        await fulfillment(of: [fetched], timeout: 1)
        for _ in 0..<100 where coordinator.messages[1].lastEventSequence < 4 {
            try await Task.sleep(nanoseconds: 10_000_000)
        }

        let receipt = coordinator.messages[1].blocks.compactMap {
            if case .artifactConsumption(let value) = $0 { return value }
            return nil
        }.first
        XCTAssertEqual(receipt?.receiptId, "acr-1")
        XCTAssertNil(coordinator.toastMessage)
        XCTAssertEqual(coordinator.messages[1].lastEventSequence, 4)
        let persisted = try XCTUnwrap(manager.storedMessage(id: "output", sessionId: sessionID))
        XCTAssertTrue(persisted.blocks.contains {
            if case .artifactConsumption(let value) = $0 { return value.receiptId == "acr-1" }
            return false
        })
    }

    func testInvalidStatusArtifactReceiptDoesNotAdvanceCursorOrSettle() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionID = manager.createSession()
        manager.setMessages([
            ChatMessage(
                id: "output", sessionId: sessionID, role: .assistant,
                content: "", pending: true, runId: "run-invalid", lastEventSequence: 2
            )
        ], for: sessionID)
        await manager.flushPendingPersistence()

        let checkpointed = await manager.checkpointStatusEvents(
            [QCPStreamEvent(
                type: "artifact.consumed", version: 1,
                payload: Data(#"{"receipt":{"receipt_id":"missing-required-fields"}}"#.utf8),
                runId: "run-invalid", eventSequence: 3
            )],
            runId: "run-invalid", cursor: 3,
            sessionId: sessionID, messageId: "output"
        )

        XCTAssertFalse(checkpointed)
        let persisted = try XCTUnwrap(manager.storedMessage(id: "output", sessionId: sessionID))
        XCTAssertEqual(persisted.lastEventSequence, 2)
        XCTAssertTrue(persisted.pending)
        XCTAssertFalse(persisted.blocks.contains {
            if case .artifactConsumption = $0 { return true }; return false
        })
    }

    func testCompletedDurableRunFallsBackToFinalAnswerWhenProjectionIsEmpty() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionID = manager.createSession()
        manager.setMessages([
            ChatMessage(sessionId: sessionID, role: .user, content: "研究一人公司"),
            ChatMessage(
                id: "output", sessionId: sessionID, role: .assistant,
                content: "", runId: "run-existing"
            )
        ], for: sessionID)
        let fetched = expectation(description: "same durable run with empty projection fetched")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { runID, _ in
                XCTAssertEqual(runID, "run-existing")
                fetched.fulfill()
                return DurableChatReplayDTO(
                    run: DurableChatRunDTO(
                        runId: runID, status: "completed", eventSequence: 93,
                        partialAnswer: nil, finalAnswer: "完整研究答案",
                        queuePosition: 0, attempt: 1, errorCode: "",
                        answerProjection: AnswerBlockPageDTO(
                            messageId: "server-message", revision: 1, status: "completed",
                            blocks: [], bytes: 0, loadedBlockCount: 0,
                            availableBlockCount: 0, hasMore: false, nextCursor: nil
                        )
                    ),
                    droppedEventCount: 0
                )
            }
        )

        coordinator.reconcileActiveRun()
        await fulfillment(of: [fetched], timeout: 1)
        for _ in 0..<20 where coordinator.messages[1].content.isEmpty { await Task.yield() }

        XCTAssertEqual(coordinator.messages[1].content, "完整研究答案")
        XCTAssertFalse(coordinator.messages[1].degraded)
    }

    func testPreFirstSSEFrameCrashStatusRecoveryPersistsArtifactBeforeCursor() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionID = manager.createSession()
        manager.setMessages([
            ChatMessage(sessionId: sessionID, role: .user, content: "长回答"),
            ChatMessage(id: "output", sessionId: sessionID, role: .interrupted, content: "")
        ], for: sessionID)
        let pageJSON = Data(#"{"run_id":"run-recovered","message_id":"output","revision":1,"status":"completed","blocks":[{"block_index":0,"kind":"markdown","content":"第一页"}],"bytes":9,"loaded_block_count":1,"available_block_count":2,"has_more":true,"next_cursor":"page-2"}"#.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let recoveredPage = try decoder.decode(AnswerBlockPageDTO.self, from: pageJSON)
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchChatStatus: { _, consume, _, offset in
                XCTAssertEqual(offset, consume ? 8 : (offset == 0 ? 0 : 7))
                let isFirstPage = offset == 0
                return ChatStatusDTO(
                    status: "completed", phase: nil, answer: nil, reasoning: nil,
                    latestStep: nil, clarify: nil, consumed: consume,
                    answerProjection: recoveredPage, runId: "run-recovered",
                    eventSequence: 8, eventsNextOffset: isFirstPage ? 7 : 8,
                    events: isFirstPage ? [QCPStreamEvent(
                        type: "artifact.consumed", version: 1,
                        payload: Data(#"{"structured_payload":{"value":"ok"},"receipt":{"receipt_id":"acr-before-frame","artifact_id":"artifact-1","artifact_content_hash":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","schema_version":"json-schema-draft-2020-12-restricted","consumed_at":"2026-09-14T08:00:00Z","status":"completed"}}"#.utf8),
                        runId: "run-recovered", eventSequence: 7
                    )] : []
                )
            },
            fetchAnswerBlocks: { runId, cursor, _ in
                XCTAssertEqual(runId, "run-recovered")
                XCTAssertEqual(cursor, "page-2")
                return AnswerBlockPageDTO(
                    messageId: "output", revision: 1, status: "completed",
                    blocks: [.init(blockIndex: 1, kind: "markdown", content: "第二页")],
                    bytes: 9, loadedBlockCount: 2, availableBlockCount: 2,
                    hasMore: false, nextCursor: nil, runId: runId
                )
            }
        )

        coordinator.reconcileActiveRun()
        for _ in 0..<100 where coordinator.messages[1].lastEventSequence < 8
            || coordinator.messages[1].content.isEmpty {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        let fullAnswer = try await coordinator.fetchFullAnswer(messageId: "output")
        XCTAssertEqual(fullAnswer, "第一页第二页")
        XCTAssertEqual(coordinator.messages[1].lastEventSequence, 8)
        XCTAssertTrue(coordinator.messages[1].blocks.contains {
            if case .artifactConsumption(let receipt) = $0 {
                return receipt.receiptId == "acr-before-frame"
            }
            return false
        })
        let persisted = try XCTUnwrap(manager.storedMessage(id: "output", sessionId: sessionID))
        XCTAssertEqual(persisted.lastEventSequence, 8)
    }

    func testApplyCompletedStatusPreservesKnowledgeActionWhenAnswerIsEmpty() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionID = manager.createSession()
        let action = KnowledgeActionBlock(
            id: "action", summary: "保存研究", steps: [], actionDigest: "digest",
            transientCapability: nil, expiresAt: 0
        )
        manager.setMessages([
            ChatMessage(
                id: "output", sessionId: sessionID, role: .assistant,
                content: "", blocks: [.knowledgeAction(action)]
            )
        ], for: sessionID)

        manager.applyCompletedStatus(
            sessionId: sessionID, requestId: "output", answer: ""
        )

        let recovered = try XCTUnwrap(manager.messages(for: sessionID).first)
        XCTAssertTrue(recovered.blocks.contains {
            if case .knowledgeAction(let preserved) = $0 { return preserved.id == action.id }
            return false
        })
        XCTAssertTrue(recovered.hasRenderableAssistantResult)
        XCTAssertFalse(recovered.shouldShowEmptyResponseError)
    }

    func testTrueEmptyCompletedRunBecomesAccurateTerminalFailure() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionID = manager.createSession()
        manager.setMessages([
            ChatMessage(sessionId: sessionID, role: .user, content: "空结果"),
            ChatMessage(
                id: "output", sessionId: sessionID, role: .assistant,
                content: "", runId: "run-empty"
            )
        ], for: sessionID)
        let fetched = expectation(description: "empty terminal fetched")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchDurableChatRun: { runID, _ in
                fetched.fulfill()
                return DurableChatReplayDTO(
                    run: DurableChatRunDTO(
                        runId: runID, status: "completed", eventSequence: 1,
                        partialAnswer: nil, finalAnswer: nil, queuePosition: 0,
                        attempt: 1, errorCode: "", answerProjection: nil
                    ),
                    droppedEventCount: 0
                )
            }
        )

        coordinator.reconcileActiveRun()
        await fulfillment(of: [fetched], timeout: 1)
        for _ in 0..<20 where !coordinator.messages[1].degraded { await Task.yield() }

        XCTAssertTrue(coordinator.messages[1].degraded)
        XCTAssertEqual(coordinator.messages[1].content, "任务已完成，但未返回正文或可显示结果")
        XCTAssertFalse(coordinator.messages[1].needsDurableResultRecovery)
    }

    func testLegacyClarifyContinuationRecoversMissingRunId() {
        let clarify = ClarifyBlock(
            requestId: "request-1", sessionId: "session-1",
            submissionState: .accepted, question: "选择路线", choices: ["省钱"],
            source: "bridge", isSubmitted: true, submittedSelection: "省钱"
        )
        var messages = [
            ChatMessage(
                id: "clarify", sessionId: "session-1", role: .assistant,
                content: "", blocks: [.clarify(clarify)], runId: "durable-run",
                lastEventSequence: 4
            ),
            ChatMessage(
                id: "answer", sessionId: "session-1", role: .assistant,
                content: "首批正文", answerRevision: 2,
                answerNextCursor: "signed-cursor", answerHasMore: true,
                answerAvailableBlockCount: 40,
                answerBlocks: [AnswerBlockDTO(
                    blockIndex: 0, kind: "markdown", content: "首批正文"
                )]
            )
        ]

        let repaired = TenantSessionCoordinator.repairClarifyContinuationRunLinks(
            in: &messages
        )

        XCTAssertEqual(repaired, 1)
        XCTAssertEqual(messages[1].runId, "durable-run")
        XCTAssertEqual(messages[1].lastEventSequence, 4)
    }

    func testRunRepairNeverLinksUnrelatedOrCompleteAnswers() {
        let clarify = ClarifyBlock(
            sessionId: "session-1", submissionState: .accepted,
            question: "选择路线", choices: ["省钱"], source: "bridge",
            isSubmitted: true, submittedSelection: "省钱"
        )
        var messages = [
            ChatMessage(
                sessionId: "session-1", role: .assistant, content: "",
                blocks: [.clarify(clarify)], runId: "durable-run"
            ),
            ChatMessage(sessionId: "session-1", role: .user, content: "新问题"),
            ChatMessage(
                sessionId: "session-1", role: .assistant, content: "独立回答",
                answerNextCursor: "cursor", answerHasMore: true
            ),
            ChatMessage(
                sessionId: "session-1", role: .assistant, content: "完整回答",
                answerHasMore: false
            )
        ]

        let repaired = TenantSessionCoordinator.repairClarifyContinuationRunLinks(
            in: &messages
        )

        XCTAssertEqual(repaired, 0)
        XCTAssertNil(messages[2].runId)
        XCTAssertNil(messages[3].runId)
    }

    func testLegacyClarifyContinuationCanFetchRemainingAnswer() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let manager = SessionManager(store: try ChatHistoryStore(
            databaseURL: root.appendingPathComponent("history.sqlite"),
            legacyDirectory: root.appendingPathComponent("legacy"),
            performLegacyMigration: false
        ))
        let sessionID = manager.createSession()
        let clarify = ClarifyBlock(
            requestId: "request-1", sessionId: sessionID,
            submissionState: .accepted, question: "选择路线", choices: ["省钱"],
            source: "bridge", isSubmitted: true, submittedSelection: "省钱"
        )
        manager.setMessages([
            ChatMessage(
                id: "clarify", sessionId: sessionID, role: .assistant,
                content: "", blocks: [.clarify(clarify)], runId: "durable-run"
            ),
            ChatMessage(
                id: "answer", sessionId: sessionID, role: .assistant,
                content: "第1页", answerRevision: 2,
                answerNextCursor: "page-2", answerHasMore: true,
                answerAvailableBlockCount: 2,
                answerBlocks: [AnswerBlockDTO(
                    blockIndex: 0, kind: "markdown", content: "第1页"
                )]
            )
        ], for: sessionID)
        let fetched = expectation(description: "remaining page fetched with inherited run")
        let coordinator = TenantSessionCoordinator(
            sessionManager: manager,
            hasAuthenticatedSession: { true },
            fetchAnswerBlocks: { runID, cursor, maxBlocks in
                XCTAssertEqual(runID, "durable-run")
                XCTAssertEqual(cursor, "page-2")
                XCTAssertEqual(maxBlocks, 20)
                fetched.fulfill()
                return AnswerBlockPageDTO(
                    messageId: "server-answer", revision: 2, status: "completed",
                    blocks: [AnswerBlockDTO(
                        blockIndex: 1, kind: "markdown", content: "第2页"
                    )], bytes: 7, loadedBlockCount: 2,
                    availableBlockCount: 2, hasMore: false, nextCursor: nil
                )
            }
        )

        let fullAnswer = try await coordinator.fetchFullAnswer(messageId: "answer")
        await fulfillment(of: [fetched], timeout: 1)

        XCTAssertEqual(fullAnswer, "第1页第2页")
        XCTAssertEqual(coordinator.messages[1].runId, "durable-run")
        XCTAssertFalse(coordinator.messages[1].answerHasMore)
        XCTAssertNil(coordinator.messages[1].answerNextCursor)
    }
}
