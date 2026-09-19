#!/usr/bin/env swift

import AppKit
import Foundation
import Vision

guard CommandLine.arguments.count == 3 else {
    FileHandle.standardError.write(Data("usage: extract_prototype_vision.swift <pages-dir> <output-json>\n".utf8))
    exit(2)
}

let root = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL
let output = URL(fileURLWithPath: CommandLine.arguments[2]).standardizedFileURL
let manager = FileManager.default
let keys: [URLResourceKey] = [.isRegularFileKey]
guard let enumerator = manager.enumerator(at: root, includingPropertiesForKeys: keys) else {
    FileHandle.standardError.write(Data("cannot enumerate \(root.path)\n".utf8))
    exit(1)
}
let files = enumerator.compactMap { $0 as? URL }
    .filter { $0.pathExtension.lowercased() == "png" }
    .sorted { $0.path < $1.path }

func pixelBox(_ box: CGRect, width: Int, height: Int) -> [String: Int] {
    [
        "x": Int((box.minX * CGFloat(width)).rounded()),
        "y": Int(((1 - box.maxY) * CGFloat(height)).rounded()),
        "width": Int((box.width * CGFloat(width)).rounded()),
        "height": Int((box.height * CGFloat(height)).rounded())
    ]
}

var pages: [[String: Any]] = []

for file in files {
    autoreleasepool {
        guard
            let image = NSImage(contentsOf: file),
            let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil)
        else { return }

        let textRequest = VNRecognizeTextRequest()
        textRequest.recognitionLevel = .accurate
        textRequest.recognitionLanguages = ["zh-Hans", "en-US"]
        textRequest.usesLanguageCorrection = true
        textRequest.minimumTextHeight = 0.008

        let rectangleRequest = VNDetectRectanglesRequest()
        rectangleRequest.maximumObservations = 80
        rectangleRequest.minimumSize = 0.018
        rectangleRequest.minimumAspectRatio = 0.08
        rectangleRequest.maximumAspectRatio = 1
        rectangleRequest.quadratureTolerance = 22

        do {
            try VNImageRequestHandler(cgImage: cgImage).perform([textRequest, rectangleRequest])
        } catch {
            FileHandle.standardError.write(Data("vision failed: \(file.path): \(error)\n".utf8))
            return
        }

        let text = (textRequest.results ?? []).compactMap { observation -> [String: Any]? in
            guard let candidate = observation.topCandidates(1).first else { return nil }
            return [
                "value": candidate.string,
                "confidence": candidate.confidence,
                "box": pixelBox(observation.boundingBox, width: cgImage.width, height: cgImage.height)
            ]
        }

        let rectangles = (rectangleRequest.results ?? []).map { observation -> [String: Any] in
            [
                "confidence": observation.confidence,
                "box": pixelBox(observation.boundingBox, width: cgImage.width, height: cgImage.height)
            ]
        }

        let relative = file.path.replacingOccurrences(of: root.path + "/", with: "")
        pages.append([
            "page": relative,
            "width": cgImage.width,
            "height": cgImage.height,
            "text": text,
            "rectangles": rectangles
        ])
        print("vision \(pages.count)/\(files.count): \(relative)")
    }
}

let payload: [String: Any] = [
    "source": root.path,
    "pageCount": pages.count,
    "pages": pages
]
let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
try manager.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true)
try data.write(to: output, options: .atomic)
