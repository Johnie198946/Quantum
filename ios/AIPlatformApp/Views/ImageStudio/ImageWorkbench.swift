import SwiftUI
import PhotosUI
import Mantis

/// The same editor is opened by Workflow and an existing Chat image card.
struct ImageWorkbench: View {
    @Environment(\.dismiss) var dismiss
    @StateObject var session: ImageStudioSession
    let onUse: (Data) -> Void
    enum Panel: String { case home = "图像调整", text = "添加文字", layers = "图层", color = "调色与滤镜", repair = "污点修复", cutout = "提取主体", save = "保存图片", batch = "批量处理" }
    @State var panel: Panel = .home
    @State var selectedLayer: String?
    @State var comparing = false
    @State var showExit = false
    @State var sticker: PhotosPickerItem?
    @State var morePhotos: [PhotosPickerItem] = []
    @State var cropImage: UIImage?
    @State var cropping = false
    @State var gestureStart: ImageStudioRecipe?
    @State var transformStart: ImageStudioRecipe?
    @State var sliderStart: ImageStudioRecipe?
    @State var drawing = ImageStudioStroke()
    @State var pendingStrokes: [ImageStudioStroke] = []
    @State var brush: Double = 0.02
    @State var erasing = false
    @State var zoom: CGFloat = 1
    @State var zoomStart: CGFloat = 1
    @State var textTab = "字体"
    @State var toolBaseline: ImageStudioRecipe?
    @State var colorTab = "调色"
    @State var adjustment = "曝光"
    @State var exportScale: Double = 1
    @State var encodedSize: String = "计算中…"
    @State var syncColor = true
    @State var syncSize = true
    @State var syncText = true
    @State var syncCrop = false
    @State var photoSaved = false
    @State var albumSaved: Set<URL> = []

