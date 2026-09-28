import SwiftUI
import ImageIO
import Vision
import CoreImage
import Mantis

public struct ImageCard: View {
    public let block: ImageBlock
    @State private var image: UIImage?
    @State private var original: Data?
    @State private var downloadURL: URL?
    @State private var error: String?
    @State private var editing = false
    @State private var retry = 0

    public init(block: ImageBlock) { self.block = block }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let image {
                Image(uiImage: image).resizable().scaledToFit()
                    .frame(maxHeight: 360)
                    .frame(maxWidth: .infinity)
                    .background(AppTheme.Colors.secondaryBackground)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md))
                    .accessibilityLabel(block.caption.isEmpty ? "已上传的图片" : block.caption)
            } else if error == nil {
                ProgressView("正在读取图片…").frame(maxWidth: .infinity, minHeight: 120)
            }
            if let error {
                Label(error, systemImage: "exclamationmark.circle")
                Button("重新加载") { retry += 1 }
            }
            Text(block.caption).font(AppTheme.Typography.supporting)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            if (block.assetName.hasPrefix("ga_") || block.assetName.hasPrefix("doc_")) {
                HStack {
                    Button("编辑图片", systemImage: "slider.horizontal.3") { editing = true }
                        .disabled(original == nil)
                    Spacer()
                    if let downloadURL {
                        ShareLink(item: downloadURL) { Label("导出", systemImage: "square.and.arrow.up") }
                    }
                }.font(.system(size: 14, weight: .semibold)).frame(minHeight: 44)
            }
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg))
        .overlay(RoundedRectangle(cornerRadius: AppTheme.Radius.lg).stroke(AppTheme.Colors.border, lineWidth: 0.5))
        .task(id: "\(block.assetName)-\(retry)") { await load() }
        .sheet(isPresented: $editing) {
            if let original {
                ImageWorkbench(data: original) { data in
                    editing = false
                    TenantSessionCoordinator.shared.attachPhoto(data)
                }
            }
        }
    }

    nonisolated static func thumbnailData(from data: Data, maxPixelSize: Int = 1_600) -> Data? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceShouldCacheImmediately: false,
                kCGImageSourceThumbnailMaxPixelSize: maxPixelSize,
              ] as CFDictionary) else { return nil }
        return UIImage(cgImage: image).pngData()
    }

    @MainActor private func load() async {
        error = nil
        image = block.imageData.flatMap(UIImage.init(data:)) ?? UIImage(named: block.assetName)
        guard (block.assetName.hasPrefix("ga_") || block.assetName.hasPrefix("doc_")) else {
            if image == nil { error = "图片不可用" }
            return
        }
        let account = TenantSessionCoordinator.shared.sessionManager.activeAccountFingerprint
        do {
            let receipt = try await APIClient.shared.fetchImageReceipt(id: block.assetName)
            let bytes = try await APIClient.shared.downloadAuthenticated(path: receipt.downloadPath, expectedHash: receipt.contentHash)
            guard !Task.isCancelled, TenantSessionCoordinator.shared.sessionManager.activeAccountFingerprint == account else { return }
            original = bytes
            image = UIImage(data: bytes)
            downloadURL = try InboxFileManager.shared.storePrivateFile(bytes, sourceId: receipt.artifactId, revision: receipt.revision, filename: receipt.filename)
        } catch {
            guard !Task.isCancelled else { return }
            self.error = error.localizedDescription
        }
    }
}

/// Native codecs preserve PNG transparency; HEIC is converted losslessly to PNG for the server.
enum ImageEditSupport {
    static func uploadData(_ data: Data) -> Data? {
        guard data.count <= 12 * 1024 * 1024,
              let source = CGImageSourceCreateWithData(data as CFData, nil),
              CGImageSourceGetCount(source) == 1,
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = properties[kCGImagePropertyPixelWidth] as? Int,
              let height = properties[kCGImagePropertyPixelHeight] as? Int,
              width > 0, height > 0, Double(width) * Double(height) <= 24_000_000 else { return nil }
        let type = CGImageSourceGetType(source) as String? ?? ""
        if ["public.png", "public.jpeg", "org.webmproject.webp"].contains(type) { return data }
        guard let png = UIImage(data: data)?.pngData(), png.count <= 12 * 1024 * 1024 else { return nil }
        return png
    }

