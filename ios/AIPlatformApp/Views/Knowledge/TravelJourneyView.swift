import SwiftUI
import WebKit
import MapKit
import SceneKit

// Native, offline position globe. No road geometry or transit claims are inferred.
struct TravelGlobeView: View {
    let stops: [TravelRouteStop]
    @State private var scene: SCNScene?
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let scene {
                SceneView(scene: scene, options: [.allowsCameraControl, .autoenablesDefaultLighting])
                    .frame(height: 300)
                    .clipShape(RoundedRectangle(cornerRadius: 24))
                    .accessibilityLabel("可旋转的全球目的地位置示意图")
            } else { ProgressView().frame(height: 300) }
            Text("拖动旋转 · 双指缩放 · 位置示意，不含地形与实际道路")
                .font(.caption).foregroundStyle(.secondary)
            ForEach(Array(stops.enumerated()), id: \.offset) { index, stop in
                Text("\(index + 1)  \(stop.name)" + (stop.coordinate == nil ? " · 坐标待核实" : ""))
                    .font(.subheadline)
            }
        }.task(id: stops) { scene = makeScene() }
    }

    private func makeScene() -> SCNScene {
        let scene = SCNScene()
        scene.background.contents = UIColor(red: 0.035, green: 0.10, blue: 0.15, alpha: 1)
        let sphere = SCNSphere(radius: 1)
        sphere.segmentCount = 64
        sphere.firstMaterial?.diffuse.contents = UIColor(red: 0.08, green: 0.23, blue: 0.28, alpha: 1)
        sphere.firstMaterial?.roughness.contents = 0.85
        scene.rootNode.addChildNode(SCNNode(geometry: sphere))
        func point(_ latitude: Double, _ longitude: Double, radius: Double = 1.008) -> SCNVector3 {
            let lat = latitude * .pi / 180, lon = longitude * .pi / 180
            return SCNVector3(Float(radius * cos(lat) * sin(lon)), Float(radius * sin(lat)), Float(radius * cos(lat) * cos(lon)))
        }
        func line(_ points: [SCNVector3], color: UIColor) {
            guard points.count > 1 else { return }
            let indices = (0..<(points.count - 1)).flatMap { [Int32($0), Int32($0 + 1)] }
            let geometry = SCNGeometry(sources: [SCNGeometrySource(vertices: points)], elements: [SCNGeometryElement(indices: indices, primitiveType: .line)])
            geometry.firstMaterial?.diffuse.contents = color
            geometry.firstMaterial?.lightingModel = .constant
            scene.rootNode.addChildNode(SCNNode(geometry: geometry))
        }
        for latitude in stride(from: -60.0, through: 60.0, by: 30) {
            line(stride(from: -180.0, through: 180.0, by: 4).map { point(latitude, $0) }, color: .systemTeal.withAlphaComponent(0.35))
        }
        for longitude in stride(from: -180.0, to: 180.0, by: 30) {
            line(stride(from: -90.0, through: 90.0, by: 3).map { point($0, longitude) }, color: .systemTeal.withAlphaComponent(0.35))
        }
        let located = stops.compactMap(\.coordinate)
        for (from, to) in zip(located, located.dropFirst()) {
            let delta = (to.longitude - from.longitude + 540).truncatingRemainder(dividingBy: 360) - 180
            let arc = (0...48).map { step -> SCNVector3 in
                let fraction = Double(step) / 48
                return point(from.latitude + (to.latitude - from.latitude) * fraction,
                             from.longitude + delta * fraction, radius: 1.025 + 0.12 * sin(.pi * fraction))
            }
            line(arc, color: .systemOrange)
        }
        for location in located {
            let pin = SCNSphere(radius: 0.018)
            pin.firstMaterial?.diffuse.contents = UIColor.systemOrange
            pin.firstMaterial?.lightingModel = .constant
            let node = SCNNode(geometry: pin)
            node.position = point(location.latitude, location.longitude, radius: 1.025)
            scene.rootNode.addChildNode(node)
        }
        let camera = SCNNode()
        camera.camera = SCNCamera()
        camera.camera?.fieldOfView = 45
        let focus = located.first ?? CLLocationCoordinate2D(latitude: 25, longitude: 100)
        camera.position = point(focus.latitude, focus.longitude, radius: 3.4)
        camera.look(at: SCNVector3Zero)
        scene.rootNode.addChildNode(camera)
        return scene
    }
}


// A rendering snapshot of the existing plan; never saves or rewrites its content.
struct TravelJourneyPayload: Encodable {
    struct Stop: Encodable {
        let name: String
        let coordinate: [Double]
    }
    struct Leg: Encodable {
        let from: Int
        let to: Int
        let title: String
    }
    let title: String
    let destination: String
    let stops: [Stop]
    let legs: [Leg]
    let unlocatedCount: Int

