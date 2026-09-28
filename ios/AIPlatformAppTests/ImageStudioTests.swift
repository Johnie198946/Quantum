import XCTest
import UIKit
import ImageIO
import Photos
@testable import AIPlatformApp

final class ImageStudioTests: XCTestCase {
    func image(_ size:CGSize = CGSize(width:160,height:120), transparent:Bool = false) throws -> Data {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.preferredRange = .standard
        return try XCTUnwrap(UIGraphicsImageRenderer(size:size,format:format).image { c in
            if !transparent { UIColor(red:0.25,green:0.55,blue:0.8,alpha:1).setFill(); c.fill(CGRect(origin:.zero,size:size)) }
            UIColor.red.setFill(); c.fill(CGRect(x:20,y:20,width:24,height:24))
        }.pngData())
    }
    func edit(_ recipe:ImageStudioRecipe, format:String = "png") -> ImageEditDTO {
        var value = ImageEditDTO(format:format,aspectRatio:"original",extractSubject:false,focusX:0.5,focusY:0.5); value.studio = recipe; return value
    }
    func pixel(_ data:Data,x:Int,y:Int) throws -> [UInt8] {
        let image = try XCTUnwrap(UIImage(data:data)?.cgImage)
        let width = image.width, height = image.height
        var pixels = [UInt8](repeating:0,count:width*height*4)
        try pixels.withUnsafeMutableBytes { buffer in
            let context = try XCTUnwrap(CGContext(data:buffer.baseAddress,width:width,height:height,bitsPerComponent:8,bytesPerRow:width*4,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue))
            context.draw(image,in:CGRect(x:0,y:0,width:width,height:height))
        }
        return Array(pixels[((y*width+x)*4)..<((y*width+x)*4+4)])
    }
    func testPixelsTextLayersFiltersDimensionsAndEncoding() throws {
        let input = try image()
        var r = ImageStudioRecipe()
        let original = try ImageEditSupport.renderStudio(input,edit:edit(r))
        r.filter = "sunny"; r.exposure = 0.3
        let filtered = try ImageEditSupport.renderStudio(input,edit:edit(r))
        XCTAssertNotEqual(filtered,original)
        var text = ImageStudioLayer(); text.text = "CAMPUS"; text.fontSize = 0.12; text.y = 0.6
        r.layers = [text]
        XCTAssertNotEqual(try ImageEditSupport.renderStudio(input,edit:edit(r)),filtered)
        r.layers[0].visible = false
        XCTAssertEqual(try ImageEditSupport.renderStudio(input,edit:edit(r)),filtered)
        r.outputWidth = 80; r.outputHeight = 60
        let small = try ImageEditSupport.renderStudio(input,edit:edit(r,format:"jpg"))
        XCTAssertEqual(UIImage(data:small)?.size,CGSize(width:80,height:60))
        XCTAssertEqual(CGImageSourceGetType(try XCTUnwrap(CGImageSourceCreateWithData(small as CFData,nil))) as String?,"public.jpeg")
        r.outputWidth = 200
        XCTAssertThrowsError(try ImageEditSupport.renderStudio(input,edit:edit(r)))
    }
    func testCropRotationAndBounds() throws {
        let input = try image()
        var r = ImageStudioRecipe()
        r.crops = [.init(corners:[.init(x:0,y:0),.init(x:0.5,y:0),.init(x:0.5,y:1),.init(x:0,y:1)],width:80,height:120)]
        let mapped = ImageEditSupport.sourcePoint(.init(x:0.5,y:0.5),recipe:r)
        XCTAssertEqual(mapped.x,0.25,accuracy:0.001); XCTAssertEqual(mapped.y,0.5,accuracy:0.001)
        r.rotation = 90
        XCTAssertEqual(UIImage(data:try ImageEditSupport.renderStudio(input,edit:edit(r)))?.size,CGSize(width:120,height:80))
        r.crops[0].corners[1] = r.crops[0].corners[0]
        XCTAssertThrowsError(try ImageEditSupport.renderStudio(input,edit:edit(r)))
    }
    func testSpotRepairChangesMaskAndPreservesAlpha() throws {
        let input = try image()
        var r = ImageStudioRecipe()
        r.strokes = [.init(id:"spot",points:[.init(x:0.19,y:0.25),.init(x:0.24,y:0.25)],radius:0.08)]
        let repaired = try ImageEditSupport.renderStudio(input,edit:edit(r))
        XCTAssertNotEqual(repaired,try ImageEditSupport.renderStudio(input,edit:edit(ImageStudioRecipe())))
        XCTAssertEqual(UIImage(data:repaired)?.size,CGSize(width:160,height:120))
        let transparent = try image(transparent:true)
        r.strokes = []
        let png = try ImageEditSupport.renderStudio(transparent,edit:edit(r))
        let source = try XCTUnwrap(CGImageSourceCreateWithData(png as CFData,nil))
        let properties = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(source,0,nil) as? [CFString:Any])
        XCTAssertEqual(properties[kCGImagePropertyHasAlpha] as? Bool,true)
        XCTAssertEqual(try pixel(png,x:0,y:0)[3],0)
        let jpeg = try ImageEditSupport.renderStudio(transparent,edit:edit(r,format:"jpg"))
        let white = try pixel(jpeg,x:0,y:0)
        XCTAssertTrue(white[0] > 240 && white[1] > 240 && white[2] > 240)
        XCTAssertEqual(ImageEditSupport.studioFont("serif",size:20).fontName,"ZCOOLXiaoWei-Regular")
        XCTAssertEqual(ImageEditSupport.studioFont("hand",size:20).fontName,"MaShanZheng-Regular")
        r.strokes = [.init(id:"bad",points:[.init(x:1.1,y:0)],radius:0.02)]
        XCTAssertThrowsError(try ImageEditSupport.renderStudio(input,edit:edit(r)))
    }
    func testPrivateLayerResourcesRequiredAndPCMEncodingRoundTrip() throws {
        var r = ImageStudioRecipe()
        var layer = ImageStudioLayer(); layer.kind = "image"; layer.assetId = "ga_"+String(repeating:"a",count:32)
        r.layers = [layer]
        let input = try image()
        XCTAssertThrowsError(try ImageEditSupport.renderStudio(input,edit:edit(r)))
        let out = try ImageEditSupport.renderStudio(input,edit:edit(r),assets:[layer.assetId!:try image(CGSize(width:30,height:30))])
        XCTAssertNotEqual(out,input)
        let request = ImageStudioSaveRequest(sourceArtifactId:"source",resultArtifactId:"result",sourceHash:"hash",filename:"edited.png",edit:edit(r))
        let wire = try XCTUnwrap(JSONSerialization.jsonObject(with:JSONEncoder().encode(request)) as? [String:Any])
        let editWire = try XCTUnwrap(wire["edit"] as? [String:Any])
        XCTAssertEqual(editWire["extract_subject"] as? Bool,false)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        XCTAssertEqual(try decoder.decode(ImageEditDTO.self,from:JSONSerialization.data(withJSONObject:editWire)),edit(r))
    }
    @MainActor func testUndoRedoAndDraftRestore() throws {
        let session = ImageStudioSession([try image()])
        let initial = session.recipe
        session.recipe.exposure = 0.5; session.remember(initial)
        session.undo(); XCTAssertEqual(session.recipe.exposure,0)
        session.redo(); XCTAssertEqual(session.recipe.exposure,0.5)
        // Encoding the same draft shape avoids writing a user's persisted draft during unit tests.
        let draft = ImageStudioSession.Draft(source:session.source,recipe:session.recipe,assets:[:],format:"png",filename:"test")
        let decoded = try JSONDecoder().decode(ImageStudioSession.Draft.self,from:JSONEncoder().encode(draft))
        XCTAssertEqual(decoded.recipe,session.recipe)
        XCTAssertEqual(decoded.source,session.source)
    }
}

