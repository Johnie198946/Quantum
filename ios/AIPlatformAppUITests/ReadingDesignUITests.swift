import XCTest

final class ReadingDesignUITests: XCTestCase {
    private let app = XCUIApplication(bundleIdentifier: "com.ailab.AIPlatformApp")

    private func launch(bookshelf: Bool = false, largeText: Bool = false) {
        continueAfterFailure = false
        app.launchArguments = ["-knowledgeTab", "-knowledgeHomePreview", "-tabBarPreview", "-readingDesignPreview"]
        if bookshelf { app.launchArguments.append("-readingBookshelfPreview") }
        if largeText { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launchEnvironment["AI_LAB_E2E_NOTE_NAMESPACE"] = "reading-design-\(UUID().uuidString)"
        app.launchEnvironment["AI_LAB_E2E_DISABLE_ANIMATIONS"] = "1"
        app.launch()
        XCTAssertTrue(app.buttons["knowledge-section-notes"].waitForExistence(timeout: 20), app.debugDescription)
    }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func reveal(_ element: XCUIElement) {
        for _ in 0..<7 where !element.isHittable { app.swipeUp() }
        XCTAssertTrue(element.isHittable, app.debugDescription)
    }

    func testNotesGridSearchPinAndDeleteConfirmation() {
        launch()
        let first = app.buttons["note-row-design-audit"]
        let second = app.buttons["note-row-design-audit-cn"]
        XCTAssertTrue(first.waitForExistence(timeout: 10))
        XCTAssertGreaterThan(abs(first.frame.midX - second.frame.midX), 100)
        XCTAssertTrue(app.buttons["note-create"].isHittable)
        capture("01-notes")
        let search = app.textFields["note-search"]
        search.tap(); search.typeText("Read-only")
        XCTAssertTrue(first.exists)
        XCTAssertFalse(second.exists)
        app.buttons["清除搜索"].tap()
        // Restore scrolling before testing horizontal card gestures.
        app.swipeDown()
        first.swipeRight()
        XCTAssertTrue(app.staticTexts["置顶"].waitForExistence(timeout: 3))
        first.swipeLeft()
        XCTAssertTrue(app.buttons["移到废纸篓"].waitForExistence(timeout: 3))
        // iOS 26 presents the confirmation as a popover with an outside dismissal region.
        app.otherElements["PopoverDismissRegion"].coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
        XCTAssertFalse(app.buttons["移到废纸篓"].exists)
        XCTAssertTrue(first.exists)
    }

    func testBookshelfDisclosureSelectionAndDraftPreservation() {
        launch(bookshelf: true)
        XCTAssertTrue(app.scrollViews["publication-bookshelf-container"].waitForExistence(timeout: 10))
        capture("02-bookshelf")
        let disclosure = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "系统刊物")).firstMatch
        reveal(disclosure)
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "bookshelf-subscribe.")).firstMatch.exists)
        capture("03-bookshelf-collapsed")
        disclosure.tap()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "bookshelf-subscribe.")).firstMatch.waitForExistence(timeout: 3))
        disclosure.tap()
        let create = app.buttons["bookshelf-create-list"]
        reveal(create); create.tap()
        let field = app.textFields["书单名称"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["保存"].isEnabled)
        capture("04-booklist-editor")
        field.tap(); field.typeText("Keep my list")
        XCTAssertTrue(app.buttons["保存"].isEnabled)
        app.switches.firstMatch.tap()
        XCTAssertEqual(app.switches.firstMatch.value as? String, "1")
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "阅读《")).firstMatch.tap()
        let close = app.buttons["关闭书籍"]
        XCTAssertTrue(close.waitForExistence(timeout: 10))
        close.tap()
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        XCTAssertEqual(field.value as? String, "Keep my list")
        XCTAssertEqual(app.switches.firstMatch.value as? String, "1")
        app.buttons["取消"].tap()
    }

    func testLargeTextAndLandscape() {
        launch(largeText: true)
        let first = app.buttons["note-row-design-audit"]
        XCTAssertTrue(first.waitForExistence(timeout: 10))
        XCTAssertGreaterThan(first.frame.width, app.frame.width * 0.75)
        XCTAssertTrue(app.buttons["note-create"].isHittable)
        capture("05-notes-large-text")
        app.terminate()
        launch()
        XCUIDevice.shared.orientation = .landscapeLeft
        defer { XCUIDevice.shared.orientation = .portrait }
        XCTAssertTrue(app.buttons["note-create"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["note-create"].isHittable)
        capture("06-notes-landscape")
    }
}