    static func encode(_ image: UIImage, format: String) -> Data? {
        if format == "PNG" { return image.pngData() }
        let settings = UIGraphicsImageRendererFormat()
        settings.scale = 1
        settings.opaque = true
        let size = CGSize(width: image.size.width * image.scale, height: image.size.height * image.scale)
        return UIGraphicsImageRenderer(size: size, format: settings).image { context in
            UIColor.white.setFill()
            context.fill(CGRect(origin: .zero, size: size))
            image.draw(in: CGRect(origin: .zero, size: size))
        }.jpegData(compressionQuality: 0.95)
    }


    static func process(_ data: Data, edit: ImageEditDTO) throws -> Data {
        if edit.studio != nil { return try renderStudio(data, edit: edit) }
        guard uploadData(data) != nil, let original = UIImage(data: data),
              ["png", "jpg"].contains(edit.format), edit.focusX.isFinite, edit.focusY.isFinite,
              (0...1).contains(edit.focusX), (0...1).contains(edit.focusY),
              !(edit.extractSubject && edit.format == "jpg") else {
            throw APIError.network("图片或处理参数无效")
        }
        // Normalize orientation before interpreting the same top-left point used by the UI.
        let size = CGSize(width: original.size.width * original.scale, height: original.size.height * original.scale)
        let settings = UIGraphicsImageRendererFormat(); settings.scale = 1
        var image = UIGraphicsImageRenderer(size: size, format: settings).image { _ in
            original.draw(in: CGRect(origin: .zero, size: size))
        }
        if edit.extractSubject {
            guard let png = image.pngData(), let extracted = UIImage(data: try extract(png, x: edit.focusX, y: edit.focusY)) else {
                throw APIError.network("无法提取主体")
            }
            image = extracted
        }
        if edit.aspectRatio != "original" {
            guard ["16:9", "9:16", "1:1", "4:3", "3:4"].contains(edit.aspectRatio), let cg = image.cgImage else {
                throw APIError.network("不支持的裁切比例")
            }
            let ratio = edit.aspectRatio.split(separator: ":").compactMap { Int($0) }
            let scale = min(cg.width / ratio[0], cg.height / ratio[1])
            guard scale > 0 else { throw APIError.network("图片太小，无法裁切") }
            let width = scale * ratio[0], height = scale * ratio[1]
            let left = max(0, min(cg.width - width, Int((edit.focusX * Double(cg.width) - Double(width) / 2).rounded())))
            let top = max(0, min(cg.height - height, Int((edit.focusY * Double(cg.height) - Double(height) / 2).rounded())))
            guard let cropped = cg.cropping(to: CGRect(x: left, y: top, width: width, height: height)) else {
                throw APIError.network("裁切失败")
            }
            image = UIImage(cgImage: cropped)
        }
        guard let result = encode(image, format: edit.format.uppercased()), result.count <= 12 * 1024 * 1024 else {
            throw APIError.network("处理结果超过 12 MB，请缩小裁切区域")
        }
        return result
    }

    static func extract(_ data: Data, x: Double, y: Double) throws -> Data {
        let handler = VNImageRequestHandler(data: data)
        let request = VNGenerateForegroundInstanceMaskRequest()
        try handler.perform([request])
        guard let result = request.results?.first else { throw APIError.network("未识别到主体，请换一张图片") }
        let mask = result.instanceMask
        CVPixelBufferLockBaseAddress(mask, .readOnly)
        let width = CVPixelBufferGetWidth(mask), height = CVPixelBufferGetHeight(mask)
        let column = min(width - 1, max(0, Int(x * Double(width))))
        let row = min(height - 1, max(0, Int(y * Double(height))))
        let label = CVPixelBufferGetBaseAddress(mask)!.assumingMemoryBound(to: UInt8.self)[row * CVPixelBufferGetBytesPerRow(mask) + column]
        CVPixelBufferUnlockBaseAddress(mask, .readOnly)
        guard label != 0 else { throw APIError.network("选中的是背景，请点一下要保留的人物或物品") }
        let output = try result.generateMaskedImage(ofInstances: IndexSet(integer: Int(label)), from: handler, croppedToInstancesExtent: false)
        let ciImage = CIImage(cvPixelBuffer: output)
        guard let cg = CIContext().createCGImage(ciImage, from: ciImage.extent),
              let png = UIImage(cgImage: cg).pngData() else { throw APIError.network("无法生成抠图结果") }
        return png
    }
}