    init(data: Data, photos: [Data]? = nil, restoreDraft: Bool = false, onUse: @escaping (Data) -> Void) {
        let state = ImageStudioSession(photos ?? [data])
        if restoreDraft { state.restoreDraft() }
        _session = StateObject(wrappedValue: state); self.onUse = onUse
    }
    var tint: Color { AppTheme.Icons.interactive }
    var layerIndex: Int? { session.recipe.layers.firstIndex { $0.id == selectedLayer } }
    var currentLayer: ImageStudioLayer? { layerIndex.map { session.recipe.layers[$0] } }
    var body: some View {
        VStack(spacing: 0) {
            header
            if panel == .save || panel == .batch {
                ScrollView { if panel == .save { savePanel } else { batchPanel } }.scrollDismissesKeyboard(.interactively).disabled(session.busy)
                exportButton.padding(.horizontal,20).padding(.vertical,12)
            } else {
                canvas.frame(maxHeight: .infinity).padding(.horizontal, 18).padding(.top, 6)
                controls.disabled(session.busy)
                    .padding(20).background(.white, in: UnevenRoundedRectangle(topLeadingRadius: 28, topTrailingRadius: 28))
            }
            if let error = session.error {
                Text(error).font(.footnote).foregroundStyle(.red).padding(8).accessibilityIdentifier("studio-error")
            }
            if session.busy {
                HStack { ProgressView(); Text(session.progress.isEmpty ? "正在处理…" : session.progress)
                    if panel == .batch { Button("停止") { session.cancelBatch = true } }
                }.font(.footnote).padding(10)
            }
        }
        .background(AppTheme.Colors.background).foregroundStyle(AppTheme.Colors.textPrimary).tint(tint)
        .interactiveDismissDisabled()
        .confirmationDialog("保留这次编辑？", isPresented: $showExit, titleVisibility: .visible) {
            Button("保存草稿并退出") { do { try session.storeDraft(); dismiss() } catch { session.error = error.localizedDescription } }
            Button("放弃本次修改", role: .destructive) { dismiss() }
            Button("继续编辑", role: .cancel) { }
        }
        .fullScreenCover(isPresented: $cropping) {
            if let cropImage { ImageStudioCropper(image: cropImage) { result in
                let region = result.cropInfo.cropRegion
                let points = [region.topLeft, region.topRight, region.bottomRight, region.bottomLeft]
                    .map { ImageStudioPoint(x: min(1,max(0,$0.x)), y: min(1,max(0,$0.y))) }
                change {
                    $0.crops.append(ImageStudioCrop(corners: points, width: Int(result.croppedImage.size.width * result.croppedImage.scale), height: Int(result.croppedImage.size.height * result.croppedImage.scale)))
                    $0.outputWidth = nil; $0.outputHeight = nil
                }
                exportScale = 1; cropping = false
            } }
        }
        .onChange(of:panel) { old,new in if old == .repair && new != .repair { applyRepairs(); zoom = 1; zoomStart = 1 } }
        .onChange(of: session.recipe) { _, _ in session.completed = [:]; photoSaved = false; session.refresh() }
        .onChange(of: session.format) { _, _ in session.completed = [:]; photoSaved = false }
        .onChange(of: session.filename) { _, _ in session.completed = [:] }
        .onChange(of: sticker) { _, item in if let item { Task { await session.addSticker(item); selectedLayer = session.recipe.layers.last?.id; panel = .layers; sticker = nil } } }
        .onChange(of: morePhotos) { _, items in if !items.isEmpty { Task { await session.addPhotos(items); morePhotos = [] } } }
        .task { session.refresh() }
    }
    var confirmingTool: Bool { [.text,.color,.repair].contains(panel) }
    var header: some View {
        HStack {
            Button {
                if panel == .home { showExit = true }
                else { if confirmingTool, let original = toolBaseline { pendingStrokes = []; change { $0 = original } }; panel = .home; zoom = 1 }
            } label: {
                Group { if confirmingTool { Text("取消") } else { Image(systemName: "chevron.left") } }.frame(width:44,height:44)
            }.accessibilityLabel(panel == .home ? "退出编辑" : "返回工具").disabled(session.busy)
            Spacer()
            if panel == .batch {
                PhotosPicker(selection:$morePhotos,maxSelectionCount:max(1,20-session.photos.count),matching:.images) { Text("添加").frame(width:70,height:44) }.disabled(session.busy || session.photos.count >= 20)
            } else if panel == .save { Color.clear.frame(width:70,height:44) } else {
            Button { if panel == .repair { applyRepairs() }; panel = confirmingTool ? .home : .save } label: {
                Text(confirmingTool ? "完成" : "保存").font(.system(size:15,weight:.semibold)).foregroundStyle(.white).padding(.horizontal,20).frame(height:40)
                    .background(AppTheme.Colors.actionGradient,in:Capsule())
            }.disabled(session.busy).accessibilityIdentifier("studio-save")
            }
        }.overlay { Text(panel == .text ? "文字" : panel == .color ? colorTab : panel == .repair ? "修复" : ([Panel.layers].contains(panel) ? "图像调整" : panel.rawValue)).font(.system(size:19,weight:.semibold)).allowsHitTesting(false) }
            .padding(.horizontal,18).padding(.vertical,10)
    }
    var canvas: some View {
        GeometryReader { geometry in
            if let image = comparing ? UIImage(data:session.source) : session.preview {
                let ratio = image.size.width / image.size.height
                let width = min(geometry.size.width, max(1,geometry.size.height)*ratio)
                let height = width/ratio
                VStack(spacing: 10) {
                    ZStack {
                        Canvas { context, size in
                            context.fill(Path(CGRect(origin:.zero,size:size)),with:.color(.white))
                            for y in stride(from:0.0,to:size.height,by:12) {
                                for x in stride(from:0.0,to:size.width,by:12) where (Int(x/12)+Int(y/12)) % 2 == 0 {
                                    context.fill(Path(CGRect(x:x,y:y,width:12,height:12)),with:.color(.gray.opacity(0.12)))
                                }
                            }
                        }
                        Image(uiImage:image).resizable().scaledToFit()
                        if panel == .repair { strokeOverlay(size: CGSize(width:width,height:height)) }
                        if let layer = currentLayer, layer.visible, !layer.locked, panel == .text || panel == .layers {
                            RoundedRectangle(cornerRadius:4).stroke(tint,lineWidth:1.5)
                                .overlay(alignment:.topLeading) { selectionCorner }
                                .overlay(alignment:.topTrailing) { selectionCorner }
                                .overlay(alignment:.bottomLeading) { selectionCorner }
                                .overlay(alignment:.bottomTrailing) { selectionCorner }
                                .frame(width: width*layer.width, height: max(44,width*(layer.kind == "text" ? layer.fontSize*1.6 : layer.width*0.7)))
                                .rotationEffect(.degrees(layer.rotation)).position(x:width*layer.x,y:height*layer.y)
                        }
                    }
                    .frame(width:width,height:height).contentShape(Rectangle())
                    .gesture(canvasDrag(size:CGSize(width:width,height:height)))
                    .simultaneousGesture(SpatialTapGesture().onEnded { event in
                        if panel == .cutout { Task { await session.lift(x:event.location.x/width,y:event.location.y/height) } }
                    })
                    .scaleEffect(zoom).clipped()
                    .simultaneousGesture(MagnificationGesture().simultaneously(with:RotationGesture()).onChanged { value in
                        if panel == .repair { zoom = min(3,max(1,zoomStart*(value.first ?? 1))) }
                        else if panel == .layers || panel == .text, let i = layerIndex, !session.recipe.layers[i].locked {
                            if transformStart == nil { transformStart = session.recipe }
                            guard let original = transformStart?.layers.first(where:{$0.id == selectedLayer}) else { return }
                            let scale = value.first ?? 1
                            session.recipe.layers[i].width = min(2,max(0.02,original.width*scale))
                            if original.kind == "text" { session.recipe.layers[i].fontSize = min(0.5,max(0.01,original.fontSize*scale)) }
                            session.recipe.layers[i].rotation = (original.rotation+(value.second?.degrees ?? 0)).truncatingRemainder(dividingBy:360)
                        }
                    }.onEnded { _ in
                        zoomStart = zoom
                        if let before = transformStart { session.remember(before); transformStart = nil }
                    })
                    .clipShape(RoundedRectangle(cornerRadius:18))
                    .overlay(alignment:.topLeading) {
                        if panel == .repair, let point = drawing.points.last {
                            Image(uiImage:image).resizable().frame(width:width*2,height:height*2)
                                .offset(x:(0.5-point.x)*width*2,y:(0.5-point.y)*height*2)
                                .frame(width:80,height:80).clipped().clipShape(Circle())
                                .overlay(Circle().stroke(.white,lineWidth:3)).shadow(radius:3).padding(8).allowsHitTesting(false)
                        }
                    }
                    .accessibilityElement(children:.contain).accessibilityLabel("图片编辑画布").accessibilityIdentifier("studio-canvas")
                    .overlay(alignment:.bottom) { canvasToolbar.padding(12) }
                    .overlay(alignment:.top) {
                        if panel == .home { Text(session.filename).font(.caption).padding(.horizontal,12).padding(.vertical,5).background(.black.opacity(0.25),in:Capsule()).foregroundStyle(.white).padding(12) }
                    }
                }.frame(maxWidth:.infinity,maxHeight:.infinity)
            } else { ProgressView().frame(maxWidth:.infinity,maxHeight:.infinity) }
        }
    }
    var selectionCorner: some View { Circle().fill(.white).frame(width:9,height:9).overlay(Circle().stroke(tint,lineWidth:1.5)) }
    var canvasToolbar: some View {
        HStack(spacing:12) {
            icon("撤销", "arrow.uturn.backward", action:session.undo).disabled(session.undoStack.isEmpty || session.busy)
            icon("重做", "arrow.uturn.forward", action:session.redo).disabled(session.redoStack.isEmpty || session.busy)
            Image(systemName:"square.lefthalf.filled").frame(width:44,height:44).background(.black.opacity(0.3),in:Circle()).foregroundStyle(.white)
                .onLongPressGesture(minimumDuration:0.01,perform:{},onPressingChanged:{ comparing = $0 })
                .accessibilityLabel("按住对比原图").accessibilityAddTraits(.isButton).accessibilityAction { comparing.toggle() }
            Spacer()
            icon("图层", "square.3.layers.3d") { panel = .layers; selectedLayer = selectedLayer ?? session.recipe.layers.last?.id }
        }.foregroundStyle(tint)
    }
    @ViewBuilder var controls: some View {
        switch panel {
        case .home: tools
        case .text: textPanel
        case .layers: layersPanel
        case .color: colorPanel
        case .repair: repairPanel
        case .cutout:
            VStack(spacing:14) {
                Label("点一下画面中要保留的人物或物品",systemImage:"square.dashed").font(.subheadline)
                Text("由 iOS 识别主体，保留透明背景。可继续添加文字和贴图。") .font(.footnote).foregroundStyle(.secondary)
                HStack {
                    Button("提取中心主体") { Task { await session.lift(x:0.5,y:0.5) } }.buttonStyle(.borderedProminent).disabled(session.busy)
                    Button("恢复背景") { change { $0.subject = false } }.buttonStyle(.bordered).disabled(session.busy)
                }
            }
        default: EmptyView()
        }
    }
    var tools: some View {
        VStack(spacing:16) {
            LazyVGrid(columns:Array(repeating:GridItem(.flexible()),count:4),spacing:16) {
                tool("构图","crop",0) { openCrop() }
                tool("调色","slider.horizontal.3",1) { toolBaseline = session.recipe; panel = .color; colorTab = "调色" }
                tool("滤镜","camera.filters",2) { toolBaseline = session.recipe; panel = .color; colorTab = "滤镜" }
                tool("文字","textformat",3) { addText() }
                PhotosPicker(selection:$sticker,matching:.images) { toolLabel("贴图","face.smiling",3) }.disabled(session.busy)
                tool("抠图","square.dashed",0) { panel = .cutout }
                tool("修复","bandage",1) { toolBaseline = session.recipe; panel = .repair }
                tool("更多","square.grid.2x2",2) { panel = .batch }
            }
            Button { Task {
                do {
                    let edit = session.edit, data = session.source, assets = session.assets
                    let bytes = try await Task.detached { try ImageEditSupport.renderStudio(data,edit:edit,assets:assets) }.value
                    guard session.currentAccount else { return }; onUse(bytes); dismiss()
                } catch { session.error = error.localizedDescription }
            } } label: { Label("用 Chat 继续调整",systemImage:"bubble.left").font(.footnote).foregroundStyle(.secondary) }.frame(minHeight:32)
        }
    }
    func tool(_ title:String,_ symbol:String,_ color:Int,action:@escaping()->Void) -> some View {
        Button(action:action) { toolLabel(title,symbol,color) }.disabled(session.busy).accessibilityIdentifier("studio-tool-\(title)")
    }
    func toolLabel(_ title:String,_ symbol:String,_ color:Int) -> some View {
        VStack(spacing:7) {
            Group { if symbol == "textformat" { Text("T").font(.system(size:28,design:.serif)) } else { Image(systemName:symbol).font(.system(size:24,weight:.regular)) } }.frame(width:54,height:50)
                .background([Color(hex:"DDECE2"),Color(hex:"DFEBED"),Color(hex:"E7E6F1"),Color(hex:"F8E9D7")][color],in:RoundedRectangle(cornerRadius:16))
            Text(title).font(.system(size:13,weight:.medium))
        }.foregroundStyle(tint).frame(maxWidth:.infinity,minHeight:76)
    }
    func icon(_ title:String,_ symbol:String,action:@escaping()->Void) -> some View {
        Button(action:action) { Image(systemName:symbol).frame(width:44,height:40).background(.black.opacity(0.3),in:Circle()).foregroundStyle(.white) }.accessibilityLabel(title)
    }
    func change(_ update:(inout ImageStudioRecipe)->Void) { let before = session.recipe; update(&session.recipe); session.remember(before) }
    func editLayer(_ update:(inout ImageStudioLayer)->Void) { guard let index = layerIndex, !session.recipe.layers[index].locked else { return }; change { update(&$0.layers[index]) } }
    func addText() {
        guard session.recipe.layers.count < 20 else { session.error = "最多20个图层"; return }
        toolBaseline = session.recipe
        let layer = ImageStudioLayer(); change { $0.layers.append(layer) }; selectedLayer = layer.id; panel = .text
    }
    func openCrop() {
        guard session.recipe.crops.count < 12 else { session.error = "最多连续裁剪12次，请保存副本后继续"; return }
        session.busy = true
        let data = session.source
        var edit = session.edit
        var r = session.recipe; r.layers = []; r.outputWidth = nil; r.outputHeight = nil; edit.studio = r
        let cropEdit = edit
        Task {
            defer { session.busy = false }
            do { let image = try await Task.detached { try ImageEditSupport.studioImage(data,edit:cropEdit) }.value
                guard session.currentAccount else { return }; cropImage = image; cropping = true
            } catch { session.error = error.localizedDescription }
        }
    }
    func canvasDrag(size:CGSize) -> some Gesture {
        DragGesture(minimumDistance:0).onChanged { value in
            guard !session.busy else { return }
            if panel == .repair {
                let p = ImageStudioPoint(x:min(1,max(0,value.location.x/size.width)),y:min(1,max(0,value.location.y/size.height)))
                if erasing {
                    pendingStrokes.removeAll { stroke in stroke.points.contains { hypot(($0.x-p.x)*size.width,($0.y-p.y)*size.height) < brush*min(size.width,size.height)*2 } }
                } else if drawing.points.count < 256 { drawing.radius = brush; drawing.points.append(p) }
            } else if panel == .text || panel == .layers, let i = layerIndex, !session.recipe.layers[i].locked {
                if gestureStart == nil { gestureStart = session.recipe }
                guard let initial = gestureStart?.layers.first(where:{$0.id == selectedLayer}) else { return }
                session.recipe.layers[i].x = min(1,max(0,initial.x+value.translation.width/size.width))
                session.recipe.layers[i].y = min(1,max(0,initial.y+value.translation.height/size.height))
            }
        }.onEnded { _ in
            if panel == .repair {
                if !drawing.points.isEmpty && pendingStrokes.count + session.recipe.strokes.count < 40 { pendingStrokes.append(drawing) }
                drawing = ImageStudioStroke()
            }
            if let before = gestureStart { session.remember(before); gestureStart = nil }
        }
    }
    func strokeOverlay(size:CGSize) -> some View {
        Canvas { context,_ in
            for stroke in pendingStrokes + (drawing.points.isEmpty ? [] : [drawing]) {
                var path = Path()
                for (i,p) in stroke.points.enumerated() {
                    let point = CGPoint(x:p.x*size.width,y:p.y*size.height)
                    if i == 0 { path.move(to:point) } else { path.addLine(to:point) }
                }
                let radius = stroke.radius*min(size.width,size.height)
                if let p = stroke.points.first, stroke.points.count == 1 { path.addEllipse(in:CGRect(x:p.x*size.width-radius,y:p.y*size.height-radius,width:radius*2,height:radius*2)) }
                context.stroke(path,with:.color(.mint.opacity(0.65)),style:StrokeStyle(lineWidth:radius*2,lineCap:.round,lineJoin:.round))
            }
        }.allowsHitTesting(false)
    }
}

