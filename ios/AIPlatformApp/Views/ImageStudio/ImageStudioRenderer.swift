import UIKit
import CoreImage
import ImageIO
import opencv2

extension ImageEditSupport {
    // ponytail: serialize image buffers to bound memory; tiled rendering if 24MP becomes insufficient.
    private static let studioLock = NSLock()
    private static let studioContext = CIContext(options: [.cacheIntermediates: false])

    static func studioFont(_ name: String, size: CGFloat) -> UIFont {
        switch name {
        case "serif": return UIFont(name: "ZCOOLXiaoWei-Regular", size: size) ?? .systemFont(ofSize: size, weight: .medium)
        case "hand": return UIFont(name: "MaShanZheng-Regular", size: size) ?? .systemFont(ofSize: size, weight: .regular, width: .condensed)
        default: return .systemFont(ofSize: size, weight: .semibold)
        }
    }
    static func studioColor(_ hex: String) -> UIColor {
        let n = UInt32(hex, radix: 16) ?? 0x1F2D2E
        return UIColor(red: CGFloat(n >> 16) / 255, green: CGFloat((n >> 8) & 255) / 255,
                       blue: CGFloat(n & 255) / 255, alpha: 1)
    }
    static func raster(_ ci: CIImage) throws -> UIImage {
        guard !ci.extent.isInfinite, !ci.extent.isEmpty,
              let cg = studioContext.createCGImage(ci, from: ci.extent) else { throw APIError.network("图片渲染失败") }
        return UIImage(cgImage: cg)
    }
    static func renderStudio(_ data: Data, edit: ImageEditDTO, assets: [String: Data] = [:], preview: Bool = false) throws -> Data {
        let image = try studioImage(data, edit: edit, assets: assets, preview: preview)
        let quality = edit.studio?.quality ?? 0.9
        let format = edit.format.lowercased()
        guard ["png", "jpg"].contains(format), quality.isFinite, (0.1...1).contains(quality) else { throw APIError.network("输出参数无效") }
        var final = image
        if format == "jpg" {
            let f = UIGraphicsImageRendererFormat(); f.scale = 1; f.preferredRange = .standard; f.opaque = true
            final = UIGraphicsImageRenderer(size: image.size, format: f).image { c in
                UIColor.white.setFill(); c.fill(CGRect(origin: .zero, size: image.size)); image.draw(at: .zero)
            }
        }
        let destination = NSMutableData()
        guard let cg = final.cgImage,
              let writer = CGImageDestinationCreateWithData(destination, (format == "png" ? "public.png" : "public.jpeg") as CFString, 1, nil) else { throw APIError.network("无法编码图片") }
        var metadata: [CFString: Any] = [kCGImageDestinationLossyCompressionQuality: quality]
        if edit.studio?.removeLocation == false,
           let input = CGImageSourceCreateWithData(data as CFData, nil),
           let properties = CGImageSourceCopyPropertiesAtIndex(input, 0, nil) as? [CFString: Any],
           let gps = properties[kCGImagePropertyGPSDictionary] { metadata[kCGImagePropertyGPSDictionary] = gps }
        CGImageDestinationAddImage(writer, cg, metadata as CFDictionary)
        guard CGImageDestinationFinalize(writer) else { throw APIError.network("无法编码图片") }
        let output = destination as Data
        guard preview || output.count <= 12 * 1024 * 1024 else { throw APIError.network("结果超过12 MB，请降低尺寸或选择JPG") }
        return output
    }
    static func studioImage(_ data: Data, edit: ImageEditDTO, assets: [String: Data] = [:], preview: Bool = false) throws -> UIImage {
        studioLock.lock(); defer { studioLock.unlock() }
        guard uploadData(data) != nil, let recipe = edit.studio,
              recipe.version == 1, recipe.crops.count <= 12, recipe.layers.count <= 20, recipe.strokes.count <= 40,
              Set(recipe.layers.map(\.id)).count == recipe.layers.count,
              (0...1).contains(recipe.subjectX), (0...1).contains(recipe.subjectY),
              (recipe.outputWidth == nil) == (recipe.outputHeight == nil),
              let input = UIImage(data: data) else { throw APIError.network("图片或版本无效") }
        let numeric = [recipe.rotation, recipe.exposure, recipe.contrast, recipe.saturation, recipe.temperature,
                       recipe.shadows, recipe.intensity, recipe.quality]
        guard numeric.allSatisfy({ $0.isFinite }), [0,90,180,270].contains(recipe.rotation),
              (-2...2).contains(recipe.exposure), (0.5...2).contains(recipe.contrast), (0...2).contains(recipe.saturation),
              (2500...10000).contains(recipe.temperature), (0...1).contains(recipe.shadows),
              (0...1).contains(recipe.intensity) else { throw APIError.network("调色参数超出范围") }
        var baseEdit = edit; baseEdit.studio = nil; baseEdit = ImageEditDTO(format: "png", aspectRatio: edit.aspectRatio,
            extractSubject: edit.extractSubject, focusX: edit.focusX, focusY: edit.focusY)
        // Normalize and preserve the existing v1 subject/crop semantics.
        var fullSize = CGSize(width: input.size.width * input.scale, height: input.size.height * input.scale)
        var image: UIImage
        if edit.extractSubject || edit.aspectRatio != "original" {
            guard let decoded = UIImage(data: try process(data, edit: baseEdit)) else { throw APIError.network("图片处理失败") }
            image = decoded; fullSize = image.size
        } else {
            let f = UIGraphicsImageRendererFormat(); f.scale = 1; f.preferredRange = .standard
            let factor = preview ? min(1, 1200 / max(fullSize.width,fullSize.height)) : 1
            let size = CGSize(width: fullSize.width * factor, height: fullSize.height * factor)
            image = UIGraphicsImageRenderer(size: size, format: f).image { _ in input.draw(in: CGRect(origin: .zero, size: size)) }
        }
        if !recipe.strokes.isEmpty { image = try repair(image, strokes: recipe.strokes) }
        if recipe.subject {
            guard let bytes = image.pngData(), let extracted = UIImage(data: try extract(bytes, x: recipe.subjectX, y: recipe.subjectY)) else { throw APIError.network("无法提取主体") }; image = extracted
        }
        for crop in recipe.crops {
            guard crop.corners.count == 4, crop.width > 0, crop.height > 0,
                  Double(crop.width) * Double(crop.height) <= 24_000_000,
                  crop.corners.allSatisfy({ $0.x.isFinite && $0.y.isFinite && (0...1).contains($0.x) && (0...1).contains($0.y) }),
                  let ci = CIImage(image: image) else { throw APIError.network("裁剪参数无效") }
            let cross = (0..<4).map { i -> Double in
                let a = crop.corners[i], b = crop.corners[(i+1)%4], c = crop.corners[(i+2)%4]
                return (b.x-a.x)*(c.y-b.y)-(b.y-a.y)*(c.x-b.x)
            }
            guard cross.allSatisfy({$0 > 1e-10}) || cross.allSatisfy({$0 < -1e-10}),
                  Double(crop.width)*Double(crop.height) <= fullSize.width*fullSize.height else { throw APIError.network("裁剪区域无效") }
            let points = crop.corners.map { CIVector(x: $0.x * ci.extent.width, y: (1 - $0.y) * ci.extent.height) }
            let result = ci.applyingFilter("CIPerspectiveCorrection", parameters: ["inputTopLeft": points[0], "inputTopRight": points[1],
                "inputBottomRight": points[2], "inputBottomLeft": points[3]])
            image = try raster(result)
            fullSize = CGSize(width: crop.width, height: crop.height)
            let factor = preview ? min(1, 1200 / max(fullSize.width,fullSize.height)) : 1
            image = resized(image, width: max(1,Int(fullSize.width*factor)), height: max(1,Int(fullSize.height*factor)))
        }
        if recipe.rotation != 0 || recipe.flipHorizontal {
            let swap = recipe.rotation == 90 || recipe.rotation == 270
            if swap { fullSize = CGSize(width:fullSize.height,height:fullSize.width) }
            let size = swap ? CGSize(width: image.size.height, height: image.size.width) : image.size
            let f = UIGraphicsImageRendererFormat(); f.scale = 1; f.preferredRange = .standard
            let old = image
            image = UIGraphicsImageRenderer(size: size, format: f).image { c in
                c.cgContext.translateBy(x: size.width / 2, y: size.height / 2)
                c.cgContext.scaleBy(x: recipe.flipHorizontal ? -1 : 1, y: 1)
                c.cgContext.rotate(by: recipe.rotation * .pi / 180)
                old.draw(in: CGRect(x: -old.size.width/2, y: -old.size.height/2, width: old.size.width, height: old.size.height))
            }
        }
        if preview && max(image.size.width, image.size.height) > 1200 {
            let factor = 1200 / max(image.size.width, image.size.height)
            image = resized(image, width: Int(image.size.width * factor), height: Int(image.size.height * factor))
        }
        guard var ci = CIImage(image: image) else { throw APIError.network("图片无法读取") }
        ci = ci.applyingFilter("CIExposureAdjust", parameters: ["inputEV": recipe.exposure])
            .applyingFilter("CIColorControls", parameters: ["inputContrast": recipe.contrast,"inputSaturation": recipe.saturation])
            .applyingFilter("CITemperatureAndTint", parameters: ["inputNeutral": CIVector(x: recipe.temperature, y: 0), "inputTargetNeutral": CIVector(x: 6500, y: 0)])
            .applyingFilter("CIHighlightShadowAdjust", parameters: ["inputShadowAmount": recipe.shadows])
        let original = ci
        switch recipe.filter {
        case "sunny": ci = ci.applyingFilter("CIPhotoEffectProcess")
        case "mint": ci = ci.applyingFilter("CIPhotoEffectTransfer")
        case "film": ci = ci.applyingFilter("CIPhotoEffectFade")
        case "original": break
        default: throw APIError.network("滤镜不可用")
        }
        if recipe.filter != "original" {
            ci = ci.applyingFilter("CIDissolveTransition", parameters: ["inputTargetImage": original, "inputTime": 1-recipe.intensity])
        }
        image = try raster(ci)
        image = try compose(image, layers: recipe.layers, assets: assets)
        if let w = recipe.outputWidth, let h = recipe.outputHeight {
            guard w > 0, h > 0, Double(w) <= fullSize.width, Double(h) <= fullSize.height,
                  Double(w) * Double(h) <= 24_000_000 else { throw APIError.network("输出尺寸超出范围") }
            if !preview { image = resized(image, width: w, height: h) }
        }
        return image
    }
    /// Manual Mantis transforms are affine. Store local selections in source coordinates
    /// so later crops never move an existing repair to a different object.
    static func sourcePoint(_ point: ImageStudioPoint, recipe: ImageStudioRecipe) -> ImageStudioPoint {
        var p = point
        if recipe.flipHorizontal { p.x = 1-p.x }
        switch recipe.rotation {
        case 90: p = .init(x:p.y,y:1-p.x)
        case 180: p = .init(x:1-p.x,y:1-p.y)
        case 270: p = .init(x:1-p.y,y:p.x)
        default: break
        }
        for crop in recipe.crops.reversed() where crop.corners.count == 4 {
            let c = crop.corners, x = p.x, y = p.y
            p = .init(x:(1-x)*(1-y)*c[0].x+x*(1-y)*c[1].x+x*y*c[2].x+(1-x)*y*c[3].x,
                      y:(1-x)*(1-y)*c[0].y+x*(1-y)*c[1].y+x*y*c[2].y+(1-x)*y*c[3].y)
        }
        return .init(x:min(1,max(0,p.x)),y:min(1,max(0,p.y)))
    }
    static func resized(_ image: UIImage, width: Int, height: Int) -> UIImage {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.preferredRange = .standard
        return UIGraphicsImageRenderer(size: CGSize(width: width, height: height), format: format).image { c in
            c.cgContext.interpolationQuality = .high
            image.draw(in: CGRect(x: 0, y: 0, width: width, height: height))
        }
    }
    static func compose(_ image: UIImage, layers: [ImageStudioLayer], assets: [String: Data]) throws -> UIImage {
        for layer in layers where layer.visible {
            guard [layer.x,layer.y,layer.width,layer.fontSize,layer.opacity,layer.rotation,layer.tracking,layer.outline,layer.shadow].allSatisfy({$0.isFinite}),
                  (0...1).contains(layer.x), (0...1).contains(layer.y), (0.02...2).contains(layer.width),
                  (0.01...0.5).contains(layer.fontSize), (0...1).contains(layer.opacity), layer.text.count <= 2000,
                  (-360...360).contains(layer.rotation), (-0.05...0.1).contains(layer.tracking),
                  (0...0.1).contains(layer.outline), (0...0.1).contains(layer.shadow),
                  ["text","image"].contains(layer.kind), ["sans","serif","hand"].contains(layer.font),
                  ["normal","multiply","screen","overlay"].contains(layer.blend) else { throw APIError.network("图层参数无效") }
            if layer.kind == "image", layer.assetId.flatMap({assets[$0]}).flatMap(UIImage.init(data:)) == nil { throw APIError.network("贴图素材未就绪") }
        }
        let f = UIGraphicsImageRendererFormat(); f.scale = 1; f.preferredRange = .standard
        return UIGraphicsImageRenderer(size: image.size, format: f).image { c in
            image.draw(at: .zero)
            for layer in layers where layer.visible {
                c.cgContext.saveGState(); defer { c.cgContext.restoreGState() }
                c.cgContext.setAlpha(layer.opacity)
                c.cgContext.setBlendMode(["multiply": .multiply, "screen": .screen, "overlay": .overlay][layer.blend] ?? .normal)
                c.cgContext.translateBy(x: layer.x * image.size.width, y: layer.y * image.size.height)
                c.cgContext.rotate(by: layer.rotation * .pi / 180)
                let w = image.size.width * layer.width
                if layer.kind == "image", let key = layer.assetId, let data = assets[key], let overlay = UIImage(data: data) {
                    let h = w * overlay.size.height / overlay.size.width
                    c.cgContext.setAlpha(1)
                    overlay.draw(in: CGRect(x: -w/2, y: -h/2, width: w, height: h), blendMode: ["multiply": .multiply, "screen": .screen, "overlay": .overlay][layer.blend] ?? .normal, alpha: layer.opacity)
                } else {
                    let p = NSMutableParagraphStyle(); p.alignment = ["left": .left, "right": .right][layer.alignment] ?? .center
                    let shadow = NSShadow(); shadow.shadowColor = UIColor.black.withAlphaComponent(0.4)
                    shadow.shadowBlurRadius = layer.shadow * image.size.width
                    shadow.shadowOffset = CGSize(width: 0, height: layer.shadow * image.size.width / 2)
                    let attributes: [NSAttributedString.Key: Any] = [.font: studioFont(layer.font,size: layer.fontSize * image.size.width),
                        .foregroundColor: studioColor(layer.color), .paragraphStyle: p, .kern: layer.tracking * image.size.width,
                        .strokeWidth: -layer.outline * 100, .strokeColor: UIColor.black, .shadow: shadow]
                    let text = NSAttributedString(string: layer.text, attributes: attributes)
                    let h = text.boundingRect(with: CGSize(width: w, height: image.size.height * 2), options: [.usesLineFragmentOrigin,.usesFontLeading], context: nil).height
                    text.draw(in: CGRect(x: -w/2, y: -h/2, width: w, height: h))
                }
            }
        }
    }
    static func repair(_ image: UIImage, strokes: [ImageStudioStroke]) throws -> UIImage {
        guard strokes.allSatisfy({ (0.001...0.08).contains($0.radius) && !$0.points.isEmpty && $0.points.count <= 256 && $0.points.allSatisfy({(0...1).contains($0.x) && (0...1).contains($0.y)}) }) else { throw APIError.network("修复选区无效") }
        let f = UIGraphicsImageRendererFormat(); f.scale = 1; f.preferredRange = .standard; f.opaque = true
        let maskImage = UIGraphicsImageRenderer(size: image.size, format: f).image { c in
            UIColor.black.setFill(); c.fill(CGRect(origin: .zero, size: image.size)); UIColor.white.setStroke(); UIColor.white.setFill()
            for stroke in strokes {
                let radius = stroke.radius * min(image.size.width, image.size.height)
                let path = UIBezierPath(); path.lineWidth = radius * 2; path.lineCapStyle = .round; path.lineJoinStyle = .round
                for (index, point) in stroke.points.enumerated() {
                    let p = CGPoint(x: point.x * image.size.width, y: point.y * image.size.height)
                    if index == 0 { path.move(to: p); UIBezierPath(ovalIn: CGRect(x: p.x-radius,y:p.y-radius,width:radius*2,height:radius*2)).fill() }
                    else { path.addLine(to: p) }
                }
                path.stroke()
            }
        }
        let rgba = Mat(uiImage: image, alphaExist: true), rgb = Mat(), maskRGBA = Mat(uiImage: maskImage, alphaExist: true), mask = Mat(), result = Mat()
        Imgproc.cvtColor(src: rgba, dst: rgb, code: .COLOR_RGBA2RGB)
        Imgproc.cvtColor(src: maskRGBA, dst: mask, code: .COLOR_RGBA2GRAY)
        Photo.inpaint(src: rgb, inpaintMask: mask, dst: result, inpaintRadius: 3, flags: Photo.INPAINT_TELEA)
        // Preserve the source alpha after RGB-only OpenCV inpainting.
        let repaired = result.toUIImage()
        guard let cg = image.cgImage else { return repaired }
        let rf = UIGraphicsImageRendererFormat(); rf.scale = 1; rf.preferredRange = .standard
        return UIGraphicsImageRenderer(size: image.size, format: rf).image { c in
            repaired.draw(at: .zero)
            UIImage(cgImage: cg).draw(at: .zero, blendMode: .destinationIn, alpha: 1)
        }
    }
}
