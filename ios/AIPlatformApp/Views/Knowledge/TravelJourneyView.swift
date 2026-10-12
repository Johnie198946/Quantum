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

    init(title: String, plan: TravelPlanDocument, resolvedStops: [TravelRouteStop]? = nil) {
        self.title = title
        destination = plan.destination ?? "我的旅行"
        let ordered = resolvedStops ?? plan.orderedStops
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

// Journey screens and map interactions now live in the approved travel-space renderer.
// TravelJourneyPayload remains the stable domain representation for exports and compatibility.