extension ImageStudioTests {
    @MainActor func testLiveManualSaveAndBatchThroughPCM() async throws {
        guard ProcessInfo.processInfo.environment["IMAGE_STUDIO_LIVE"] == "1" else { throw XCTSkip("Requires isolated local PCM backend") }
        InboxFileManager.shared.activatePrivateCache(tenantKey:"image-studio-test",userId:"alice")
        defer { InboxFileManager.shared.clearPrivateCache() }
        let session = ImageStudioSession([try image(),try image(CGSize(width:240,height:180))])
        session.keepDraft = false
        session.recipe.layers = [ImageStudioLayer()]
        session.recipe.filter = "sunny"
        session.recipe.outputWidth = 80; session.recipe.outputHeight = 60
        await session.save(batch:true)
        XCTAssertNil(session.error)
        XCTAssertEqual(session.completed.count,2)
        XCTAssertTrue(session.failures.isEmpty)
        for (_,url) in session.completed {
            XCTAssertEqual(UIImage(data:try Data(contentsOf:url))?.size,CGSize(width:80,height:60))
        }
        XCTAssertEqual(PHPhotoLibrary.authorizationStatus(for:.addOnly),.authorized)
        let urls = Array(session.completed.values)
        try await PHPhotoLibrary.shared().performChanges {
            for url in urls { PHAssetChangeRequest.creationRequestForAssetFromImage(atFileURL:url) }
        }
        let first = session.completed
        await session.save(batch:true)
        XCTAssertEqual(session.completed,first)
    }
}
