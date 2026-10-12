import XCTest

final class TravelSpaceUITests: XCTestCase {
    @MainActor @objc func testAuthenticatedAomoriExistingPages() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["QUANTUM_TRAVEL_LIVE_ACCEPTANCE"] == "1")
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-workflowTab", "-travelLiveEvidence"]
        let target = ProcessInfo.processInfo.environment["QUANTUM_TRAVEL_WORKFLOW_ID"]
        if let target { app.launchArguments += ["-travelLiveWorkflowID", target] }
        app.launch()
        XCTAssertTrue(app.buttons["main-tab-1"].waitForExistence(timeout: 30))
        app.buttons["main-tab-1"].tap()
        if target != nil {
            let retainedDraft = app.webViews.buttons["查看任务与已完成内容"].firstMatch
            if retainedDraft.waitForExistence(timeout: 20) {
                XCTAssertTrue(app.webViews.buttons["采用这份行程"].firstMatch.exists)
                XCTAssertFalse(app.webViews.buttons["采用这份行程"].firstMatch.isEnabled)
                let draft = XCTAttachment(screenshot: app.screenshot())
                draft.name = "authenticated-five-day-draft-retained-adoption-disabled"; draft.lifetime = .keepAlways; add(draft)
                retainedDraft.tap()
                XCTAssertTrue(app.webViews.staticTexts["ALONG THE WAY"].waitForExistence(timeout: 15))
                let failure = XCTAttachment(screenshot: app.screenshot())
                failure.name = "authenticated-notebook-size-failure-current-task-details"; failure.lifetime = .keepAlways; add(failure)
                return
            }
            XCTAssertTrue(app.webViews.buttons["重新整理计划"].firstMatch.waitForExistence(timeout: 20))
            let evidence = XCTAttachment(screenshot: app.screenshot())
            evidence.name = "authenticated-exact-aomori-planning-failure"; evidence.lifetime = .keepAlways; add(evidence)
            let tree = XCTAttachment(string: app.debugDescription)
            tree.name = "authenticated-exact-aomori-planning-accessibility"; tree.lifetime = .keepAlways; add(tree)
            return
        }
        let library = app.webViews.buttons["全部任务"].firstMatch
        XCTAssertTrue(library.waitForExistence(timeout: 30)); library.tap()
        XCTAssertTrue(app.webViews.staticTexts["YOUR IDEAS, KEPT"].waitForExistence(timeout: 15))
        func capture(_ name: String) {
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = name; image.lifetime = .keepAlways; add(image)
            let tree = XCTAttachment(string: app.debugDescription)
            tree.name = name + "-accessibility"; tree.lifetime = .keepAlways; add(tree)
        }
        capture("authenticated-current-task-library")
        let task = app.webViews.buttons.matching(NSPredicate(format: "label CONTAINS %@", "青森 · 旅行计划")).firstMatch
        XCTAssertTrue(task.waitForExistence(timeout: 20)); task.tap()
        XCTAssertFalse(app.buttons["协同拓扑"].exists)
        let planning = app.webViews.buttons["重新整理计划"].firstMatch
        if planning.waitForExistence(timeout: 10) {
            capture("authenticated-current-aomori-planning-failure")
            return
        }
        XCTAssertTrue(app.webViews.staticTexts["ALONG THE WAY"].waitForExistence(timeout: 30))
        XCTAssertTrue(app.webViews.buttons["从失败步骤继续"].exists)
        capture("authenticated-current-aomori-failure")
        let artifact = app.webViews.buttons.matching(NSPredicate(format: "label CONTAINS %@", "核对落地、住宿、交通与餐饮 MD")).firstMatch
        XCTAssertTrue(artifact.exists)
        for _ in 0..<8 where !artifact.isHittable { app.webViews.firstMatch.swipeUp() }
        XCTAssertTrue(artifact.isHittable); artifact.tap()
        XCTAssertTrue(app.webViews.buttons["关闭成果预览"].waitForExistence(timeout: 30))
        capture("authenticated-current-research-preview")
        // This is read-only page acceptance, not a successful full journey.
        app.webViews.buttons["关闭成果预览"].tap()
    }

    @MainActor @objc func testAomoriLiveWorkflow() throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["QUANTUM_TRAVEL_LIVE_ACCEPTANCE"] == "1",
            "Live server writes require an explicitly selected acceptance run."
        )
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-workflowTab", "-travelLiveEvidence"]
        let target = ProcessInfo.processInfo.environment["QUANTUM_TRAVEL_WORKFLOW_ID"]
        if let target { app.launchArguments += ["-travelLiveWorkflowID", target] }
        app.launch()
        func capture(_ name: String) {
            print("AOMORI_STEP: \(name)")
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "aomori-" + name; image.lifetime = .keepAlways; add(image)
            let tree = XCTAttachment(string: app.debugDescription)
            tree.name = "aomori-" + name + "-accessibility"; tree.lifetime = .keepAlways; add(tree)
            if let path = ProcessInfo.processInfo.environment["QUANTUM_TRAVEL_CONTROL_FILE"] {
                let folder = URL(fileURLWithPath: path).deletingLastPathComponent()
                try? app.screenshot().pngRepresentation.write(to: folder.appendingPathComponent("live-screen.png"), options: .atomic)
                try? app.debugDescription.write(to: folder.appendingPathComponent("live-accessibility.txt"), atomically: true, encoding: .utf8)
            }
        }
        func foreground() -> XCUIElement {
            let dialog = app.webViews.otherElements.matching(NSPredicate(format: "label ENDSWITH %@", "网页对话框")).allElementsBoundByIndex.last
            return dialog ?? app
        }
        func tap(_ label: String, timeout: TimeInterval = 15) {
            let surface = label.hasPrefix("main-tab-") ? app : foreground()
            // A receipt can replace its button between observation and capture.
            // Let the loop read the next foreground state instead of tapping a stale control.
            guard surface.buttons[label].firstMatch.waitForExistence(timeout: timeout) else {
                print("AOMORI_TRANSITION: control replaced: \(label)")
                return
            }
            let button = surface.buttons.matching(identifier: label).allElementsBoundByIndex.last ?? surface.buttons[label].firstMatch
            for _ in 0..<12 where !button.isHittable {
                let web = app.webViews.firstMatch
                let surface = web.exists ? web : app
                if button.frame.midY < surface.frame.minY + 24 { surface.swipeDown() }
                else { surface.swipeUp() }
            }
            XCTAssertTrue(button.isHittable, "Not hittable: \(label)")
            button.tap()
        }
        func available(_ label: String) -> Bool {
            let button = foreground().buttons[label].firstMatch
            return button.exists && button.isEnabled
        }
        guard !app.buttons["手机号登录"].waitForExistence(timeout: 3),
              app.buttons["main-tab-1"].waitForExistence(timeout: 30) else {
            capture("authenticated-session-missing")
            XCTFail("已登录的验收会话不可用；不以开发者账号或预览替代真实登录。")
            return
        }
        if app.buttons["agreement.cta"].exists { tap("agreement.cta") }
        tap("main-tab-1")
        let newTask = app.webViews.buttons["新建任务"].firstMatch
        if target == nil { XCTAssertTrue(newTask.waitForExistence(timeout: 30)) }
        capture("authenticated-workflow")
        let existing = app.webViews.buttons.matching(NSPredicate(format: "label CONTAINS %@", "青森 · 旅行计划")).firstMatch
        if target != nil {
            RunLoop.current.run(until: Date().addingTimeInterval(4))
            capture("resumed-exact-server-state")
        } else if existing.exists && ProcessInfo.processInfo.environment["QUANTUM_TRAVEL_CREATE_NEW"] != "1" {
            existing.tap()
            RunLoop.current.run(until: Date().addingTimeInterval(3))
            capture("resumed-server-state")
            XCTAssertFalse(app.buttons["协同拓扑"].exists, "Workflow must stay in the reviewed renderer")
        } else {
            newTask.tap()
            let input = app.webViews.textViews["旅行想法"].firstMatch
            XCTAssertTrue(input.waitForExistence(timeout: 20))
            input.tap(); input.typeText("我要去青森")
            capture("initial-request")
            tap("发送旅行想法")
            RunLoop.current.run(until: Date().addingTimeInterval(2))
            XCTAssertTrue(input.waitForExistence(timeout: 180), "等待已登录服务端返回旅行追问")
            input.tap(); input.typeText("模拟器验收条件：从上海出发，5天，2人，人均预算8000元人民币，公共交通，轻松，喜欢自然风光、当地美食和温泉。日期未定，不要编造已确认的机票、库存、班次或开放日期。需要逐日行程、交通接驳、住宿区域、餐饮、预算、入境及行前清单、季节备选方案、来源和待核对事项。")
            tap("发送旅行想法")
            capture("requirements")
        }
        var answers = 0, approvals = 0, retries = 0, planningRetries = 0
        var lastCommand: String?
        let controlPath = ProcessInfo.processInfo.environment["QUANTUM_TRAVEL_CONTROL_FILE"]
        let deadline = Date().addingTimeInterval(900)
        while Date() < deadline {
            if let controlPath,
               let data = try? Data(contentsOf: URL(fileURLWithPath: controlPath)),
               let command = (try? JSONSerialization.jsonObject(with: data)) as? [String: String],
               let id = command["id"], id != lastCommand {
                lastCommand = id
                if command["operation"] == "tap", let label = command["label"] { tap(label) }
                if command["operation"] == "scrollUp" { app.webViews.firstMatch.swipeUp() }
                if command["operation"] == "scrollDown" { app.webViews.firstMatch.swipeDown() }
                capture("checkpoint-" + id)
            }
            if available("打开这趟旅行") {
                capture("adopted-notebook")
                RunLoop.current.run(until: Date().addingTimeInterval(2))
                XCTAssertTrue(app.webViews.staticTexts["已保存到笔记"].waitForExistence(timeout: 40),
                              "手记必须收到并回读真实保存回执，不能只凭本地页面跳转通过。")
                tap("打开这趟旅行")
                XCTAssertTrue(app.webViews.buttons["开始这趟旅行"].waitForExistence(timeout: 20))
                capture("ten-step-before-trip")
                return
            }
            if available("保存为旅行手记") {
                capture("adopted-guide")
                XCTAssertTrue(app.webViews.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "青森")).firstMatch.exists)
                tap("保存为旅行手记")
            } else if available("生成我的旅行手记") {
                capture("save-notebook"); tap("生成我的旅行手记")
            }
            let clarification = app.webViews.textViews["回答旅行澄清问题"].firstMatch
            if clarification.exists && available("确认回答") {
                answers += 1; XCTAssertLessThanOrEqual(answers, 8)
                capture("server-question-\(answers)")
                clarification.tap()
                if let value = clarification.value as? String, !value.isEmpty {
                    clarification.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: value.count))
                }
                clarification.typeText("确认验收需求：目的地日本青森县，上海出发，5天2人，人均预算8000元人民币，公共交通，轻松自然、美食和温泉。日期未定，请保留季节和日期限制，给出逐日安排、接驳、住宿区域、餐饮、预算、行前准备、替代方案以及来源，不进行购票或商户预订。")
                tap("确认回答")
                RunLoop.current.run(until: Date().addingTimeInterval(4))
            } else if clarification.exists && app.buttons["确认旅行需求"].exists {
                capture("confirm-server-requirements")
                if let value = clarification.value as? String, value.isEmpty {
                    if app.buttons["确认，开始制作攻略"].exists { tap("确认，开始制作攻略") }
                    else { clarification.tap(); clarification.typeText("确认，按上海出发、5天2人、人均8000元、公共交通和日期未定制作青森攻略。") }
                }
                if available("确认旅行需求") { tap("确认旅行需求") }
                RunLoop.current.run(until: Date().addingTimeInterval(4))
            } else if available("重新整理计划") && planningRetries < 1 {
                planningRetries += 1
                capture("planning-failure-before-retry"); tap("重新整理计划")
                RunLoop.current.run(until: Date().addingTimeInterval(4))
            } else if available("重新整理计划") {
                capture("planning-failure-after-retry")
                XCTFail("当前青森计划的同任务重试仍失败；保留具体服务端错误，不继续重复提交。")
                return
            } else if available("确认旅行计划") {
                capture("travel-plan"); tap("确认旅行计划")
            } else if available("进入交通与预订") {
                capture("enter-transport"); tap("进入交通与预订")
            } else if app.webViews.otherElements["往返规划, 网页对话框"].exists {
                capture("transport-unknown-dates"); tap("关闭")
            } else if available("开始制作行程") {
                if app.webViews.buttons["关闭"].exists { tap("关闭") }
                capture("transport"); tap("开始制作行程")
            } else if available("查看任务与已完成内容") {
                capture("generation-failure"); tap("查看任务与已完成内容")
            } else if available("从失败步骤继续") && retries < 1 {
                if app.webViews.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "分块策划预算已耗尽")).firstMatch.exists {
                    capture("server-chunk-budget-exhausted")
                    XCTFail("服务端分块策划预算耗尽；现有重试接口不能调整该预算，保留成果和失败回执。")
                    return
                }
                retries += 1
                capture("failed-step-before-retry"); tap("从失败步骤继续")
                RunLoop.current.run(until: Date().addingTimeInterval(8))
                capture("failed-step-retry-receipt")
            } else if available("采用这份行程") {
                approvals += 1; XCTAssertLessThanOrEqual(approvals, 5)
                capture("review-draft-\(approvals)"); tap("采用这份行程")
                RunLoop.current.run(until: Date().addingTimeInterval(8))
            } else if available("查看成稿") {
                capture("generated"); tap("查看成稿")
            } else if available("完善旅行计划") {
                capture("place-folder"); tap("完善旅行计划")
            } else if available("确认完善计划") {
                capture("preferences"); tap("确认完善计划")
            } else if available("确定") {
                capture("discovery"); tap("确定")
            } else if !clarification.exists && available("确认旅行需求") {
                capture("converged-requirements"); tap("确认旅行需求")
            } else if let proceed = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "继续生成")).allElementsBoundByIndex.first(where: { $0.isHittable && $0.isEnabled }) {
                proceed.tap()
            }
            RunLoop.current.run(until: Date().addingTimeInterval(2))
        }
        capture("timeout")
        XCTFail("青森完整流程未在十五分钟内到达采用后的攻略。")
    }

    @MainActor func testProductionRendererAndNativeLiquidNavigation() throws {
        let app = XCUIApplication()
        app.launchArguments = ["-travelSpacePreview"]
        app.launch()
        let create = app.webViews.buttons["新建任务"]
        XCTAssertTrue(create.waitForExistence(timeout: 30), app.debugDescription)
        XCTAssertFalse(app.webViews.staticTexts["9:41"].exists)
        XCTAssertFalse(app.webViews.buttons["评审：悬浮对话"].exists)
        let web = app.webViews.firstMatch
        XCTAssertGreaterThan(web.frame.width, 300)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "native-travel-space-production-entry"; screenshot.lifetime = .keepAlways; add(screenshot)
        app.webViews.buttons["全部任务"].tap()
        XCTAssertTrue(app.webViews.staticTexts["YOUR IDEAS, KEPT"].waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertFalse(app.buttons["协同拓扑"].exists)
        let libraryImage = XCTAttachment(screenshot: app.screenshot())
        libraryImage.name = "native-current-task-library"; libraryImage.lifetime = .keepAlways; add(libraryImage)
        app.webViews.buttons["关闭"].firstMatch.tap()
        app.webViews.buttons["照片处理"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["ROOM FOR YOUR PHOTOS"].waitForExistence(timeout: 15), app.debugDescription)
        let photoImage = XCTAttachment(screenshot: app.screenshot())
        photoImage.name = "native-current-photo-entry"; photoImage.lifetime = .keepAlways; add(photoImage)
        app.buttons["关闭照片处理"].firstMatch.tap()
        XCTAssertTrue(create.waitForExistence(timeout: 15))
        for tag in [2, 3, 0, 1] {
            let tab = app.buttons["main-tab-\(tag)"]
            XCTAssertTrue(tab.isHittable)
            tab.tap()
            switch tag {
            case 2: XCTAssertTrue(app.staticTexts["YOUR WORDS, KEPT"].waitForExistence(timeout: 15), app.debugDescription)
            case 3: XCTAssertTrue(app.staticTexts["YOUR SPACE, AT YOUR PACE"].waitForExistence(timeout: 15), app.debugDescription)
            case 0: XCTAssertTrue(app.staticTexts["QUANTUM · YOUR EVERYDAY SPACE"].waitForExistence(timeout: 15), app.debugDescription)
            default: XCTAssertTrue(create.waitForExistence(timeout: 15), app.debugDescription)
            }
            // Capture settled capsules and content rather than the transition frame.
            RunLoop.current.run(until: Date().addingTimeInterval(0.7))
            if tag == 0 {
                XCTAssertTrue(app.staticTexts["把片刻的风景，留给下一次出发。"].isHittable,
                              "The magazine caption must remain inside the visible photo crop")
            }
            let tabImage = XCTAttachment(screenshot: app.screenshot())
            tabImage.name = "native-front-end-tab-\(tag)"; tabImage.lifetime = .keepAlways; add(tabImage)
        }
        XCTAssertTrue(create.waitForExistence(timeout: 15))
        create.tap()
        XCTAssertTrue(app.webViews.buttons["返回"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.webViews.textFields["旅行想法"].waitForExistence(timeout: 15)
                      || app.webViews.textViews["旅行想法"].waitForExistence(timeout: 5), app.debugDescription)
    }
}
