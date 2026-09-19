import CryptoKit
import XCTest

final class ProductionSessionIsolationUITests: XCTestCase {
    private var baseURL: URL!
    private var signingSecret: String!

    override func setUpWithError() throws {
        continueAfterFailure = false
        let environment = ProcessInfo.processInfo.environment
        baseURL = try XCTUnwrap(URL(string: environment["LIVE_ACCEPTANCE_BASE_URL"] ?? "http://127.0.0.1:8765"))
        let secretPath = try XCTUnwrap(
            environment["LIVE_ACCEPTANCE_JWT_SECRET_FILE"],
            "Session isolation requires LIVE_ACCEPTANCE_JWT_SECRET_FILE."
        )
        signingSecret = try String(contentsOfFile: secretPath, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        XCTAssertFalse(signingSecret.isEmpty)
    }

    @MainActor
    func testCrossOwnerDeepLinkFailsClosedAcrossAccountSwitchAndColdRelaunch() async throws {
        let suffix = UUID().uuidString.lowercased()
        let ownerA = "isolation-a-\(suffix)"
        let ownerB = "isolation-b-\(suffix)"
        let tenant = "isolation-tenant-\(suffix)"
        let tokenA = localToken(owner: ownerA, tenant: tenant)
        let tokenB = localToken(owner: ownerB, tenant: tenant)
        try await acceptAgreement(token: tokenA)
        try await acceptAgreement(token: tokenB)

        let workflowResponse = try await request(
            "POST",
            path: "/api/v1/workflows",
            token: tokenA,
            body: [
                "title": "Owner A private review",
                "description": "Deep-link owner and session isolation acceptance",
                "desired_output": "Editable PPTX",
                "output_kind": "presentation",
            ]
        )
        XCTAssertEqual(workflowResponse.status, 201)
        let workflow = try XCTUnwrap(workflowResponse.json["workflow"] as? [String: Any])
        let workflowID = try XCTUnwrap(workflow["id"] as? String)
        let reviewPath = "/api/v1/workflows/\(workflowID)/structured-reviews/final-draft"
        let marker = "PRIVATE-A-\(suffix)"
        let createReview = try await request(
            "POST",
            path: reviewPath,
            token: tokenA,
            body: [
                "schema_id": "workflow.structured-review.v1",
                "document": [
                    "title": marker,
                    "fields": [["id": "title", "label": "标题", "type": "text", "required": true]],
                    "values": ["title": marker],
                ],
            ]
        )
        XCTAssertEqual(createReview.status, 201)

        let appA = launchReview(workflowID: workflowID, token: tokenA)
        XCTAssertTrue(appA.staticTexts[marker].waitForExistence(timeout: 20))
        appA.terminate()

        let appB = launchReview(workflowID: workflowID, token: tokenB)
        XCTAssertFalse(appB.staticTexts[marker].waitForExistence(timeout: 3))
        let deniedWhileForeignAppIsOpen = try await request("GET", path: reviewPath, token: tokenB)
        XCTAssertEqual(deniedWhileForeignAppIsOpen.status, 404)
        appB.terminate()

        let appARelaunched = launchReview(workflowID: workflowID, token: tokenA)
        XCTAssertTrue(appARelaunched.staticTexts[marker].waitForExistence(timeout: 20))
        let denied = try await request("GET", path: reviewPath, token: tokenB)
        XCTAssertEqual(denied.status, 404)
    }

    private func launchReview(workflowID: String, token: String) -> XCUIApplication {
        let app = XCUIApplication(bundleIdentifier: "com.ailab.AIPlatformApp")
        app.launchArguments = ["-structuredReviewE2E", "-autoLogin"]
        app.launchEnvironment["AI_LAB_E2E_BASE_URL"] = baseURL.absoluteString
        app.launchEnvironment["AI_LAB_E2E_TOKEN"] = token
        app.launchEnvironment["AI_LAB_E2E_WORKFLOW_ID"] = workflowID
        app.launchEnvironment["AI_LAB_E2E_REVIEW_KEY"] = "final-draft"
        app.launch()
        return app
    }

    private func acceptAgreement(token: String) async throws {
        let agreement = try await request("GET", path: "/api/v1/legal/agreement", token: token)
        let version = try XCTUnwrap(agreement.json["version"] as? String)
        let accepted = try await request(
            "PUT",
            path: "/api/v1/me/agreement-acceptance",
            token: token,
            body: [
                "agreement_version": version,
                "idempotency_key": UUID().uuidString,
                "source": "ios",
            ]
        )
        XCTAssertEqual(accepted.status, 200)
    }

    private func request(
        _ method: String,
        path: String,
        token: String,
        body: [String: Any]? = nil
    ) async throws -> (status: Int, json: [String: Any]) {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("ios-unified-agreement-v1", forHTTPHeaderField: "X-Client-Contract")
        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        let http = try XCTUnwrap(response as? HTTPURLResponse)
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        return (http.statusCode, json)
    }

    private func localToken(owner: String, tenant: String) -> String {
        func encoded(_ value: Data) -> String {
            value.base64EncodedString()
                .replacingOccurrences(of: "+", with: "-")
                .replacingOccurrences(of: "/", with: "_")
                .replacingOccurrences(of: "=", with: "")
        }
        let header = encoded(Data(#"{"alg":"HS256","typ":"JWT"}"#.utf8))
        let expires = Int(Date().addingTimeInterval(3_600).timeIntervalSince1970)
        let payloadObject: [String: Any] = [
            "sub": owner,
            "username": owner,
            "tenant_id": tenant,
            "iss": "quantumn",
            "aud": "quantumn-ios",
            "token_use": "access",
            "principal_type": "human",
            "amr": ["session_isolation_ui"],
            "iat": Int(Date().timeIntervalSince1970),
            "exp": expires,
        ]
        let payload = encoded(try! JSONSerialization.data(withJSONObject: payloadObject, options: [.sortedKeys]))
        let signingInput = "\(header).\(payload)"
        let signature = HMAC<SHA256>.authenticationCode(
            for: Data(signingInput.utf8),
            using: SymmetricKey(data: Data(signingSecret.utf8))
        )
        return "\(signingInput).\(encoded(Data(signature)))"
    }
}