    init(title: String, plan: TravelPlanDocument) {
        self.title = title
        destination = plan.destination ?? "我的旅行"
        let ordered = plan.orderedStops
        var locations: [Stop] = []
        var indices: [String: Int] = [:]
        for stop in ordered where indices[stop.id] == nil {
            guard let coordinate = stop.coordinate else { continue }
            indices[stop.id] = locations.count
            locations.append(.init(name: stop.name, coordinate: [coordinate.longitude, coordinate.latitude]))
        }
        stops = locations
        // Missing coordinates break a leg rather than connecting unrelated places across the gap.
        legs = zip(ordered, ordered.dropFirst()).compactMap { from, to in
            guard from.coordinate != nil, to.coordinate != nil, let a = indices[from.id], let b = indices[to.id], a != b else { return nil }
            return Leg(from: a, to: b, title: "\(to.name)，把脚步放慢")
        }
        unlocatedCount = ordered.filter { $0.coordinate == nil }.count
    }

    var json: String? {
        guard let bytes = try? JSONEncoder().encode(self), let json = String(data: bytes, encoding: .utf8) else { return nil }
        return json.replacingOccurrences(of: "<", with: "\\u003c")
            .replacingOccurrences(of: ">", with: "\\u003e")
            .replacingOccurrences(of: "&", with: "\\u0026")
    }
}

struct TravelJourneyView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    let title: String
    let plan: TravelPlanDocument
    @State private var error: String?
    @State private var ready = false
    @State private var reloadID = UUID()
    @State private var offline = false
    private var payload: TravelJourneyPayload { .init(title: title, plan: plan) }

    var body: some View {
        ZStack {
            AppTheme.Colors.mistSky.ignoresSafeArea()
            if payload.stops.isEmpty {
                ContentUnavailableView("地点还没有坐标", systemImage: "mappin.slash",
                                       description: Text("先在行程中核实地点。原笔记与记录都已保留。"))
            } else if offline {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        Text("旅行的坐标").font(.system(.largeTitle, design: .serif))
                        TravelGlobeView(stops: plan.orderedStops)
                        Button("重新打开全屏地图") { retry() }.buttonStyle(.borderedProminent)
                    }.padding(24).padding(.top, 44)
                }
            } else {
                TravelJourneyWebView(payload: payload, active: scenePhase == .active,
                                     onClose: { dismiss() }, onReady: { ready = true; error = nil },
                                     onError: { error = $0 })
                    .id(reloadID).ignoresSafeArea()
                if let error {
                    VStack(spacing: 16) {
                        Image(systemName: "globe.asia.australia").font(.system(size: 44))
                        Text("旅行小世界暂时没打开").font(.system(.title2, design: .serif))
                        Text(error).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                        Button("重新加载", action: retry).buttonStyle(.borderedProminent)
                        Button("查看离线位置") { offline = true }.buttonStyle(.bordered)
                    }
                    .padding(28).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 28)).padding(24)
                } else if !ready {
                    ProgressView("正在打开旅行小世界…")
                        .padding(24).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20))
                        .accessibilityIdentifier("travel-journey-loading")
                }
            }
        }
        .overlay(alignment: .topTrailing) {
            if !ready || offline || payload.stops.isEmpty || error != nil {
                Button { dismiss() } label: {
                    Image(systemName: "xmark").font(.headline).frame(width: 44, height: 44)
                        .background(.regularMaterial, in: Circle())
                }
                .accessibilityLabel("关闭旅行地图").accessibilityIdentifier("travel-journey-close")
                .padding(16)
            }
        }
        .statusBarHidden(ready && !offline && error == nil)
        .tint(AppTheme.Colors.primary)
    }

    private func retry() { error = nil; ready = false; offline = false; reloadID = UUID() }
}

