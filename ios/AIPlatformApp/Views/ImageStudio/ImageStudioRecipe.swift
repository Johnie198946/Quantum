import Foundation

/// PCM media.process studio v1. Coordinates are normalized, top-left origin.
public struct ImageStudioPoint: Codable, Hashable, Sendable {
    public var x: Double
    public var y: Double
}
public struct ImageStudioCrop: Codable, Hashable, Sendable {
    public var corners: [ImageStudioPoint]
    public var width: Int
    public var height: Int
}
public struct ImageStudioStroke: Codable, Hashable, Sendable, Identifiable {
    public var id = UUID().uuidString
    public var points: [ImageStudioPoint] = []
    public var radius: Double = 0.015
}
public struct ImageStudioLayer: Codable, Hashable, Sendable, Identifiable {
    public var id = UUID().uuidString
    public var kind = "text"
    public var text = "把日子过成诗"
    public var assetId: String? = nil
    public var font = "serif"
    public var fontSize: Double = 0.12
    public var color = "FFF7EC"
    public var x: Double = 0.5
    public var y: Double = 0.2
    public var width: Double = 0.85
    public var rotation: Double = 0
    public var opacity: Double = 1
    public var visible = true
    public var locked = false
    public var alignment = "center"
    public var tracking: Double = 0
    public var outline: Double = 0
    public var shadow: Double = 0
    public var blend = "normal"
}
public struct ImageStudioRecipe: Codable, Hashable, Sendable {
    public var version = 1
    public var crops: [ImageStudioCrop] = []
    public var rotation: Double = 0
    public var flipHorizontal = false
    public var subject = false
    public var subjectX: Double = 0.5
    public var subjectY: Double = 0.5
    public var exposure: Double = 0
    public var contrast: Double = 1
    public var saturation: Double = 1
    public var temperature: Double = 6500
    public var shadows: Double = 0
    public var filter = "original"
    public var intensity: Double = 1
    public var layers: [ImageStudioLayer] = []
    public var strokes: [ImageStudioStroke] = []
    public var outputWidth: Int? = nil
    public var outputHeight: Int? = nil
    public var quality: Double = 0.9
    public var removeLocation = true
}

struct ImageStudioSaveRequest: Encodable {
    let sourceArtifactId: String
    let resultArtifactId: String
    let sourceHash: String
    let filename: String
    let edit: ImageEditDTO
    enum CodingKeys: String, CodingKey {
        case sourceArtifactId = "source_artifact_id", resultArtifactId = "result_artifact_id"
        case sourceHash = "source_hash", filename, edit
    }
}
