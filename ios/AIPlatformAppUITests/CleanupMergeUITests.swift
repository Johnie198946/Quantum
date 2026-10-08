import XCTest

final class CleanupMergeUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func scrollContent(_ app: XCUIApplication) {
        let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.6))
        start.press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.3)))
    }

    func testDifferencesAreVisibleAndUnreviewedMergeCannotBeAccepted() {
        let app = XCUIApplication()
        app.launchArguments = ["-cleanupMergePreview"]
        app.launch()
        let accept = app.buttons["cleanup-accept-merge"]
        XCTAssertTrue(accept.waitForExistence(timeout: 10))
        XCTAssertFalse(accept.isEnabled)
        XCTAssertTrue(app.staticTexts["不同表述 · 请选择"].exists)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "cleanup-differences-first-screen"
        screenshot.lifetime = .keepAlways
        add(screenshot)
        let choice = app.buttons["cleanup-choice-1-source"]
        for _ in 0..<8 where !choice.isHittable || choice.frame.midY >= min(accept.frame.minY, app.frame.maxY - 80) { scrollContent(app) }
        XCTAssertTrue(choice.isHittable)
        choice.tap()
        XCTAssertTrue(accept.isEnabled)
        accept.tap()
        XCTAssertTrue(app.staticTexts["cleanup-preview-accepted"].waitForExistence(timeout: 3))
    }

    func testLargeTypeKeepsChoiceAndActionAccessible() {
        let app = XCUIApplication()
        app.launchArguments = ["-cleanupMergePreview", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        let accept = app.buttons["cleanup-accept-merge"]
        XCTAssertTrue(accept.waitForExistence(timeout: 10))
        let choice = app.buttons["cleanup-choice-1-both"]
        for _ in 0..<20 where !choice.isHittable || choice.frame.midY >= min(accept.frame.minY, app.frame.maxY - 80) { scrollContent(app) }
        XCTAssertTrue(choice.isHittable)
        choice.tap()
        for _ in 0..<12 where !accept.isHittable { scrollContent(app) }
        XCTAssertTrue(accept.isHittable)
        XCTAssertTrue(accept.isEnabled)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "cleanup-large-type"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }
}

