import XCTest

final class TravelJourneyUITests: XCTestCase {
    @MainActor func testMapWithoutCoordinatesKeepsSearchAndCloseUsable() {
        let app = XCUIApplication()
        app.launchArguments = ["-travelJourneyPreview", "-travelMapMissingCoordinatesPreview"]
        app.launch()
        let entry = app.buttons["travel-journey-open"]
        for _ in 0..<6 where !entry.isHittable { app.swipeUp() }
        XCTAssertTrue(entry.waitForExistence(timeout: 10))
        entry.tap()
        XCTAssertTrue(app.descendants(matching: .any)["travel-native-map"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["仙巌園"].firstMatch.exists)
        XCTAssertTrue(app.links["查看"].exists || app.buttons["查看"].exists, app.debugDescription)
        XCTAssertFalse(app.staticTexts["地点还没有坐标"].exists)
        XCTAssertTrue(app.links["Google 地图"].exists || app.buttons["Google 地图"].exists)
        let picture = XCTAttachment(screenshot: app.screenshot())
        picture.name = "travel-map-without-model-coordinates"; picture.lifetime = .keepAlways; add(picture)
        app.buttons["travel-journey-close"].tap()
        XCTAssertTrue(entry.waitForExistence(timeout: 5))
    }

    @MainActor func testNativeFullScreenMapAndSheetControls() async throws {
        let app = XCUIApplication()
        app.launchArguments = ["-travelJourneyPreview"]
        app.launch()
        let entry = app.buttons["travel-journey-open"]
        for _ in 0..<4 where !entry.isHittable { app.swipeUp() }
        XCTAssertTrue(entry.waitForExistence(timeout: 10))
        entry.tap()
        let play = app.webViews.buttons["播放旅程"]
        XCTAssertTrue(play.waitForExistence(timeout: 45), app.debugDescription)
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: play)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 40), .completed, app.debugDescription)
        let web = app.webViews.firstMatch
        XCTAssertTrue(web.frame.width >= app.frame.width - 2)
        XCTAssertTrue(web.frame.height >= app.frame.height - 2, "Map must use the full screen")
        let opener = app.descendants(matching: .any)["打开旅程控制"]
        XCTAssertTrue(opener.waitForExistence(timeout: 5)); opener.tap()
        let car = app.descendants(matching: .any)["选择汽车"]
        XCTAssertTrue(car.waitForExistence(timeout: 5), app.debugDescription)
        let sheet = XCTAttachment(screenshot: app.screenshot())
        sheet.name = "ios-travel-transport-sheet"; sheet.lifetime = .keepAlways; add(sheet)
        car.tap()
        XCTAssertFalse(app.webViews.buttons["关闭旅程面板"].exists, "Picking transport should reveal the route")
        play.tap()
        XCTAssertTrue(app.webViews.buttons["暂停旅程"].waitForExistence(timeout: 5))
        try await Task.sleep(for: .seconds(4)) // Capture the vehicle along the route, away from its start marker.
        app.webViews.buttons["暂停旅程"].tap()
        try await Task.sleep(for: .seconds(6)) // Allow the city camera transition and tile rendering before visual QA.
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "ios-fullscreen-travel-map"; screenshot.lifetime = .keepAlways; add(screenshot)
        app.webViews.buttons["返回旅行笔记"].tap()
        XCTAssertTrue(entry.waitForExistence(timeout: 5), "Closing must return to the original note")
        XCTAssertFalse(app.webViews.firstMatch.exists)
    }
}