private struct ImageStudioCropper: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var session = CropSession()
    let image: UIImage
    let onCrop: (CropResult)->Void
    var body: some View {
        VStack {
            HStack { Button("取消") { dismiss() }; Spacer(); Text("构图").bold(); Spacer(); Button("完成") { session.crop() } }.padding()
            Text("调整照片构图，文字与贴图保持相对位置").font(.caption).foregroundStyle(.secondary)
            ImageCropper(image:image,session:session).appearance(.forceLight).builtInToolbarVisible(false)
                .onCrop(onCrop).onCancel { dismiss() }
            HStack {
                Button("自由") { session.setAspectRatio(.free) }
                ForEach(["1:1","3:4","4:3","9:16"],id:\.self) { name in
                    Button(name) { let n = name.split(separator:":").compactMap { Double($0) }; session.setAspectRatio(.fixed(n[0]/n[1])) }
                }
            }.buttonStyle(.bordered).padding(.horizontal)
            HStack { Button("旋转",systemImage:"rotate.right") { session.rotate() }; Button("翻转",systemImage:"arrow.left.and.right.righttriangle.left.righttriangle.right") { session.flip() }; Button("重置") { session.reset() } }.padding()
        }.tint(AppTheme.Icons.interactive).background(AppTheme.Colors.background)
    }
}

