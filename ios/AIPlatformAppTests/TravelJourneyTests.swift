import XCTest
@testable import AIPlatformApp

final class TravelJourneyTests: XCTestCase {
    func testPayloadUsesCurrentCoordinatesAndBreaksMissingLegs() {
        let plan = TravelPlanDocument(destination: "杭州", dateRange: nil, budget: nil, companions: nil, style: nil, stops: [
            .init(name: "起点", latitude: 30.2, longitude: 120.1),
            .init(name: "待定位", latitude: nil, longitude: nil),
            .init(name: "终点", latitude: 30.3, longitude: 120.2)
        ])
        let payload = TravelJourneyPayload(title: "我的旅行", plan: plan)
        XCTAssertEqual(payload.destination, "杭州")
        XCTAssertEqual(payload.stops.map(\.coordinate), [[120.1, 30.2], [120.2, 30.3]])
        XCTAssertTrue(payload.legs.isEmpty, "Do not invent a route across an unlocated place")
        XCTAssertEqual(payload.unlocatedCount, 1)
    }

    func testInvalidCoordinatesAreExcludedAndScriptTextIsData() throws {
        let title = "</script><script>alert('x')</script>"
        let plan = TravelPlanDocument(destination: title, dateRange: nil, budget: nil, companions: nil, style: nil, stops: [
            .init(name: title, latitude: 35, longitude: 135),
            .init(name: "Invalid", latitude: 100, longitude: 0),
            .init(name: "Invalid2", latitude: 0, longitude: .infinity)
        ])
        let payload = TravelJourneyPayload(title: title, plan: plan)
        XCTAssertEqual(payload.stops.count, 1)
        let json = try XCTUnwrap(payload.json)
        XCTAssertFalse(json.contains("<"))
        let decoded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        XCTAssertEqual(decoded["title"] as? String, title)
    }

    func testRoutePreservesVisitOrderIncludingReturnToStart() {
        let a = TravelRouteStop(name: "A", latitude: 1, longitude: 2)
        let b = TravelRouteStop(name: "B", latitude: 3, longitude: 4)
        let plan = TravelPlanDocument(destination: nil, dateRange: nil, budget: nil, companions: nil, style: nil, stops: [a, b, a])
        let payload = TravelJourneyPayload(title: "Loop", plan: plan)
        XCTAssertEqual(payload.stops.count, 2)
        XCTAssertEqual(payload.legs.map(\.from), [0, 1])
        XCTAssertEqual(payload.legs.map(\.to), [1, 0])
    }

    func testBundledMapHasNoDemoCoordinatesAndSupportsNativeLifecycle() throws {
        let url = try XCTUnwrap(Bundle.main.url(forResource: "journey", withExtension: "js"))
        let script = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(script.contains("135.6668"))
        XCTAssertFalse(script.contains("京都"))
        XCTAssertTrue(script.contains("window.quantumJourney"))
        XCTAssertTrue(script.contains("window.pauseJourney=pause"))
        XCTAssertTrue(script.contains("result.requestID!==requestID"))
    }
}
