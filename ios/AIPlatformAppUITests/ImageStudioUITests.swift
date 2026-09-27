import XCTest

final class ImageStudioUITests: XCTestCase {
    func testManualToolsAndSevenScreens() throws {
        guard ProcessInfo.processInfo.environment["IMAGE_STUDIO_LIVE"] == "1" else { throw XCTSkip("Requires tests/fixtures/image_studio_server.py") }
        let app = XCUIApplication()
        app.launchArguments = ["-imageWorkbenchPreview"]
        app.launchEnvironment["AI_LAB_E2E_BASE_URL"] = "http://127.0.0.1:8897"
        app.launchEnvironment["AI_LAB_E2E_TOKEN"] = "image-studio-local-fixture"
        app.launchEnvironment["AI_LAB_E2E_DISABLE_ANIMATIONS"] = "1"
        app.launchEnvironment["IMAGE_STUDIO_LIVE"] = "1"
        app.launch()
        XCTAssertTrue(app.buttons["studio-tool-文字"].waitForExistence(timeout:20))
        capture("01-editor",app)
        app.buttons["studio-tool-文字"].tap()
        let field = app.textFields["studio-text-input"].exists ? app.textFields["studio-text-input"] : app.textViews["studio-text-input"]
        XCTAssertTrue(field.waitForExistence(timeout:5))
        capture("02-text",app)
        app.buttons["studio-save"].tap()
        app.buttons["图层"].firstMatch.tap()
        XCTAssertTrue(app.buttons["复制"].waitForExistence(timeout:5))
        capture("03-layers",app)
        app.buttons["复制"].tap()
        app.buttons["返回工具"].tap()
        app.buttons["studio-tool-调色"].tap()
        app.sliders.firstMatch.adjust(toNormalizedSliderPosition:0.6)
        capture("04-color",app)
        app.buttons["滤镜"].tap()
        app.buttons["晴日"].tap()
        app.buttons["studio-save"].tap()
        app.buttons["studio-tool-修复"].tap()
        let canvas = app.descendants(matching:.any)["studio-canvas"].firstMatch
        canvas.coordinate(withNormalizedOffset:CGVector(dx:0.4,dy:0.5)).press(forDuration:0.1,thenDragTo:canvas.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)))
        capture("05-repair",app)
        app.buttons["预览修复"].tap()
        app.buttons["studio-save"].tap()
        app.buttons["studio-save"].tap()
        XCTAssertTrue(app.buttons["studio-save-copy"].waitForExistence(timeout:10))
        capture("06-save",app)
        XCTAssertTrue(app.buttons["studio-save-copy"].isHittable)
        app.buttons["studio-save-copy"].tap()
        XCTAssertTrue(app.staticTexts["已保存到作品文件"].waitForExistence(timeout:20))
        app.swipeUp()
        XCTAssertTrue(app.buttons["已存入相册"].waitForExistence(timeout:10))
        app.buttons["批量处理更多照片"].tap()
        XCTAssertTrue(app.staticTexts["同步当前样张的设置"].waitForExistence(timeout:5))
        capture("07-batch",app)
        XCTAssertFalse(app.staticTexts["生成计划"].exists)
        app.buttons["studio-save-batch"].tap()
        XCTAssertTrue(app.staticTexts["已完成 5 张"].waitForExistence(timeout:30))
        XCTAssertFalse(app.staticTexts["studio-error"].exists)
    }
    private func capture(_ name:String,_ app:XCUIApplication) {
        let attachment = XCTAttachment(screenshot:app.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