struct ImageStudioEntry: View {
    let onChat: (Data) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var items: [PhotosPickerItem] = []
    @State private var photos: [Data] = []
    @State private var error: String?
    @State private var loading = false
    @State private var editing = false
    @State private var restoring = false
    var body: some View {
        NavigationStack {
            VStack(spacing:24) {
                Spacer()
                Image(systemName:"photo.on.rectangle.angled").font(.system(size:64)).foregroundStyle(AppTheme.Icons.interactive)
                Text("把日常，调成喜欢的样子").font(.title2.bold())
                Text("手动修图 · 添加文字 · 批量保存").font(.subheadline).foregroundStyle(.secondary)
                PhotosPicker(selection:$items,maxSelectionCount:20,matching:.images) { Label("选择照片",systemImage:"plus").frame(maxWidth:.infinity) }.buttonStyle(QuantumPrimaryButtonStyle()).disabled(loading)
                Button("继续上次草稿") {
                    let session = ImageStudioSession([]); session.restoreDraft()
                    if !session.source.isEmpty { photos = [session.source]; restoring = true; editing = true } else { error = "暂无可恢复的草稿" }
                }
                if loading { ProgressView("正在读取照片…") }
                if let error { Text(error).foregroundStyle(.red).font(.footnote) }
                Spacer()
            }.padding(24).background(AppTheme.Colors.background).navigationTitle("处理图像").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement:.cancellationAction) { Button("关闭") { dismiss() } } }
                .onChange(of:items) { _, selection in
                    guard !selection.isEmpty else { return }; loading = true
                    Task {
                        let session = ImageStudioSession([]); await session.addPhotos(selection)
                        photos = session.photos; restoring = false; error = session.error; loading = false
                        if !photos.isEmpty { editing = true }
                    }
                }
                .fullScreenCover(isPresented:$editing) {
                    if let first = photos.first { ImageWorkbench(data:first,photos:photos,restoreDraft:restoring) { data in onChat(data) } }
                }
        }
    }
}