@MainActor
final class TravelFlowUITests: XCTestCase {
    private let app = XCUIApplication()
    private func tapVisible(_ element: XCUIElement) {
        _ = element.waitForExistence(timeout: 3)
        for _ in 0..<12 {
            if element.exists && element.isHittable { break }
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.96, dy: 0.55))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.96, dy: 0.20)))
        }
        XCTAssertTrue(element.isHittable, app.debugDescription)
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: element)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 30), .completed, app.debugDescription)
        element.tap()
    }
    private func launchTravel() throws {
        let env = ProcessInfo.processInfo.environment
        app.launchArguments = ["-tabBarPreview", "-workflowTab"]
        app.launchEnvironment["AI_LAB_E2E_BASE_URL"] = "http://127.0.0.1:8846"
        app.launchEnvironment["AI_LAB_E2E_TOKEN"] = try XCTUnwrap(env["TRAVEL_E2E_TOKEN"])
        app.launchEnvironment["AI_LAB_E2E_DISABLE_ANIMATIONS"] = "1"
        app.launch()
        tapVisible(app.buttons["workflow-card-旅行客户端验收"])
        tapVisible(app.buttons["workflow-artifact-preview-" + (try XCTUnwrap(env["TRAVEL_E2E_ARTIFACT"]))])
        tapVisible(app.buttons["查看完整行程  →"])
    }
    private func cloudTitle() async throws -> String? {
        func get(_ path: String) async throws -> Any {
            var request = URLRequest(url: URL(string: "http://127.0.0.1:8846/api/v1/" + path)!)
            request.setValue("Bearer " + (ProcessInfo.processInfo.environment["TRAVEL_E2E_TOKEN"] ?? ""), forHTTPHeaderField: "Authorization")
            let (data, response) = try await URLSession.shared.data(for: request)
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
            return try JSONSerialization.jsonObject(with: data)
        }
        let path = "workflow-executions/client-travel-execution/artifacts"
        let artifacts = try await get(path) as! [[String: Any]]
        let latest = artifacts.max {
            (($0["metadata"] as? [String: Any])?["travel_revision"] as? Int ?? 0) < (($1["metadata"] as? [String: Any])?["travel_revision"] as? Int ?? 0)
        }!
        let result = try await get(path + "/" + (latest["id"] as! String) + "/content") as! [String: Any]
        let document = try JSONSerialization.jsonObject(with: Data((result["content"] as! String).utf8)) as! [String: Any]
        return (document["actions"] as? [[String: Any]])?.first?["title"] as? String
    }
    private func editTravel(title newTitle: String, reason why: String) {
        tapVisible(app.buttons["调整这个安排"].firstMatch)
        let title = app.textFields["事项名称"]
        XCTAssertTrue(title.waitForExistence(timeout: 5))
        title.tap()
        let old = title.value as? String ?? ""
        title.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count) + newTitle)
        let reason = app.descendants(matching: .any).matching(NSPredicate(format: "placeholderValue == %@", "例如：下雨，下午改在旅馆休息")).firstMatch
        tapVisible(reason)
        reason.typeText(why)
        tapVisible(app.buttons["保存为新版本"])
        XCTAssertTrue(app.staticTexts[newTitle].waitForExistence(timeout: 15), app.debugDescription)
    }
    private func setNetwork(_ online: Bool) async throws {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8846/__acceptance/network/" + (online ? "online" : "offline"))!)
        request.httpMethod = "POST"
        let (_, response) = try await URLSession.shared.data(for: request)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
    }
    func testFullClientJourneyWithStageWaits() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        app.launchArguments = ["-tabBarPreview", "-workflowTab"]
        app.launchEnvironment["AI_LAB_E2E_BASE_URL"] = "http://127.0.0.1:8847"
        app.launchEnvironment["AI_LAB_E2E_TOKEN"] = try XCTUnwrap(env["TRAVEL_FULL_E2E_TOKEN"])
        app.launchEnvironment["AI_LAB_E2E_DISABLE_ANIMATIONS"] = "1"
        app.launch()
        tapVisible(app.buttons["创建第一个工作流"])
        let goal = app.descendants(matching: .any).matching(NSPredicate(format: "placeholderValue == %@", "例如：写一篇关于人工智能的课程论文…")).firstMatch
        tapVisible(goal)
        goal.typeText("Client full journey. 2030年1月3日日本一日安静温泉旅行，仅查日本秘汤守护协会官网，一个候选区域、最多三个事项，留两小时休息。未知留空，不预约。")
        tapVisible(app.buttons["旅行计划"])
        tapVisible(app.buttons["生成计划"])
        let questions = ["从哪里出发？大致什么时候、几天？还没决定也可以直接说。", "最想体验什么、想避开什么？可以自由回答或补充资料。", "同行人数、预算和交通偏好是什么？哪些条件必须保留？"]
        let answers = ["一人，2030年1月3日，日本", "小众温泉和放空，不去人多的地方", "只查官方网页，最多3个安排，不预约"]
        for (question, answer) in zip(questions, answers) {
            XCTAssertTrue(app.staticTexts[question].waitForExistence(timeout: 30), app.debugDescription)
            let input = app.descendants(matching: .any)["clarify-custom-input"]
            for _ in 0..<12 {
                if input.exists && input.frame.maxY < app.frame.maxY - 150 { break }
                app.coordinate(withNormalizedOffset: CGVector(dx: 0.96, dy: 0.55))
                    .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.96, dy: 0.25)))
            }
            tapVisible(input); input.typeText(answer)
            let keyboardAction = app.buttons["clarify-keyboard-primary-action"]
            tapVisible(keyboardAction.exists ? keyboardAction : app.buttons["clarify-primary-action"])
        }
        tapVisible(app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "内容准确")).firstMatch)
        let confirm = app.buttons["requirement-confirm-primary-action"]
        for _ in 0..<8 {
            if confirm.exists && confirm.frame.maxY < app.frame.maxY - 160 { break }
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.96, dy: 0.55))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.96, dy: 0.25)))
        }
        XCTAssertEqual(confirm.label, "确认并生成方案")
        tapVisible(confirm)
        XCTAssertTrue(app.buttons["查看并确认方案"].waitForExistence(timeout: 90), app.debugDescription)
        tapVisible(app.buttons["查看并确认方案"])
        tapVisible(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "workflow-card-Client full journey")).firstMatch)
        tapVisible(app.buttons["确认并构建 Agent"])
        XCTAssertTrue(app.buttons["启动任务"].waitForExistence(timeout: 60), app.debugDescription)
        tapVisible(app.buttons["启动任务"])
        XCTAssertTrue(app.buttons["确认行程"].waitForExistence(timeout: 240), app.debugDescription)
        tapVisible(app.buttons["确认行程"])
        XCTAssertTrue(app.buttons["采用这份行程"].waitForExistence(timeout: 180), app.debugDescription)
        tapVisible(app.buttons["采用这份行程"])
        XCTAssertTrue(app.buttons["查看完整行程  →"].waitForExistence(timeout: 30), app.debugDescription)
        tapVisible(app.buttons["查看完整行程  →"])
        XCTAssertTrue(app.buttons["第 1 天"].waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(app.buttons["现在开始"].firstMatch.exists, app.debugDescription)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "travel-real-model-client-notebook"; screenshot.lifetime = .keepAlways; add(screenshot)
    }
    func testSavedRealNotebookSurvivesRelaunch() throws {
        continueAfterFailure = false
        app.launchArguments = ["-tabBarPreview", "-workflowTab"]
        app.launchEnvironment["AI_LAB_E2E_BASE_URL"] = "http://127.0.0.1:8847"
        app.launchEnvironment["AI_LAB_E2E_TOKEN"] = try XCTUnwrap(ProcessInfo.processInfo.environment["TRAVEL_FULL_E2E_TOKEN"])
        app.launchEnvironment["AI_LAB_E2E_DISABLE_ANIMATIONS"] = "1"
        app.launch()
        tapVisible(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "workflow-card-Client full journey")).firstMatch)
        tapVisible(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "workflow-artifact-preview-")).firstMatch)
        tapVisible(app.buttons["生成旅行笔记"])
        let noteTitle = "Client accepted trip " + UUID().uuidString.prefix(8)
        let titleField = app.textFields["travel-note-title"]
        tapVisible(titleField)
        if !app.keyboards.firstMatch.waitForExistence(timeout: 2) {
            titleField.coordinate(withNormalizedOffset: CGVector(dx: 0.15, dy: 0.5)).tap()
        }
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5), app.debugDescription)
        titleField.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: (titleField.value as? String ?? "").count) + noteTitle)
        tapVisible(app.buttons["生成我的旅行手记"])
        XCTAssertTrue(app.buttons["travel-note-open-diary"].waitForExistence(timeout: 15), app.debugDescription)
        app.terminate(); app.launch()
        tapVisible(app.buttons["main-tab-2"])
        let search = app.textFields["note-search"]
        tapVisible(search); search.typeText(noteTitle)
        tapVisible(app.staticTexts[noteTitle].firstMatch)
        XCTAssertTrue(app.buttons["travel-note-open-diary"].waitForExistence(timeout: 15), app.debugDescription)
        let saved = XCTAttachment(screenshot: app.screenshot())
        saved.name = "travel-saved-note-after-relaunch"; saved.lifetime = .keepAlways; add(saved)
    }
    func testOfflineEditSurvivesTerminationAndSynchronizes() async throws {
        continueAfterFailure = false
        try await setNetwork(true)
        addTeardownBlock { [self] in try await setNetwork(true) }
        try launchTravel()
        try await setNetwork(false)
        editTravel(title: "Offline retained", reason: "Offline client acceptance")
        app.terminate()
        try launchTravel()
        XCTAssertTrue(app.staticTexts["Offline retained"].waitForExistence(timeout: 10), app.debugDescription)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "travel-offline-relaunch"; screenshot.lifetime = .keepAlways; add(screenshot)
        try await setNetwork(true)
        tapVisible(app.buttons["立即同步"])
        for _ in 0..<20 {
            if try await cloudTitle() == "Offline retained" { break }
            try await Task.sleep(for: .milliseconds(250))
        }
        let saved = try await cloudTitle()
        XCTAssertEqual(saved, "Offline retained")
        app.terminate()
        try launchTravel()
        XCTAssertTrue(app.staticTexts["Offline retained"].waitForExistence(timeout: 10))
    }
    func testTenTravelEditsSurviveRelaunch() async throws {
        continueAfterFailure = false
        try launchTravel()
        for index in 1...10 {
            editTravel(title: "Travel edit \(index)", reason: "Client round \(index)")
            let persistedTitle = try await cloudTitle()
            XCTAssertEqual(persistedTitle, "Travel edit \(index)")
        }
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "travel-ten-edits"; screenshot.lifetime = .keepAlways; add(screenshot)
        app.terminate()
        try launchTravel()
        XCTAssertTrue(app.staticTexts["Travel edit 10"].waitForExistence(timeout: 10))
        tapVisible(app.buttons["旧版本"])
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Client round")).firstMatch.waitForExistence(timeout: 10), app.debugDescription)
    }
}
