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