private struct TravelJourneyWebView: UIViewRepresentable {
    let payload: TravelJourneyPayload
    let active: Bool
    let onClose: () -> Void
    let onReady: () -> Void
    let onError: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIView(context: Context) -> WKWebView {
        let controller = WKUserContentController()
        controller.add(context.coordinator, name: "journey")
        let config = WKWebViewConfiguration()
        config.userContentController = controller
        config.websiteDataStore = .nonPersistent()
        let web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = context.coordinator
        web.isOpaque = false
        web.backgroundColor = UIColor(AppTheme.Colors.mistSky)
        web.scrollView.isScrollEnabled = false
        web.scrollView.contentInsetAdjustmentBehavior = .never
        context.coordinator.web = web
        guard let htmlURL = Bundle.main.url(forResource: "journey", withExtension: "html", subdirectory: "TravelJourney") ?? Bundle.main.url(forResource: "journey", withExtension: "html"),
              let scriptURL = Bundle.main.url(forResource: "journey", withExtension: "js", subdirectory: "TravelJourney") ?? Bundle.main.url(forResource: "journey", withExtension: "js"),
              let html = try? String(contentsOf: htmlURL, encoding: .utf8),
              let script = try? String(contentsOf: scriptURL, encoding: .utf8), let json = payload.json else {
            DispatchQueue.main.async { onError("地图资源缺失，请重新安装当前版本。") }
            return web
        }
        // JSON is escaped and inserted as data. Note text never becomes executable source.
        let source = "<script>window.quantumJourney=\(json);</script><script type=\"module\">\(script)</script>"
        web.loadHTMLString(html.replacingOccurrences(of: "<!--JOURNEY_SCRIPT-->", with: source),
                           baseURL: URL(string: "https://quantum-travel.invalid/"))
        context.coordinator.timeout = Task { @MainActor in
            try? await Task.sleep(for: .seconds(35))
            guard !Task.isCancelled, !context.coordinator.ready else { return }
            onError("网络较慢或设备暂不支持三维地图，可以重试或查看离线位置。")
        }
        return web
    }
    func updateUIView(_ web: WKWebView, context: Context) {
        context.coordinator.parent = self
        if !active { web.evaluateJavaScript("window.pauseJourney?.()", completionHandler: nil) }
    }
    static func dismantleUIView(_ web: WKWebView, coordinator: Coordinator) {
        coordinator.cancel()
        web.evaluateJavaScript("window.pauseJourney?.()", completionHandler: nil)
        web.configuration.userContentController.removeScriptMessageHandler(forName: "journey")
        web.navigationDelegate = nil
        web.stopLoading()
    }

    @MainActor final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
        var parent: TravelJourneyWebView
        weak var web: WKWebView?
        var ready = false
        var timeout: Task<Void, Never>?
        var routeTask: Task<Void, Never>?
        var directions: MKDirections?
        init(_ parent: TravelJourneyWebView) { self.parent = parent }
        func cancel() { timeout?.cancel(); routeTask?.cancel(); directions?.cancel() }
        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.frameInfo.isMainFrame, let body = message.body as? [String: Any], let type = body["type"] as? String else { return }
            switch type {
            case "close": parent.onClose()
            case "ready": ready = true; timeout?.cancel(); parent.onReady()
            case "error": parent.onError("地图连接失败，请检查网络后重试。")
            case "route":
                guard let leg = body["leg"] as? Int, parent.payload.legs.indices.contains(leg),
                      let mode = body["mode"] as? String, ["car", "walk"].contains(mode),
                      let requestID = body["requestID"] as? Int, requestID >= 0 else { return }
                route(leg: leg, mode: mode, requestID: requestID)
            default: break
            }
        }
        func route(leg index: Int, mode: String, requestID: Int) {
            routeTask?.cancel(); directions?.cancel()
            let leg = parent.payload.legs[index]
            func coordinate(_ index: Int) -> CLLocationCoordinate2D {
                let p = parent.payload.stops[index].coordinate
                return .init(latitude: p[1], longitude: p[0])
            }
            let request = MKDirections.Request()
            request.source = MKMapItem(placemark: MKPlacemark(coordinate: coordinate(leg.from)))
            request.destination = MKMapItem(placemark: MKPlacemark(coordinate: coordinate(leg.to)))
            request.transportType = mode == "car" ? .automobile : .walking
            let directions = MKDirections(request: request)
            self.directions = directions
            routeTask = Task { @MainActor [weak self] in
                var points: [[Double]] = []
                do {
                    let result = try await directions.calculate()
                    if let route = result.routes.first {
                        var coordinates = Array(repeating: CLLocationCoordinate2D(), count: route.polyline.pointCount)
                        route.polyline.getCoordinates(&coordinates, range: NSRange(location: 0, length: coordinates.count))
                        points = coordinates.map { [$0.longitude, $0.latitude] }
                    }
                } catch { /* Keep the illustrative route; don't present a false road. */ }
                guard !Task.isCancelled, let self, let web = self.web else { return }
                try? await web.callAsyncJavaScript("window.applyJourneyRoute(result)",
                                                  arguments: ["result": ["requestID": requestID, "points": points]],
                                                  in: nil, contentWorld: .page)
            }
        }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            parent.onError("地图页面未能加载，请重试。")
        }
        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            parent.onError("地图已暂停，重新加载即可继续。")
        }
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            // This screen never loads arbitrary note/source URLs or shares the app's authenticated session.
            if action.navigationType == .linkActivated {
                if let url = action.request.url, url.scheme == "https",
                   ["openfreemap.org", "www.openmaptiles.org", "www.openstreetmap.org"].contains(url.host ?? "") {
                    UIApplication.shared.open(url)
                }
                decisionHandler(.cancel)
            } else if action.request.url?.scheme == "about" || action.request.url?.host == "quantum-travel.invalid" {
                decisionHandler(.allow)
            } else { decisionHandler(.cancel) }
        }
    }
}
