import SwiftUI
import WebKit
import CryptoKit
import CoreText
import MapKit

/// The reviewed interaction renderer uses the same authenticated native transport
/// as the rest of Quantum. Credentials never enter JavaScript or web storage.
struct TravelSpaceView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var activities: WorkflowActivityCoordinator
    @State private var routedWorkflowID: String?
    @State private var showingPhotoStudio = false
    @State private var photoScope: WorkflowActivityCoordinator.Scope?
    @State private var photoAction: ClientActionDTO?
    @State private var processingPhotoData: Data?
    @State private var photoError: String?

    var body: some View {
        Group {
            if let scope = activities.currentScope {
                TravelSpaceWebView(scope: scope, activities: activities,
                    onTab: { appState.activeTab = $0 },
                    onPhoto: { photoScope = scope; processingPhotoData = nil; showingPhotoStudio = true },
                    onPhotoAction: { photoScope = scope; photoError = nil; photoAction = $0 },
                    onPhotoImage: { photoScope = scope; processingPhotoData = $0; showingPhotoStudio = true },
                    routedWorkflowID: routedWorkflowID,
                    onRouteDelivered: { if routedWorkflowID == $0 { routedWorkflowID = nil } })
                    .id(scope)
            } else {
                ContentUnavailableView("选择一个对话，开始下一段旅程", systemImage: "bubble.left.and.bubble.right",
                    description: Text("旅行任务会保留在创建它的对话中。"))
            }
        }
        .background(QuantumMistBackground())
        .fullScreenCover(isPresented: $showingPhotoStudio) {
            Group {
            if let processingPhotoData {
                ImageWorkbench(data: processingPhotoData) { data in
                    guard let photoScope, activities.isCurrent(photoScope) else { showingPhotoStudio = false; return }
                    TenantSessionCoordinator.shared.attachPhoto(data); appState.activeTab = 0; showingPhotoStudio = false
                }
            } else { ImageStudioEntry { data in
                guard let photoScope, activities.isCurrent(photoScope) else { showingPhotoStudio = false; return }
                TenantSessionCoordinator.shared.attachPhoto(data)
                appState.activeTab = 0
                showingPhotoStudio = false
            } }
            }
        }
        .sheet(item: $photoAction) { action in
            NativeClientActionHost(action: action) { status, metadata in
                guard let scope = photoScope, activities.isCurrent(scope) else { return }
                Task {
                    do {
                        _ = try await CapabilityClient().recordClientActionReceipt(actionId: action.id, status: status, resultMetadata: metadata)
                        guard activities.isCurrent(scope) else { return }
                        photoAction = nil
                    } catch {
                        guard activities.isCurrent(scope) else { return }
                        photoError = error.localizedDescription
                    }
                }
            }
            .overlay(alignment: .bottom) {
                if let photoError { Text(photoError).foregroundStyle(AppTheme.Colors.statusError).padding(18).quantumCard().padding(20) }
            }
        }
        .onChange(of: activities.currentScope) { _, _ in showingPhotoStudio = false; photoAction = nil; processingPhotoData = nil; photoScope = nil }
        .task(id: activities.currentScope) {
            #if DEBUG
            let arguments = ProcessInfo.processInfo.arguments
            if arguments.contains("-travelLiveEvidence"), let scope = activities.currentScope,
               let index = arguments.firstIndex(of: "-travelLiveWorkflowID"), arguments.indices.contains(index + 1),
               let workflow = try? await APIClient.shared.fetchWorkflow(id: arguments[index + 1]),
               activities.isCurrent(scope), activities.accepts(workflow, in: scope) {
                routedWorkflowID = workflow.id
            }
            #endif
        }
        .task(id: appState.pendingWorkflowId) {
            if let workflow = await appState.resolvePendingWorkflow(using: { try await APIClient.shared.fetchWorkflow(id: $0) }) {
                routedWorkflowID = workflow.id
            }
        }
    }
}

/// Saved notes reuse the approved travel renderer, independent of the source Chat selection.
struct TravelNoteTemplateView: View {
    let noteID: String
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var activities: WorkflowActivityCoordinator
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        Group {
            if let scope = activities.currentScope {
                TravelSpaceWebView(noteID: noteID, scope: scope, activities: activities,
                    onTab: { appState.activeTab = $0; dismiss() },
                    onPhoto: {}, onPhotoAction: { _ in }, onPhotoImage: { _ in },
                    routedWorkflowID: nil, onRouteDelivered: { _ in })
                    .id(noteID + scope.ownerIdentity)
            } else { ContentUnavailableView("笔记正在准备", systemImage: "book") }
        }
        .background(QuantumMistBackground())
    }
}

/// Legacy artifact entry points share the current template; they cannot mutate a note.
struct TravelArtifactTemplateView: View {
    let content: String
    @StateObject private var activities = WorkflowActivityCoordinator()
    var body: some View {
        TravelSpaceWebView(readOnlyDocument: content,
            scope: .init(ownerIdentity: "readonly-artifact", clientSessionId: "readonly-artifact", generation: 0),
            activities: activities, onTab: { _ in }, onPhoto: {}, onPhotoAction: { _ in }, onPhotoImage: { _ in },
            routedWorkflowID: nil, onRouteDelivered: { _ in })
    }
}

