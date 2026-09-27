import SwiftUI
import PhotosUI
import CryptoKit

@MainActor final class ImageStudioSession: ObservableObject {
    @Published var recipe = ImageStudioRecipe()
    @Published var format = "jpg"
    @Published var filename = "照片-编辑"
    @Published var preview: UIImage?
    @Published var error: String?
    @Published var busy = false
    @Published var progress = ""
    @Published var source: Data
    @Published var photos: [Data]
    @Published var selected: Set<Int>
    @Published var completed: [Int: URL] = [:]
    @Published var failures: [Int: String] = [:]
    @Published var lastResult: Data?
    @Published var undoStack: [ImageStudioRecipe] = []
    @Published var redoStack: [ImageStudioRecipe] = []
    @Published var keepDraft = true
    var assets: [String: Data] = [:]
    var receipts: [String: ImageReceiptDTO] = [:]
    var pendingResults: [String: ImageReceiptDTO] = [:]
    var saveKeys: [String: String] = [:]
    var cancelBatch = false
    var renderVersion = 0
    let account: String
    private var previewTask: Task<Void, Never>?
    private var renderRunning = false
    init(_ photos: [Data]) {
        self.photos = photos; source = photos.first ?? Data(); selected = Set(photos.indices)
        account = TenantSessionCoordinator.shared.sessionManager.activeAccountFingerprint
        preview = UIImage(data: source)
    }
    var currentAccount: Bool { account == TenantSessionCoordinator.shared.sessionManager.activeAccountFingerprint }
    var edit: ImageEditDTO {
        var dto = ImageEditDTO(format: format, aspectRatio: "original", extractSubject: false, focusX: 0.5, focusY: 0.5)
        dto.studio = recipe; return dto
    }
    func remember(_ before: ImageStudioRecipe) {
        guard before != recipe else { return }
        undoStack.append(before); if undoStack.count > 20 { undoStack.removeFirst() }; redoStack = []
    }
    func undo() { if let previous = undoStack.popLast() { redoStack.append(recipe); recipe = previous; refresh() } }
    func redo() { if let next = redoStack.popLast() { undoStack.append(recipe); recipe = next; refresh() } }
    func refresh() {
        renderVersion += 1
        guard !renderRunning else { return }
        renderRunning = true
        previewTask = Task {
            defer { renderRunning = false }
            while currentAccount {
                let version = renderVersion
                try? await Task.sleep(for: .milliseconds(100))
                if version != renderVersion { continue }
                let bytes = source, config = edit, resources = assets
                do {
                    let image = try await Task.detached(priority: .userInitiated) {
                        try ImageEditSupport.studioImage(bytes, edit: config, assets: resources, preview: true)
                    }.value
                    guard currentAccount else { return }
                    if version == renderVersion { preview = image; error = nil; return }
                } catch {
                    if version == renderVersion { self.error = error.localizedDescription; return }
                }
            }
        }
    }
    func addPhotos(_ items: [PhotosPickerItem]) async {
        busy = true; defer { busy = false }
        do {
            for item in items {
                guard photos.count < 20, currentAccount else { throw APIError.network("一次最多20张图片") }
                guard let raw = try await item.loadTransferable(type: Data.self), let data = ImageEditSupport.uploadData(raw) else { throw APIError.network("请选择12 MB、2400万像素以内的静态图片") }
                // ponytail: 60MB input budget; disk-backed batch inputs if larger batches are required.
                guard photos.reduce(0,{$0+$1.count}) + data.count <= 60 * 1024 * 1024 else { throw APIError.network("本批图片总大小超过60 MB，请分批处理") }
                selected.insert(photos.count); photos.append(data)
            }
        } catch { self.error = error.localizedDescription }
    }
    func addSticker(_ item: PhotosPickerItem) async {
        busy = true; defer { busy = false }
        do {
            guard let raw = try await item.loadTransferable(type: Data.self), let bytes = ImageEditSupport.uploadData(raw),
                  assets.values.reduce(0,{$0+$1.count}) + bytes.count <= 24 * 1024 * 1024,
                  recipe.layers.count < 20 else { throw APIError.network("贴图过大或已达到20层上限") }
            let receipt = try await APIClient.shared.uploadImage(data: bytes)
            guard currentAccount else { return }
            assets[receipt.artifactId] = bytes
            let before = recipe
            var layer = ImageStudioLayer(); layer.kind = "image"; layer.text = "图片贴图"; layer.assetId = receipt.artifactId; layer.y = 0.5; layer.width = 0.4
            recipe.layers.append(layer); remember(before); refresh()
        } catch { self.error = error.localizedDescription }
    }
    func lift(x: Double, y: Double) async {
        guard !busy, currentAccount else { return }
        busy = true; defer { busy = false }
        let before = recipe, bytes = source, resources = assets
        var candidate = recipe
        let point = ImageEditSupport.sourcePoint(.init(x:x,y:y),recipe:recipe)
        candidate.subject = true; candidate.subjectX = point.x; candidate.subjectY = point.y
        var config = ImageEditDTO(format:"png",aspectRatio:"original",extractSubject:false,focusX:0.5,focusY:0.5)
        config.studio = candidate
        let request = config
        do {
            let image = try await Task.detached(priority:.userInitiated) { try ImageEditSupport.studioImage(bytes,edit:request,assets:resources,preview:true) }.value
            guard currentAccount else { return }
            recipe = candidate; format = "png"; preview = image; remember(before); error = nil
        } catch { if currentAccount { self.error = error.localizedDescription } }
    }
    func save(batch: Bool, syncColor: Bool = true, syncSize: Bool = true, syncText: Bool = true, syncCrop: Bool = false) async {
        guard !busy, currentAccount else { return }
        busy = true; cancelBatch = false; error = nil; defer { busy = false; progress = "" }
        let indices = batch ? selected.sorted() : [0]
        let originalRecipe = recipe, originalEdit = edit, resources = assets
        for (position, index) in indices.enumerated() {
            guard !cancelBatch, currentAccount else { break }
            if batch && completed[index] != nil { continue }
            progress = "正在保存 \(position + 1)/\(indices.count)"
            do {
                let input = batch ? photos[index] : source
                var configuration = originalEdit
                if batch && index != 0 {
                    var r = originalRecipe
                    r.strokes = []; r.subject = false
                    if !syncCrop { r.crops = []; r.rotation = 0; r.flipHorizontal = false }
                    else if let original = UIImage(data: source), let target = UIImage(data: input) {
                        var oldSize = original.size, newSize = target.size
                        r.crops = originalRecipe.crops.map { crop in
                            let a = crop.corners[0], b = crop.corners[1], d = crop.corners[3]
                            let oldW = hypot((b.x-a.x)*oldSize.width,(b.y-a.y)*oldSize.height)
                            let oldH = hypot((d.x-a.x)*oldSize.width,(d.y-a.y)*oldSize.height)
                            let newW = hypot((b.x-a.x)*newSize.width,(b.y-a.y)*newSize.height)
                            let newH = hypot((d.x-a.x)*newSize.width,(d.y-a.y)*newSize.height)
                            let w = max(1,Int(Double(crop.width)*newW/max(1,oldW)))
                            let h = max(1,Int(Double(crop.height)*newH/max(1,oldH)))
                            oldSize = CGSize(width:crop.width,height:crop.height); newSize = CGSize(width:w,height:h)
                            return ImageStudioCrop(corners:crop.corners,width:w,height:h)
                        }
                    }
                    r.layers = syncText ? r.layers.filter {$0.kind == "text"} : []
                    if !syncColor { r.exposure = 0; r.contrast = 1; r.saturation = 1; r.temperature = 6500; r.shadows = 0; r.filter = "original" }
                    if !syncSize { r.outputWidth = nil; r.outputHeight = nil; r.quality = 0.9 }
                    else if let w = r.outputWidth, let h = r.outputHeight, let image = UIImage(data: input) {
                        var target = r.crops.last.map { CGSize(width:$0.width,height:$0.height) } ?? image.size
                        if r.rotation == 90 || r.rotation == 270 { target = CGSize(width:target.height,height:target.width) }
                        let factor = min(1, Double(max(w,h)) / max(target.width,target.height))
                        r.outputWidth = max(1,Int(target.width*factor)); r.outputHeight = max(1,Int(target.height*factor))
                    }
                    configuration.studio = r
                }
                let renderEdit = configuration
                let bytes = try await Task.detached(priority: .userInitiated) { try ImageEditSupport.renderStudio(input, edit: renderEdit, assets: resources) }.value
                guard currentAccount, !cancelBatch else { break }
                let sourceKey = SHA256.hash(data: input).map {String(format:"%02x",$0)}.joined()
                let outputKey = SHA256.hash(data: bytes).map {String(format:"%02x",$0)}.joined()
                if receipts[sourceKey] == nil { receipts[sourceKey] = try await APIClient.shared.uploadImage(data: input) }
                guard currentAccount else { break }
                if pendingResults[outputKey] == nil { pendingResults[outputKey] = try await APIClient.shared.uploadImage(data: bytes) }
                guard currentAccount, let original = receipts[sourceKey], let result = pendingResults[outputKey] else { break }
                let saveRequest = ImageStudioSaveRequest(sourceArtifactId: original.artifactId, resultArtifactId: result.artifactId,
                    sourceHash: original.contentHash, filename: "\(String(filename.prefix(65)))\(batch ? "-\(index+1)" : "").\(format)", edit: configuration)
                let keyEncoder = JSONEncoder(); keyEncoder.outputFormatting = .sortedKeys
                let key = SHA256.hash(data: try keyEncoder.encode(saveRequest)).map { String(format:"%02x",$0) }.joined()
                if saveKeys[key] == nil { saveKeys[key] = UUID().uuidString }
                let response: QCPInvokeResponseDTO<ImageReceiptDTO> = try await CapabilityClient().invoke("media.save_edit", input: saveRequest, idempotencyKey: saveKeys[key])
                guard currentAccount else { break }
                guard response.error == nil, response.status == "completed", let saved = response.events.first?.payload else { throw APIError.network(response.error?.message ?? "保存未返回有效收据") }
                let url = try InboxFileManager.shared.storePrivateFile(bytes, sourceId: saved.artifactId, revision: saved.revision, filename: saved.filename, durable: true)
                completed[index] = url; failures[index] = nil; lastResult = bytes
                if keepDraft { do { try storeDraft() } catch { self.error = "图片已保存，但草稿保存失败：" + error.localizedDescription } }
            } catch { failures[index] = error.localizedDescription; self.error = error.localizedDescription }
        }
    }
    struct Draft: Codable { let source: Data; let recipe: ImageStudioRecipe; let assets: [String: Data]; let format: String; let filename: String }
    func storeDraft() throws {
        guard currentAccount else { throw APIError.network("账号已切换") }
        let bytes = try JSONEncoder().encode(Draft(source:source,recipe:recipe,assets:assets,format:format,filename:filename))
        _ = try InboxFileManager.shared.storePrivateFile(bytes,sourceId:"image-studio-latest",revision:1,filename:"draft.bin",durable:true)
    }
    func restoreDraft() {
        guard currentAccount, let bytes = InboxFileManager.shared.readPrivateFile(sourceId:"image-studio-latest",revision:1,filename:"draft.bin",durable:true),
              let draft = try? JSONDecoder().decode(Draft.self,from:bytes) else { return }
        source = draft.source; photos = [source]; selected = [0]; recipe = draft.recipe; assets = draft.assets; format = draft.format; filename = draft.filename; refresh()
    }
}

extension ImageStudioSaveRequest {
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(sourceArtifactId,forKey:.sourceArtifactId); try c.encode(resultArtifactId,forKey:.resultArtifactId)
        try c.encode(sourceHash,forKey:.sourceHash); try c.encode(filename,forKey:.filename)
        let json = JSONEncoder(); json.keyEncodingStrategy = .convertToSnakeCase
        let value = try JSONDecoder().decode(JSONScalar.self,from:json.encode(edit))
        try c.encode(value,forKey:.edit)
    }
}