private struct TravelSpaceWebView: UIViewRepresentable {
    var noteID: String? = nil
    var readOnlyDocument: String? = nil
    let scope: WorkflowActivityCoordinator.Scope
    let activities: WorkflowActivityCoordinator
    let onTab: (Int) -> Void
    let onPhoto: () -> Void
    let onPhotoAction: (ClientActionDTO) -> Void
    let onPhotoImage: (Data) -> Void
    let routedWorkflowID: String?
    let onRouteDelivered: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        if readOnlyDocument == nil { configuration.userContentController.addUserScript(WKUserScript(source: "window.__quantumBudgetNative=true;", injectionTime: .atDocumentStart, forMainFrameOnly: true)) }
        configuration.userContentController.addScriptMessageHandler(context.coordinator,
            contentWorld: .page, name: "quantum")
        configuration.setURLSchemeHandler(context.coordinator, forURLScheme: "quantum-media")
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.isOpaque = false
        view.backgroundColor = .clear
        view.scrollView.backgroundColor = .clear
        view.scrollView.isScrollEnabled = false
        view.scrollView.contentInsetAdjustmentBehavior = .never
        view.accessibilityIdentifier = "quantum-travel-space"
        if let file = Bundle.main.url(forResource: "index", withExtension: "html", subdirectory: "TravelSpace") {
            context.coordinator.root = file.deletingLastPathComponent()
            view.loadFileURL(file, allowingReadAccessTo: file.deletingLastPathComponent())
        } else {
            view.loadHTMLString("<html lang='zh'><body><p>旅行界面资源缺失，请重新安装应用。</p></body></html>", baseURL: nil)
        }
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        context.coordinator.parent = self
        context.coordinator.deliverRoute(to: view)
    }

    static func dismantleUIView(_ view: WKWebView, coordinator: Coordinator) {
        coordinator.pageLoaded = false
        coordinator.tasks.values.forEach { $0.cancel() }
        coordinator.tasks.removeAll()
        coordinator.eventTask?.cancel()
        coordinator.mediaTasks.values.forEach { $0.cancel() }
        coordinator.mediaTasks.removeAll()
        coordinator.speech.cancel()
        coordinator.location.cancel()
        view.configuration.userContentController.removeScriptMessageHandler(forName: "quantum", contentWorld: .page)
        view.stopLoading()
    }

    @MainActor final class Coordinator: NSObject, WKScriptMessageHandlerWithReply, WKNavigationDelegate, WKURLSchemeHandler {
        var parent: TravelSpaceWebView
        var boundNoteID: String?
        var boundWorkflowID: String?
        var pageLoaded = false
        var deliveringWorkflowID: String?
        var eventTask: Task<Void, Never>?
        var eventExecutionID: String?
        var executionEvents: [WorkflowEventDTO] = []
        var ownedWorkflowIDs: Set<String> = []
        let credentialGeneration: UInt64
        var root: URL?
        var tasks: [UUID: Task<Void, Never>] = [:]
        var mediaTasks: [ObjectIdentifier: Task<Void, Never>] = [:]
        let speech = SpeechRecognizerService()
        let location = TravelLocationService()
        var voiceCancelled = false
        init(_ parent: TravelSpaceWebView) {
            self.parent = parent
            boundNoteID = parent.noteID
            credentialGeneration = APIClient.shared.currentCredentialGeneration()
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            pageLoaded = true
            deliverRoute(to: webView)
        }

        func deliverRoute(to view: WKWebView) {
            guard pageLoaded, let identifier = parent.routedWorkflowID,
                  deliveringWorkflowID != identifier,
                  let data = try? JSONSerialization.data(withJSONObject: ["workflowId": identifier]),
                  let json = String(data: data, encoding: .utf8) else { return }
            deliveringWorkflowID = identifier
            view.evaluateJavaScript("window.__quantumWorkflowReady===true && window.dispatchEvent(new CustomEvent('quantum-open-workflow',{detail:\(json)}))") { [weak self, weak view] result, error in
                guard let self else { return }
                self.deliveringWorkflowID = nil
                if error == nil, result as? Bool == true { self.parent.onRouteDelivered(identifier) }
                else if let view, self.pageLoaded {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self, weak view] in
                        if let view { self?.deliverRoute(to: view) }
                    }
                }
            }
        }

        func trackEvents(executionID: String) {
            if eventExecutionID != executionID {
                eventTask?.cancel()
                eventTask = nil
                executionEvents.removeAll()
                eventExecutionID = executionID
            }
            guard eventTask == nil else { return }
            let after = executionEvents.last?.id ?? 0
            eventTask = Task { [weak self] in
                guard let self else { return }
                defer { if self.eventExecutionID == executionID { self.eventTask = nil } }
                do {
                    for try await event in APIClient.shared.workflowEventStream(executionId: executionID, after: after) {
                        try self.checkScope()
                        guard !Task.isCancelled, self.eventExecutionID == executionID else { return }
                        if !self.executionEvents.contains(where: { $0.id == event.id }) {
                            self.executionEvents.append(event)
                            if self.executionEvents.count > 100 { self.executionEvents.removeFirst(self.executionEvents.count - 100) }
                        }
                    }
                } catch { /* The next authoritative snapshot reconnects this read-only stream. */ }
            }
        }

        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage,
                                   replyHandler: @escaping (Any?, String?) -> Void) {
            guard message.frameInfo.isMainFrame, message.frameInfo.request.url?.isFileURL == true,
                  let body = message.body as? [String: Any], let operation = body["operation"] as? String else {
                replyHandler(nil, "不允许此页面调用客户端"); return
            }
            let identifier = UUID()
            tasks[identifier] = Task { [weak self] in
                guard let self else { replyHandler(nil, "页面已关闭"); return }
                defer { self.tasks.removeValue(forKey: identifier) }
                do {
                    try self.checkScope()
                    let result = try await self.perform(operation, body: body)
                    try self.checkScope()
                    replyHandler(result, nil)
                } catch { replyHandler(nil, error.localizedDescription) }
            }
        }

        private func checkScope() throws {
            try Task.checkCancellation()
            guard (parent.readOnlyDocument != nil || (parent.noteID == nil ? parent.activities.isCurrent(parent.scope) : parent.activities.currentScope?.ownerIdentity == parent.scope.ownerIdentity)),
                  credentialGeneration == APIClient.shared.currentCredentialGeneration() else {
                throw APIError.network("账号或对话已切换，请重新打开任务")
            }
        }

        private func object<T: Encodable>(_ value: T) throws -> Any {
            try JSONSerialization.jsonObject(with: JSONEncoder().encode(value))
        }

        private func string(_ body: [String: Any], _ key: String) throws -> String {
            guard let value = body[key] as? String, !value.isEmpty, value.count <= (key == "content" ? 8 * 1024 * 1024 : 48000) else {
                throw APIError.network("缺少有效的 \(key)")
            }
            return value
        }

        private func ownedWorkflow(_ body: [String: Any]) async throws -> WorkflowDTO {
            let value = try await APIClient.shared.fetchWorkflow(id: string(body, "workflowId"))
            try checkScope()
            guard parent.activities.accepts(value, in: parent.scope) else {
                throw APIError.network("任务不属于当前对话")
            }
            ownedWorkflowIDs.insert(value.id)
            return value
        }

        private func workflowPresentation(_ workflow: WorkflowDTO) throws -> [String: Any] {
            guard var value = try object(workflow) as? [String: Any] else { throw APIError.invalidURL }
            let output = workflow.desiredOutput.lowercased()
            if ["旅行计划", "攻略", "旅行手记", "旅程"].contains(where: output.contains) { value["uiKind"] = "travel" }
            else if ["图片", "图像", "照片", "image", "photo"].contains(where: output.contains) { value["uiKind"] = "photo" }
            else { value["uiKind"] = WorkflowDetailTransitionPolicy.isTravel(workflow) ? "travel" : "archive" }
            return value
        }

        private func draftURL(workflowID: String? = nil) throws -> URL {
            let directory = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                appropriateFor: nil, create: true).appendingPathComponent("TravelDrafts", isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let identity = parent.scope.ownerIdentity + "\u{0}" + parent.scope.clientSessionId + (workflowID.map { "\u{0}" + $0 } ?? "")
            let digest = SHA256.hash(data: Data(identity.utf8)).map { String(format: "%02x", $0) }.joined()
            return directory.appendingPathComponent(digest + ".json")
        }

        private func perform(_ operation: String, body: [String: Any]) async throws -> Any {
            let api = APIClient.shared
            if let raw = parent.readOnlyDocument {
                if operation == "draft" { return ["saved": false] }
                guard operation == "bootstrap" else { throw APIError.network("这是原始成果预览，请从已保存的旅行笔记继续记录") }
                var document = NoteIllustrationPlacement.travelObject(raw) ?? ["destination": "旅行手记", "journal": raw]
                document["schema_version"] = 2
                for key in ["actions", "stops", "sources", "photo_references"] where document[key] == nil { document[key] = [] }
                let bytes = try JSONSerialization.data(withJSONObject: document)
                let content = String(decoding: bytes, as: UTF8.self)
                return ["workflows": [], "draft": NSNull(), "readOnly": true,
                    "note": ["noteMode": true, "workflow": ["id": "readonly-artifact", "title": document["destination"] ?? "旅行手记", "status": "ready", "uiKind": "travel"],
                             "artifact": ["id": "readonly-artifact", "contentHash": SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()], "content": content]]
            }
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("-travelSpacePreview") {
                switch operation {
                case "bootstrap": return ["workflows": [], "draft": NSNull()]
                case "draft": return ["saved": false]
                case "photoStudio": parent.onPhoto(); return ["opened": true]
                case "tab":
                    guard let tag = body["tag"] as? Int, [0, 1, 2, 3].contains(tag) else { throw APIError.invalidURL }
                    parent.onTab(tag); return ["selected": tag]
                default: throw APIError.network("预览不执行联网任务或保存个人数据")
                }
            }
            #endif
            if operation == "photoStudio" { parent.onPhoto(); return ["opened": true] }
            if operation == "bootstrap", let noteID = parent.noteID {
                return ["workflows": [], "draft": NSNull(), "note": try await notebookSnapshot(noteID), "offline": false]
            }
            if operation == "bootstrap" {
                let workflows = try await api.fetchWorkflows().filter { parent.activities.accepts($0, in: parent.scope) }
                try checkScope()
                ownedWorkflowIDs.formUnion(workflows.map(\.id))
                let draft = (try? Data(contentsOf: draftURL())).flatMap { try? JSONSerialization.jsonObject(with: $0) }
                return ["workflows": try workflows.map(workflowPresentation), "draft": draft ?? NSNull(), "offline": api.isOfflineMode]
            }
            if operation == "draft", boundNoteID != nil { return ["saved": false] }
            if operation == "draft" {
                guard let state = body["state"] as? [String: Any] else { throw APIError.network("草稿无效") }
                let data = try JSONSerialization.data(withJSONObject: state)
                guard data.count <= 4 * 1024 * 1024 else { throw APIError.network("草稿过大，请先上传附件") }
                if let workflowID = state["_workflowId"] as? String {
                    guard ownedWorkflowIDs.contains(workflowID) else { throw APIError.network("请先读取当前对话中的任务再保存草稿") }
                    try data.write(to: draftURL(workflowID: workflowID), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
                }
                try data.write(to: draftURL(), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
                return ["saved": true]
            }
            if operation == "tab" {
                guard let tag = body["tag"] as? Int, [0, 1, 2, 3].contains(tag) else { throw APIError.network("导航无效") }
                parent.onTab(tag); return ["selected": tag]
            }
            if operation == "budgetQueueRead" {
                guard let noteID = boundNoteID else { return [] }
                _ = try await api.readTravelNotebook(id: noteID)
                try checkScope()
                return try object(TravelExpenseDraftQueue.read(noteID: noteID))
            }
            if operation == "location" {
                let value = try await location.coordinate()
                return ["lat": value.coordinate.latitude, "lon": value.coordinate.longitude,
                        "accuracy": value.horizontalAccuracy, "at": value.timestamp.timeIntervalSince1970]
            }
            if operation == "map" {
                guard let bounds = body["bounds"] as? [String: Double],
                      let west = bounds["west"], let east = bounds["east"],
                      let north = bounds["north"], let south = bounds["south"],
                      west.isFinite, east.isFinite, north.isFinite, south.isFinite,
                      west >= -180, east <= 180, south >= -85, north <= 85, east > west, north > south else {
                    throw APIError.network("地图范围无效")
                }
                let options = MKMapSnapshotter.Options()
                let northwest = CLLocationCoordinate2D(latitude: north, longitude: west)
                let southeast = CLLocationCoordinate2D(latitude: south, longitude: east)
                let first = MKMapPoint(northwest), last = MKMapPoint(southeast)
                options.mapRect = MKMapRect(x: first.x, y: first.y, width: last.x - first.x, height: last.y - first.y)
                options.size = CGSize(width: 1000, height: 620)
                options.scale = 1
                options.mapType = .standard
                let snapshot = try await MKMapSnapshotter(options: options).start()
                // MapKit expands a requested region to match its viewport. Crop
                // back to the exact Mercator bounds used by the HTML pin layer.
                let start = snapshot.point(for: northwest), end = snapshot.point(for: southeast)
                let rect = CGRect(x: start.x, y: start.y, width: end.x - start.x, height: end.y - start.y)
                guard rect.width > 0, rect.height > 0,
                      let cropped = snapshot.image.cgImage?.cropping(to: rect),
                      let image = UIImage(cgImage: cropped).jpegData(compressionQuality: 0.8) else {
                    throw APIError.network("地图生成失败")
                }
                return ["image": "data:image/jpeg;base64," + image.base64EncodedString()]
            }
            if operation == "export" {
                guard let content = body["content"] as? String, content.utf8.count <= 4 * 1024 * 1024 else { throw APIError.network("导出内容过大") }
                let filename = try string(body, "filename")
                guard ["travel-route.kml", "travel-journal.json", "travel-track.gpx"].contains(filename) else { throw APIError.network("导出类型无效") }
                let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                let file = folder.appendingPathComponent(filename)
                try Data(content.utf8).write(to: file, options: .atomic)
                guard let window = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).flatMap(\.windows).first(where: \.isKeyWindow),
                      var controller = window.rootViewController else { throw APIError.network("无法打开导出面板") }
                while let presented = controller.presentedViewController { controller = presented }
                let share = UIActivityViewController(activityItems: [file], applicationActivities: nil)
                share.popoverPresentationController?.sourceView = controller.view
                share.popoverPresentationController?.sourceRect = CGRect(x: controller.view.bounds.midX, y: controller.view.bounds.maxY - 40, width: 1, height: 1)
                controller.present(share, animated: true)
                return ["opened": true]
            }
            if operation == "ask" {
                let response = try await api.chat(question: string(body, "question"), requestId: UUID().uuidString,
                    sessionId: parent.scope.clientSessionId, quotedContext: body["quote"] as? String)
                return ["answer": response.answer, "sessionId": response.sessionId ?? "",
                        "hasActions": response.events?.contains(where: { $0.type == "capability.proposed" || $0.type == "client.action.proposed" }) ?? false]
            }
            if operation == "voice" {
                guard speech.state == .idle else { throw APIError.network("语音识别已经在进行") }
                voiceCancelled = false
                defer { speech.cancel() }
                guard !speech.isMockMode else { throw APIError.network("当前设备的中文语音识别不可用，请输入文字") }
                await speech.start(autoStopOnSilence: false, captureAudio: body["capture"] as? Bool == true)
                guard !speech.permissionDenied, !speech.isMockMode, speech.state == .recording else {
                    speech.cancel(); throw APIError.network("未能开始语音识别，请检查麦克风与语音权限")
                }
                let deadline = Date().addingTimeInterval(45)
                while speech.state != .idle {
                    try checkScope()
                    if Date() >= deadline { speech.stop() }
                    try await Task.sleep(for: .milliseconds(100))
                }
                if voiceCancelled { return ["text": ""] }
                var result: [String: Any] = ["text": speech.transcript]
                if let file = speech.capturedAudioURL, let bytes = try? Data(contentsOf: file), !bytes.isEmpty {
                    let receipt = try await api.uploadDocument(data: bytes, filename: "travel-recording.m4a", contentType: "audio/mp4", fileOptOut: true)
                    result["media"] = ["kind": "audio", "src": "quantum-media://audio/" + receipt.sourceId,
                                       "name": "旅行录音", "seconds": speech.elapsedSeconds]
                }
                return result
            }
            if operation == "voiceStop" {
                if body["cancel"] as? Bool == true { voiceCancelled = true; speech.cancel() } else { speech.stop() }
                return ["stopped": true]
            }
            if operation == "voiceStatus" {
                return ["text": speech.transcript, "levels": speech.audioLevels.map(Double.init), "seconds": speech.elapsedSeconds]
            }
            if operation == "uploadMedia" {
                guard let value = body["data"] as? String, value.count <= 1500000 else { throw APIError.network("附件过大") }
                guard let comma = value.firstIndex(of: ","), let data = Data(base64Encoded: String(value[value.index(after: comma)...])),
                      data.count <= 900000 else { throw APIError.network("请选择小于 900 KB 的附件") }
                let prefix = String(value[..<comma])
                if prefix.hasPrefix("data:image/") {
                    let receipt = try await api.uploadImage(data: data)
                    return ["src": "quantum-media://image/" + receipt.artifactId]
                }
                let suffix: String, mime: String
                if prefix.hasPrefix("data:audio/webm") { suffix = "webm"; mime = "audio/webm" }
                else if prefix.hasPrefix("data:audio/ogg") { suffix = "ogg"; mime = "audio/ogg" }
                else if prefix.hasPrefix("data:audio/mp4") { suffix = "m4a"; mime = "audio/mp4" }
                else if prefix.hasPrefix("data:audio/wav") { suffix = "wav"; mime = "audio/wav" }
                else { throw APIError.network("附件类型不受支持") }
                let receipt = try await api.uploadDocument(data: data, filename: "travel-recording." + suffix, contentType: mime, fileOptOut: true)
                return ["src": "quantum-media://audio/" + receipt.sourceId]
            }
            if operation == "create" {
                guard parent.noteID == nil else { throw APIError.network("请从工作流入口新建旅行") }
                let response = try await api.createWorkflow(title: string(body, "title"), description: string(body, "description"),
                    desiredOutput: "旅行计划、带来源的攻略与旅行手记", outputKind: "travel",
                    sourceClientSessionId: parent.scope.clientSessionId, requestId: string(body, "requestId"))
                try checkScope()
                boundNoteID = nil; boundWorkflowID = nil
                ownedWorkflowIDs.insert(response.workflow.id)
                parent.activities.track(response.workflow)
                return try object(response)
            }
            if operation == "snapshot", parent.noteID == nil, boundNoteID != nil,
               let requested = body["workflowId"] as? String, requested != boundWorkflowID {
                boundNoteID = nil; boundWorkflowID = nil
            }
            if let noteID = boundNoteID, ["snapshot", "saveState", "revise", "progress", "saveNotebook", "printNotebook", "versions", "version"].contains(operation) {
                return try await performNotebook(operation, id: noteID, body: body)
            }
            let workflow = try await ownedWorkflow(body)
            let uiKind = try workflowPresentation(workflow)["uiKind"] as? String
            if uiKind == "archive", !["snapshot", "versions", "version", "artifactContent", "shareArtifact"].contains(operation) {
                throw APIError.network("旧工作流仅保留历史记录与成果导出")
            }
            if operation == "openPhotoTask" {
                guard try workflowPresentation(workflow)["uiKind"] as? String == "photo", let latest = workflow.latestExecution else {
                    throw APIError.network("照片处理记录尚未准备好")
                }
                let execution = try await api.fetchWorkflowExecution(id: latest.id)
                guard execution.workflowId == workflow.id else { throw APIError.network("照片执行不属于当前任务") }
                if execution.status == "awaiting_approval" {
                    let action = try await api.prepareImageAction(executionId: execution.id)
                    try checkScope()
                    guard ["image_process", "image_studio_v1"].contains(action.actionType) else { throw APIError.network("照片处理参数类型不匹配") }
                    parent.onPhotoAction(action)
                } else if execution.status == "completed" {
                    let artifacts = try await api.fetchWorkflowArtifacts(executionId: execution.id)
                    guard let image = artifacts.last(where: { $0.mimeType.hasPrefix("image/") }) else { throw APIError.network("处理后的照片尚未读取到") }
                    let data = try await api.downloadAuthenticated(path: "workflow-executions/\(execution.id)/artifacts/\(image.id)/download", expectedHash: image.contentHash)
                    try checkScope()
                    guard data.count <= 12 * 1024 * 1024 else { throw APIError.network("照片超过编辑器的 12 MB 上限，可在成果中导出原件") }
                    parent.onPhotoImage(data)
                } else { throw APIError.network("照片仍在准备中，请先查看当前进度") }
                return ["opened": true]
            }
            if operation == "replan" {
                guard workflow.latestExecution == nil else { throw APIError.network("制作已开始，请在成稿里调整") }
                return try object(await api.replanWorkflow(workflowId: workflow.id, instruction: string(body, "instruction"), description: string(body, "description")))
            }
            if operation == "snapshot", let execution = workflow.latestExecution, execution.status == "completed" {
                let cloud = try await api.fetchKnowledgeNotes(includeArchived: true, includeTrashed: true)
                try checkScope()
                let linked = cloud.items.filter { note in
                    guard !note.archived, note.trashed != true, let raw = try? notebookContent(note.markdown),
                          let document = try? JSONSerialization.jsonObject(with: Data(raw.utf8)) as? [String: Any] else { return false }
                    return document["workflow_execution_id"] as? String == execution.id
                }
                if linked.count == 1 { boundNoteID = linked[0].noteId; boundWorkflowID = workflow.id; return try await notebookSnapshot(linked[0].noteId) }
            }
            if operation == "snapshot" {
                var snapshot: [String: Any] = ["workflow": try workflowPresentation(workflow)]
                snapshot["draft"] = (try? Data(contentsOf: draftURL(workflowID: workflow.id))).flatMap { try? JSONSerialization.jsonObject(with: $0) } ?? NSNull()
                snapshot["clarification"] = try object(await api.fetchWorkflowClarification(workflowId: workflow.id))
                if workflow.activePlanId != nil { snapshot["plan"] = try object(await api.fetchWorkflowPlan(workflowId: workflow.id)) }
                if let execution = workflow.latestExecution {
                    snapshot["execution"] = try object(await api.fetchWorkflowExecution(id: execution.id))
                    trackEvents(executionID: execution.id)
                    snapshot["executionEvents"] = try object(executionEvents)
                    let artifacts = try await api.fetchWorkflowArtifacts(executionId: execution.id)
                    snapshot["artifacts"] = try object(artifacts)
                    if let artifact = artifacts.filter({ $0.metadata.renderType == "travel_plan_v2" })
                        .sorted(by: {
                            if ($0.metadata.travelRevision ?? 0) != ($1.metadata.travelRevision ?? 0) {
                                return ($0.metadata.travelRevision ?? 0) > ($1.metadata.travelRevision ?? 0)
                            }
                            if ($0.metadata.approvalGate == nil) != ($1.metadata.approvalGate == nil) {
                                return $0.metadata.approvalGate == nil
                            }
                            if $0.createdAt != $1.createdAt { return ($0.createdAt ?? "") > ($1.createdAt ?? "") }
                            return $0.id > $1.id
                        }).first {
                        snapshot["artifact"] = try object(artifact)
                        let content = try await api.fetchWorkflowArtifactContent(executionId: execution.id, artifactId: artifact.id)
                        let digest = SHA256.hash(data: Data(content.content.utf8)).map { String(format: "%02x", $0) }.joined()
                        guard content.id == artifact.id, digest == artifact.contentHash else {
                            throw APIError.network("旅行成果与当前版本不一致，请重新读取")
                        }
                        snapshot["content"] = content.content
                    }
                }
                snapshot["offline"] = api.isOfflineMode
                #if DEBUG
                // Explicit simulator acceptance capture; no credentials or additional API calls.
                let evidence: [String: Any] = [
                    "workflow_id": workflow.id, "workflow_title": workflow.title,
                    "workflow_status": workflow.status,
                    "planning_error": (((snapshot["clarification"] as? [String: Any])?["events"] as? [[String: Any]] ?? []).last(where: { ["planning_failed", "clarification_unavailable"].contains($0["type"] as? String ?? "") })?.filter { ["type", "message", "payload"].contains($0.key) } ?? [:]),
                    "execution_status": (snapshot["execution"] as? [String: Any])?["status"] ?? NSNull(),
                    "execution_progress": (snapshot["execution"] as? [String: Any])?["progress"] ?? NSNull(),
                    "execution_id": (snapshot["execution"] as? [String: Any])?["id"] ?? NSNull(),
                    "execution_token_budget": (snapshot["execution"] as? [String: Any])?["tokenBudget"] ?? NSNull(),
                    "execution_token_used": (snapshot["execution"] as? [String: Any])?["tokenUsed"] ?? NSNull(),
                    "execution_error": (snapshot["execution"] as? [String: Any])?["errorMessage"] ?? NSNull(),
                    "execution_nodes": ((snapshot["execution"] as? [String: Any])?["nodes"] as? [[String: Any]] ?? []).map { node in
                        node.filter { ["nodeId", "node_id", "name", "status", "attempt", "tokenUsed", "token_used", "apiCalls", "api_calls", "maxTokens", "errorMessage"].contains($0.key) }
                    },
                    "artifact_id": (snapshot["artifact"] as? [String: Any])?["id"] ?? NSNull(),
                    "content": snapshot["content"] ?? NSNull(), "offline": api.isOfflineMode
                ]
                if ProcessInfo.processInfo.arguments.contains("-travelLiveEvidence"),
                   let data = try? JSONSerialization.data(withJSONObject: evidence, options: [.sortedKeys]),
                   data.count <= 6 * 1024 * 1024,
                   let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first {
                    try? data.write(to: folder.appendingPathComponent("travel-live-last-snapshot.json"),
                                    options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
                }
                #endif
                return snapshot
            }
            if operation == "respond" {
                return try object(await api.respondToWorkflowClarification(workflowId: workflow.id,
                    response: string(body, "response"), expectedRound: body["round"] as? Int))
            }
            if operation == "approvePlan" {
                guard let revision = body["revision"] as? Int else { throw APIError.network("计划版本缺失") }
                if uiKind != "travel" {
                    let plan = try await api.fetchWorkflowPlan(workflowId: workflow.id)
                    let expectedHash = try string(body, "hash")
                    guard plan.contentHash == expectedHash, plan.activationRevision == revision else {
                        throw APIError.network("计划已变化，请重新查看后确认")
                    }
                    return try object(await api.approveWorkflowPlan(workflowId: workflow.id, requestId: UUID().uuidString))
                }
                return try object(await api.confirmTravelWorkflowPlan(workflowId: workflow.id,
                    expectedHash: string(body, "hash"), expectedRevision: revision, clientSessionId: parent.scope.clientSessionId))
            }
            if operation == "retryPlanning" {
                guard workflow.status == "needs_attention" else { throw APIError.network("当前计划无需重试，请重新读取状态") }
                return try object(await api.retryWorkflowPlanning(workflowId: workflow.id))
            }
            if operation == "start" {
                guard let revision = body["revision"] as? Int else { throw APIError.network("计划版本缺失") }
                return try object(await api.startWorkflow(workflowId: workflow.id, requestId: string(body, "requestId"), expectedHash: string(body, "hash"), expectedRevision: revision))
            }
            guard let executionId = body["executionId"] as? String else { throw APIError.network("执行版本缺失") }
            let execution = try await api.fetchWorkflowExecution(id: executionId)
            guard execution.workflowId == workflow.id else { throw APIError.network("执行不属于当前任务") }
            if !["versions", "version", "artifactContent", "shareArtifact"].contains(operation),
               workflow.latestExecution?.id != execution.id { throw APIError.network("执行已有新版本，请重新读取后确认") }
            try checkScope()
            if operation == "retryExecution" {
                guard ["failed", "cancelled"].contains(execution.status) else { throw APIError.network("当前任务无需重试，请重新读取状态") }
                return try object(await api.retryWorkflowExecution(id: executionId))
            }
            if operation == "printNotebook" {
                guard uiKind == "travel", execution.status == "completed" else { throw APIError.network("请先采用并保存旅行手记") }
                let identifier = try string(body, "artifactId"), hash = try string(body, "hash")
                let artifacts = try await api.fetchWorkflowArtifacts(executionId: execution.id)
                guard let artifact = artifacts.filter({ $0.metadata.renderType == "travel_plan_v2" }).max(by: {
                    if ($0.metadata.travelRevision ?? 0) != ($1.metadata.travelRevision ?? 0) { return ($0.metadata.travelRevision ?? 0) < ($1.metadata.travelRevision ?? 0) }
                    return ($0.createdAt ?? "") < ($1.createdAt ?? "")
                }), artifact.id == identifier, artifact.contentHash == hash else { throw APIError.network("手记已有新版本，请重新读取后导出") }
                let content = try await api.fetchWorkflowArtifactContent(executionId: execution.id, artifactId: identifier)
                guard content.id == identifier, SHA256.hash(data: Data(content.content.utf8)).map({ String(format: "%02x", $0) }).joined() == hash,
                      let document = try JSONSerialization.jsonObject(with: Data(content.content.utf8)) as? [String: Any] else { throw APIError.network("旅行手记内容校验失败") }
                try checkScope()
                let pretty = try JSONSerialization.data(withJSONObject: document, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
                let text = workflow.title + "\n旅行手记 · 文字归档\n来源版本：" + hash + "\n照片与手记版式可在应用内查看。\n\n" + (String(data: pretty, encoding: .utf8) ?? "")
                let data = try TravelNotebookPDF.render(text)
                let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                let file = folder.appendingPathComponent("旅行手记-文字版.pdf")
                try data.write(to: file, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
                guard let window = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).flatMap(\.windows).first(where: \.isKeyWindow), var host = window.rootViewController else { throw APIError.network("分享窗口不可用") }
                while let presented = host.presentedViewController { host = presented }
                let share = UIActivityViewController(activityItems: [file], applicationActivities: nil)
                share.popoverPresentationController?.sourceView = host.view
                share.popoverPresentationController?.sourceRect = CGRect(x: host.view.bounds.midX, y: host.view.bounds.midY, width: 1, height: 1)
                host.present(share, animated: true)
                return ["opened": true]
            }
            if operation == "artifactContent" {
                let identifier = try string(body, "artifactId"), hash = try string(body, "hash")
                let artifacts = try await api.fetchWorkflowArtifacts(executionId: executionId)
                guard let artifact = artifacts.first(where: { $0.id == identifier && $0.contentHash == hash }) else {
                    throw APIError.network("成果已变化，请重新读取")
                }
                let textArtifact = ["md", "txt", "json", "csv", "html"].contains(artifact.extension.lowercased())
                if !textArtifact {
                    // A PDF/Office preview is derived text. Verify the original
                    // bytes rather than comparing its text digest to a binary hash.
                    _ = try await api.downloadAuthenticated(path: "workflow-executions/\(execution.id)/artifacts/\(artifact.id)/download", expectedHash: hash)
                }
                let content = try await api.fetchWorkflowArtifactContent(executionId: executionId, artifactId: identifier)
                let digest = SHA256.hash(data: Data(content.content.utf8)).map { String(format: "%02x", $0) }.joined()
                guard content.id == identifier, !textArtifact || digest == hash else { throw APIError.network("成果内容校验失败，请重新读取") }
                #if DEBUG
                if ProcessInfo.processInfo.arguments.contains("-travelLiveEvidence"),
                   let data = try? JSONSerialization.data(withJSONObject: ["workflow_id": workflow.id, "execution_id": executionId,
                       "artifact_id": identifier, "content_hash": hash, "title": content.title, "content": content.content], options: [.sortedKeys]),
                   data.count <= 6 * 1024 * 1024,
                   let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first {
                    try? data.write(to: folder.appendingPathComponent("travel-live-viewed-artifact.json"),
                                    options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
                }
                #endif
                return try object(content)
            }
            if operation == "shareArtifact" {
                let identifier = try string(body, "artifactId"), hash = try string(body, "hash")
                let artifacts = try await api.fetchWorkflowArtifacts(executionId: executionId)
                guard let artifact = artifacts.first(where: { $0.id == identifier && $0.contentHash == hash }) else {
                    throw APIError.network("成果已变化，请重新读取后导出")
                }
                let data = try await api.downloadAuthenticated(path: "workflow-executions/\(execution.id)/artifacts/\(artifact.id)/download", expectedHash: hash)
                try checkScope()
                guard data.count <= 25 * 1024 * 1024 else { throw APIError.network("成果文件超过 25 MB") }
                let suffix = artifact.extension.lowercased()
                guard suffix.range(of: "^[a-z0-9]{1,12}$", options: .regularExpression) != nil else { throw APIError.network("文件类型无效") }
                let name = String(artifact.title.prefix(80)).components(separatedBy: CharacterSet(charactersIn: "/\\:\n\r")).joined(separator: "_")
                let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                let file = folder.appendingPathComponent((name.isEmpty ? "Quantum" : name) + "." + suffix)
                try data.write(to: file, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
                let share = UIActivityViewController(activityItems: [file], applicationActivities: nil)
                guard let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
                      let window = scene.windows.first(where: \.isKeyWindow), var host = window.rootViewController else { throw APIError.network("分享窗口不可用") }
                while let presented = host.presentedViewController { host = presented }
                share.popoverPresentationController?.sourceView = host.view
                share.popoverPresentationController?.sourceRect = CGRect(x: host.view.bounds.midX, y: host.view.bounds.midY, width: 1, height: 1)
                host.present(share, animated: true)
                return ["opened": true]
            }
            if operation == "versions" { return try object(await api.fetchWorkflowArtifacts(executionId: executionId).filter { $0.metadata.renderType == "travel_plan_v2" }) }
            if operation == "version" {
                let identifier = try string(body, "artifactId"), hash = try string(body, "hash")
                let artifacts = try await api.fetchWorkflowArtifacts(executionId: executionId)
                guard artifacts.contains(where: { $0.id == identifier && $0.contentHash == hash && $0.metadata.renderType == "travel_plan_v2" }) else {
                    throw APIError.network("版本不存在或内容已变化")
                }
                return ["content": try await api.fetchWorkflowArtifactContent(executionId: executionId, artifactId: identifier).content]
            }
            if operation == "reviewArtifact" {
                let identifier = try string(body, "artifactId"), hash = try string(body, "hash")
                let artifacts = try await api.fetchWorkflowArtifacts(executionId: executionId)
                guard let artifact = artifacts.first(where: { $0.id == identifier }), artifact.contentHash == hash else {
                    throw APIError.network("成果已更新，请查看新版本后确认")
                }
                let decision = body["decision"] as? String ?? "approve"
                guard ["approve", "revise"].contains(decision) else { throw APIError.invalidURL }
                return try object(await api.reviewPresentationStage(executionId: executionId, artifact: artifact,
                    decision: decision, comment: body["comment"] as? String ?? "用户确认当前成稿"))
            }
            if operation == "approveOutput" {
                guard let ids = body["artifactIds"] as? [String], !ids.isEmpty,
                      let hashes = body["expectedHashes"] as? [String: String], hashes.count == ids.count,
                      Set(ids).count == ids.count else { throw APIError.network("成果版本缺失") }
                let artifacts = try await api.fetchWorkflowArtifacts(executionId: executionId)
                guard ids.allSatisfy({ id in artifacts.contains { $0.id == id && $0.contentHash == hashes[id] } }) else {
                    throw APIError.network("成果已更新，请重新查看后采用")
                }
                let latestTravel = artifacts.filter { $0.metadata.renderType == "travel_plan_v2" }.sorted {
                    if ($0.metadata.travelRevision ?? 0) != ($1.metadata.travelRevision ?? 0) { return ($0.metadata.travelRevision ?? 0) > ($1.metadata.travelRevision ?? 0) }
                    if ($0.metadata.approvalGate == nil) != ($1.metadata.approvalGate == nil) { return $0.metadata.approvalGate == nil }
                    if $0.createdAt != $1.createdAt { return ($0.createdAt ?? "") > ($1.createdAt ?? "") }
                    return $0.id > $1.id
                }.first
                if let latestTravel, !ids.contains(latestTravel.id) { throw APIError.network("请采用最新的旅行成稿") }
                if execution.status == "completed" { return ["approved": true, "recovered": true] }
                try await api.approveWorkflowOutput(executionId: executionId, artifactIds: ids)
                return ["approved": true]
            }
            if operation == "saveNotebook" {
                let result = try await api.performTravelCapability("travel.notebook.save", input: [
                    "execution_id": executionId, "artifact_id": try string(body, "artifactId"), "expected_hash": try string(body, "hash")],
                    sessionId: parent.scope.clientSessionId, requestId: try string(body, "requestId"))
                guard let receipt = result["note"] as? [String: Any], let noteID = receipt["note_id"] as? String,
                      let hash = receipt["content_hash"] as? String else { throw APIError.network("没有收到笔记保存回执") }
                let note = try await api.readTravelNotebook(id: noteID)
                guard note.contentHash == hash else { throw APIError.network("笔记已变化，请重新读取") }
                try checkScope()
                _ = await KnowledgeNoteStore.shared.restoreFromCloud()
                try checkScope()
                boundNoteID = noteID; boundWorkflowID = workflow.id
                TravelExpenseDraftQueue.bind(noteID: noteID)
                return ["noteId": noteID, "contentHash": hash, "content": try notebookContent(note.markdown)]
            }
            let artifactId = try string(body, "artifactId"), hash = try string(body, "hash"), requestId = try string(body, "requestId")
            let receipt: TravelRevisionReceipt
            switch operation {
            case "saveState":
                guard let state = body["state"] as? [String: Any] else { throw APIError.network("旅行记录无效") }
                receipt = try await api.saveTravelClientState(executionId: executionId, artifactId: artifactId, expectedHash: hash,
                    state: state, requestId: requestId)
            case "revise":
                receipt = try await api.reviseTravelPlan(executionId: executionId, artifactId: artifactId, expectedHash: hash,
                    content: string(body, "content"), reason: string(body, "reason"), requestId: requestId,
                    confirmedBookings: body["confirmedBookings"] as? [String: String] ?? [:])
            case "progress":
                receipt = try await api.recordTravelProgress(executionId: executionId, artifactId: artifactId, expectedHash: hash,
                    actionId: string(body, "actionId"), progress: string(body, "progress"), requestId: requestId)
            default: throw APIError.network("不支持的客户端操作")
            }
            return ["id": receipt.id, "contentHash": receipt.contentHash]
        }

        private func notebookContent(_ markdown: String) throws -> String {
            let raw: String
            if let start = markdown.range(of: "```json"), let end = markdown.range(of: "```", range: start.upperBound..<markdown.endIndex) {
                raw = String(markdown[start.upperBound..<end.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
            } else { raw = markdown.trimmingCharacters(in: .whitespacesAndNewlines) }
            guard let value = try JSONSerialization.jsonObject(with: Data(raw.utf8)) as? [String: Any],
                  value["schema_version"] as? Int == 2 else { throw APIError.network("笔记没有可读取的旅行内容") }
            return raw
        }

        private func notebookSnapshot(_ id: String) async throws -> [String: Any] {
            let note = try await APIClient.shared.readTravelNotebook(id: id)
            try checkScope()
            TravelExpenseDraftQueue.bind(noteID: id)
            let content = try notebookContent(note.markdown)
            let document = try JSONSerialization.jsonObject(with: Data(content.utf8)) as? [String: Any] ?? [:]
            return ["noteId": id, "noteMode": true,
                "workflow": ["id": document["workflow_id"] ?? id, "title": document["destination"] ?? "旅行手记", "status": "ready", "uiKind": "travel"],
                "artifact": ["id": id, "contentHash": note.contentHash], "content": content, "offline": false]
        }

        private func performNotebook(_ operation: String, id: String, body: [String: Any]) async throws -> Any {
            let api = APIClient.shared
            if operation == "snapshot" { return try await notebookSnapshot(id) }
            let note = try await api.readTravelNotebook(id: id)
            let content = try notebookContent(note.markdown)
            if operation == "saveNotebook" { return ["noteId": id, "contentHash": note.contentHash, "content": content] }
            if operation == "printNotebook" {
                guard note.contentHash == (try string(body, "hash")) else { throw APIError.network("笔记已更新，请重新读取后导出") }
                let file = FileManager.default.temporaryDirectory.appendingPathComponent("旅行手记-" + UUID().uuidString + ".pdf")
                try TravelNotebookPDF.render(content).write(to: file, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
                try presentShare(file)
                return ["opened": true]
            }
            if operation == "versions" || operation == "version" {
                var input: [String: JSONScalar] = ["note_id": .string(id), "include_versions": .bool(true)]
                if operation == "version" { input["version_hash"] = .string(try string(body, "hash")) }
                let response: QCPInvokeResponseDTO<JSONScalar> = try await CapabilityClient(apiClient: api).invoke("knowledge.note.read", input: input)
                guard response.status == "completed", let result = response.events.first?.payload,
                      let value = try object(result) as? [String: Any] else { throw APIError.network(response.error?.message ?? "版本读取失败") }
                if operation == "version", let selected = value["note"] as? [String: Any], let markdown = selected["markdown"] as? String {
                    return ["content": try notebookContent(markdown)]
                }
                return (value["versions"] as? [[String: Any]] ?? []).enumerated().map { index, row in
                    ["id": row["content_hash"] ?? "", "contentHash": row["content_hash"] ?? "", "createdAt": row["updated_at"] ?? "",
                     "title": "旅行笔记", "metadata": ["travelRevision": 50 - index, "changeReason": row["change_reason"] ?? "过去的安排"]] as [String: Any]
                }
            }
            var input: [String: Any] = ["note_id": id, "expected_note_hash": try string(body, "hash"), "reason": body["reason"] as? String ?? "用户保存旅行手记"]
            switch operation {
            case "saveState": input["client_state"] = body["state"]
            case "revise":
                input["proposed"] = try JSONSerialization.jsonObject(with: Data(string(body, "content").utf8))
                input["confirmed_bookings"] = body["confirmedBookings"] ?? [:]
            case "progress": input["action_id"] = try string(body, "actionId"); input["progress"] = try string(body, "progress")
            default: throw APIError.network("不支持的笔记操作")
            }
            let result = try await api.performTravelCapability("travel.notebook.update", input: input,
                sessionId: parent.activities.currentScope?.clientSessionId ?? parent.scope.clientSessionId, requestId: string(body, "requestId"))
            guard let updated = result["note"] as? [String: Any], updated["note_id"] as? String == id, let hash = updated["content_hash"] as? String else { throw APIError.network("没有笔记保存回执") }
            let stored = try await api.readTravelNotebook(id: id)
            guard stored.contentHash == hash else { throw APIError.network("保存后笔记已变化，请读取新版本") }
            try checkScope()
            _ = await KnowledgeNoteStore.shared.restoreFromCloud()
                try checkScope()
            if operation == "saveState", let document = try JSONSerialization.jsonObject(with: Data(notebookContent(stored.markdown).utf8)) as? [String: Any] {
                try TravelExpenseDraftQueue.acknowledge(noteID: id, document: document)
            }
            return ["id": id, "contentHash": hash, "content": try notebookContent(stored.markdown)]
        }

        private func presentShare(_ file: URL) throws {
            guard let window = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).flatMap(\.windows).first(where: \.isKeyWindow), var host = window.rootViewController else { throw APIError.network("分享窗口不可用") }
            while let presented = host.presentedViewController { host = presented }
            let share = UIActivityViewController(activityItems: [file], applicationActivities: nil)
            share.popoverPresentationController?.sourceView = host.view
            share.popoverPresentationController?.sourceRect = CGRect(x: host.view.bounds.midX, y: host.view.bounds.midY, width: 1, height: 1)
            host.present(share, animated: true)
        }

        func webView(_ webView: WKWebView, start urlSchemeTask: WKURLSchemeTask) {
            let key = ObjectIdentifier(urlSchemeTask as AnyObject)
            mediaTasks[key] = Task {
                defer { mediaTasks.removeValue(forKey: key) }
                do {
                    try checkScope()
                    guard let url = urlSchemeTask.request.url, ["image", "audio"].contains(url.host ?? "") else { throw APIError.invalidURL }
                    let identifier = String(url.path.dropFirst())
                    guard identifier.range(of: "^[a-zA-Z0-9_-]{1,100}$", options: .regularExpression) != nil else { throw APIError.invalidURL }
                    let receipt = try await APIClient.shared.fetchImageReceipt(id: identifier)
                    let bytes = try await APIClient.shared.downloadAuthenticated(path: receipt.downloadPath, expectedHash: receipt.contentHash)
                    try checkScope()
                    let mime = url.host == "image" ? (receipt.filename.lowercased().hasSuffix(".png") ? "image/png" : receipt.filename.lowercased().hasSuffix(".webp") ? "image/webp" : "image/jpeg") : (receipt.filename.hasSuffix(".wav") ? "audio/wav" : receipt.filename.hasSuffix(".webm") ? "audio/webm" : receipt.filename.hasSuffix(".ogg") ? "audio/ogg" : "audio/mp4")
                    urlSchemeTask.didReceive(URLResponse(url: url, mimeType: mime, expectedContentLength: bytes.count, textEncodingName: nil))
                    urlSchemeTask.didReceive(bytes)
                    urlSchemeTask.didFinish()
                } catch { if !Task.isCancelled { urlSchemeTask.didFailWithError(error) } }
            }
        }

        func webView(_ webView: WKWebView, stop urlSchemeTask: WKURLSchemeTask) {
            let key = ObjectIdentifier(urlSchemeTask as AnyObject)
            mediaTasks.removeValue(forKey: key)?.cancel()
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
            if url.isFileURL, let root, url.standardizedFileURL.path.hasPrefix(root.standardizedFileURL.path + "/") {
                decisionHandler(.allow)
            } else {
                decisionHandler(.cancel)
                if ["https", "http"].contains(url.scheme?.lowercased() ?? ""), navigationAction.navigationType == .linkActivated {
                    UIApplication.shared.open(url)
                }
            }
        }
    }
}

#if DEBUG
struct TravelSpacePreviewHost: View {
    @StateObject private var activities: WorkflowActivityCoordinator
    @StateObject private var state = AppState()
    init() {
        let value = WorkflowActivityCoordinator()
        value.activate(tenantKey: "ui-test", userId: "preview")
        value.selectClientSession("travel-space-preview")
        _activities = StateObject(wrappedValue: value)
    }
    var body: some View {
        VStack(spacing: 0) {
            if state.activeTab == 1 { TravelSpaceView() }
            else if state.activeTab == 2 { KnowledgeView() }
            else if state.activeTab == 3 { SettingsView().environmentObject(APIClient.shared) }
            else {
                ScrollView { LearningWelcomeView(resume: nil, resumeStatus: "登录后同步阅读进度", onAction: { _ in state.activeTab = 2 }) }
            }
            QuantumFloatingTabBar(selection: $state.activeTab).padding(.bottom, 6)
        }
        .background(QuantumMistBackground())
        .environmentObject(state).environmentObject(activities)
        .onAppear { state.activeTab = 1 }
    }
}
#endif

// Text archive export paginates the entire Unicode string. No WebKit printing,
// external resource loading or clipping of a scroll viewport is involved.
enum TravelNotebookPDF {
    static func render(_ text: String) throws -> Data {
        guard !text.isEmpty, text.utf8.count <= 4 * 1024 * 1024 else { throw APIError.network("文字归档过大，请分次导出") }
        let value = NSAttributedString(string: text, attributes: [.font: UIFont.systemFont(ofSize: 11), .foregroundColor: UIColor.darkGray])
        let framesetter = CTFramesetterCreateWithAttributedString(value)
        let bounds = CGRect(x: 0, y: 0, width: 595, height: 842)
        var offset = 0, pages = 0
        let data = UIGraphicsPDFRenderer(bounds: bounds).pdfData { renderer in
            while offset < value.length && pages < 2000 {
                renderer.beginPage(); pages += 1
                let context = renderer.cgContext
                context.saveGState(); context.textMatrix = .identity
                context.translateBy(x: 0, y: bounds.height); context.scaleBy(x: 1, y: -1)
                let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: offset, length: 0), CGPath(rect: bounds.insetBy(dx: 36, dy: 44), transform: nil), nil)
                let visible = CTFrameGetVisibleStringRange(frame)
                guard visible.length > 0 else { context.restoreGState(); break }
                CTFrameDraw(frame, context); context.restoreGState()
                offset += visible.length
                ("Quantum · " + String(pages)).draw(at: CGPoint(x: 36, y: 814), withAttributes: [.font: UIFont.systemFont(ofSize: 9), .foregroundColor: UIColor.gray])
            }
        }
        guard offset == value.length else { throw APIError.network("文字归档未完整分页，未导出不完整文件") }
        return data
    }
}
