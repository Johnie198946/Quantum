import SwiftUI
import PhotosUI
import Photos

extension ImageWorkbench {
    func tabs(_ options:[String], selection:Binding<String>) -> some View {
        HStack(spacing:8) { ForEach(options,id:\.self) { title in
            Button { selection.wrappedValue = title } label: {
                Text(["jpg","png"].contains(title) ? title.uppercased() : title).font(.subheadline.weight(.medium)).frame(maxWidth:.infinity,minHeight:38)
                    .background(selection.wrappedValue == title ? Color(hex:"DDECE2") : .clear,in:Capsule())
            }
        } }.foregroundStyle(tint)
    }
    func recipeSlider(_ name:String,_ path:WritableKeyPath<ImageStudioRecipe,Double>,_ range:ClosedRange<Double>, suffix:String = "") -> some View {
        VStack(spacing:4) {
            HStack { Text(name); Spacer(); Text(name == "图片质量" ? "\(Int(session.recipe[keyPath:path]*100))%" : String(format:"%.2f",session.recipe[keyPath:path])+suffix).monospacedDigit().foregroundStyle(.secondary) }.font(.footnote)
            Slider(value:Binding(get:{session.recipe[keyPath:path]},set:{session.recipe[keyPath:path] = $0}),in:range,onEditingChanged:sliderEditing).frame(minHeight:32)
        }
    }
    func sliderEditing(_ active:Bool) {
        if active { sliderStart = session.recipe }
        else if let before = sliderStart { session.remember(before); sliderStart = nil }
    }
    func layerSlider(_ name:String,_ path:WritableKeyPath<ImageStudioLayer,Double>,_ range:ClosedRange<Double>, multiplier:Double = 1) -> some View {
        VStack(spacing:3) {
            HStack { Text(name); Spacer(); Text(String(format:"%.0f",(currentLayer?[keyPath:path] ?? 0)*multiplier)).monospacedDigit().foregroundStyle(.secondary) }.font(.footnote)
            Slider(value:Binding(get:{currentLayer?[keyPath:path] ?? range.lowerBound},set:{ value in
                if let i = layerIndex, !session.recipe.layers[i].locked { session.recipe.layers[i][keyPath:path] = value }
            }),in:range,onEditingChanged:sliderEditing).frame(minHeight:32).disabled(currentLayer?.locked == true)
        }
    }
    var textPanel: some View {
        VStack(spacing:12) {
            TextField("写下此刻的心情",text:Binding(get:{currentLayer?.text ?? ""},set:{ value in editLayer { $0.text = String(value.prefix(2000)) } }),axis:.vertical)
                .lineLimit(1...3).padding(10).background(AppTheme.Colors.background,in:RoundedRectangle(cornerRadius:12))
                .accessibilityIdentifier("studio-text-input")
            tabs(["字体","样式","颜色","排版"],selection:$textTab)
            if textTab == "字体" {
                HStack(spacing:10) { ForEach(["sans","serif","hand"],id:\.self) { font in
                    Button { editLayer { $0.font = font } } label: {
                        VStack(spacing:5) {
                            Text("晴日").font(Font(ImageEditSupport.studioFont(font,size:25)))
                            Text(["sans":"清新黑体","serif":"文艺宋体","hand":"手写心情"][font]!).font(.caption2)
                        }.frame(maxWidth:.infinity,minHeight:60).background(currentLayer?.font == font ? Color(hex:"DDECE2") : AppTheme.Colors.background,in:RoundedRectangle(cornerRadius:12))
                    }
                } }
                HStack {
                    layerSlider("字号",\.fontSize,0.02...0.25,multiplier:400)
                    Button { editLayer { $0.fontSize = max(0.02,$0.fontSize-0.005) } } label: { Image(systemName:"minus").frame(width:44,height:44).background(AppTheme.Colors.background,in:Circle()) }.accessibilityLabel("减小字号")
                    Button { editLayer { $0.fontSize = min(0.25,$0.fontSize+0.005) } } label: { Image(systemName:"plus").frame(width:44,height:44).background(AppTheme.Colors.background,in:Circle()) }.accessibilityLabel("增大字号")
                }
                textPalette
                textAlignment
            } else if textTab == "颜色" {
                textPalette
                ColorPicker("自选颜色",selection:Binding(get:{Color(uiColor:ImageEditSupport.studioColor(currentLayer?.color ?? "FFF7EC"))},set:{ color in
                    var r:CGFloat = 0,g:CGFloat = 0,b:CGFloat = 0,a:CGFloat = 0
                    UIColor(color).getRed(&r,green:&g,blue:&b,alpha:&a)
                    editLayer { $0.color = String(format:"%02X%02X%02X",Int(r*255),Int(g*255),Int(b*255)) }
                }),supportsOpacity:false)
            } else if textTab == "样式" {
                layerSlider("描边",\.outline,0...0.1,multiplier:100)
                layerSlider("阴影",\.shadow,0...0.04,multiplier:1000)
            } else {
                textAlignment
                layerSlider("字间距",\.tracking,-0.02...0.04,multiplier:1000)
                layerSlider("文本框宽度",\.width,0.1...1.5,multiplier:100)
            }
        }.disabled(session.busy || currentLayer?.locked == true)
    }
    var textPalette: some View {
                HStack { ForEach(["FFF7EC","1F2D2E","3F7278","F3CDAE","6673A6","DC8490"],id:\.self) { hex in
                    Button { editLayer { $0.color = hex } } label: {
                        Circle().fill(Color(uiColor:ImageEditSupport.studioColor(hex))).frame(width:36,height:36)
                            .overlay(Circle().stroke(currentLayer?.color == hex ? tint : .gray.opacity(0.2),lineWidth:2)).padding(4)
                    }.accessibilityLabel("颜色 \(hex)")
                } }
    }
    var textAlignment: some View {
                HStack { ForEach(["left","center","right"],id:\.self) { value in
                    Button { editLayer { $0.alignment = value } } label: { Image(systemName:"text.align\(value)").frame(maxWidth:.infinity,minHeight:40) }.accessibilityLabel(["left":"左对齐","center":"居中","right":"右对齐"][value]!)
                } }
    }
    var layersPanel: some View {
        VStack(spacing:10) {
            HStack { Text("图层").font(.headline); Spacer(); Button("添加文字",systemImage:"plus",action:addText) }
            ScrollView {
                VStack(spacing:6) {
                    ForEach(Array(session.recipe.layers.enumerated().reversed()),id:\.element.id) { index, layer in
                        HStack(spacing:8) {
                            Button { selectedLayer = layer.id } label: {
                                HStack { StudioLayerThumbnail(layer:layer,data:layer.assetId.flatMap { session.assets[$0] }).frame(width:36,height:40)
                                    Text(layer.text.isEmpty ? "文字图层" : layer.text).font(.subheadline).lineLimit(1); Spacer() }
                            }
                            Button { change { $0.layers[index].visible.toggle() } } label: { Image(systemName:layer.visible ? "eye" : "eye.slash").frame(width:44,height:44) }.accessibilityLabel("显示或隐藏图层")
                            Button { change { $0.layers[index].locked.toggle() } } label: { Image(systemName:layer.locked ? "lock.fill" : "lock.open").frame(width:44,height:44) }.accessibilityLabel("锁定或解锁图层")
                            Menu { Button("上移一层") { moveLayer(index,by:1) }.disabled(index == session.recipe.layers.count-1 || layer.locked)
                                Button("下移一层") { moveLayer(index,by:-1) }.disabled(index == 0 || layer.locked)
                                if layer.kind == "text" { Button("编辑文字") { selectedLayer = layer.id; toolBaseline = session.recipe; panel = .text }.disabled(layer.locked) }
                            } label: { Image(systemName:"line.3.horizontal").frame(width:44,height:44) }.accessibilityLabel("图层顺序")
                        }.padding(.horizontal,8).background(layer.id == selectedLayer ? Color(hex:"DDECE2") : AppTheme.Colors.background,in:RoundedRectangle(cornerRadius:12))
                    }
                    HStack { Image(systemName:"photo"); Text("原始图片"); Spacer(); Image(systemName:"lock.fill") }.font(.footnote).foregroundStyle(.secondary).padding(12)
                }
            }.frame(maxHeight:165)
            if currentLayer != nil {
                layerSlider("不透明度",\.opacity,0...1,multiplier:100)
                HStack {
                    Menu(currentLayer?.blend == "normal" ? "正常混合" : currentLayer?.blend ?? "") {
                        ForEach(["normal","multiply","screen","overlay"],id:\.self) { mode in Button(["normal":"正常","multiply":"正片叠底","screen":"滤色","overlay":"叠加"][mode]!) { editLayer { $0.blend = mode } } }
                    }
                    Spacer()
                    Button("复制",systemImage:"square.on.square") {
                        guard var copy = currentLayer, session.recipe.layers.count < 20 else { return }; copy.id = UUID().uuidString; copy.locked = false; copy.y = min(1,copy.y+0.05)
                        change { $0.layers.append(copy) }; selectedLayer = copy.id
                    }
                    Button("删除",systemImage:"trash",role:.destructive) { if let i = layerIndex { change { $0.layers.remove(at:i) }; selectedLayer = session.recipe.layers.last?.id } }.disabled(currentLayer?.locked == true)
                }.font(.footnote).frame(minHeight:38)
                layerSlider("旋转",\.rotation,-180...180)
                if currentLayer?.kind == "image" { layerSlider("图层尺寸",\.width,0.05...1.5,multiplier:100) }
            } else { Text("添加文字或照片，开始叠加创作").font(.footnote).foregroundStyle(.secondary).padding() }
        }
    }
    func moveLayer(_ index:Int,by delta:Int) { change { $0.layers.swapAt(index,index+delta) } }
    var colorPanel: some View {
        VStack(spacing:14) {
            tabs(["调色","滤镜"],selection:$colorTab)
            if colorTab == "调色" {
                ScrollView(.horizontal,showsIndicators:false) {
                    HStack(spacing:12) { ForEach(["曝光","对比度","饱和度","色温","阴影"],id:\.self) { name in
                        Button { adjustment = name } label: {
                            VStack(spacing:7) { Image(systemName:["曝光":"sun.max","对比度":"circle.lefthalf.filled","饱和度":"drop","色温":"thermometer.medium","阴影":"circle.bottomhalf.filled"][name]!).font(.title3); Text(name).font(.caption) }
                                .frame(width:60,height:64).background(adjustment == name ? Color(hex:"DDECE2") : .clear,in:RoundedRectangle(cornerRadius:14))
                        }
                    } }
                }
                switch adjustment {
                case "曝光": recipeSlider("曝光",\.exposure,-2...2)
                case "对比度": recipeSlider("对比度",\.contrast,0.5...2)
                case "饱和度": recipeSlider("饱和度",\.saturation,0...2)
                case "色温": recipeSlider("色温",\.temperature,2500...10000,suffix:" K")
                default: recipeSlider("阴影",\.shadows,0...1)
                }
                Button("重置调色") { change { $0.exposure = 0; $0.contrast = 1; $0.saturation = 1; $0.temperature = 6500; $0.shadows = 0 } }.font(.footnote)
            }
            Group {
                HStack(spacing:10) { ForEach(["original","sunny","mint","film"],id:\.self) { name in
                    Button { change { $0.filter = name } } label: {
                        VStack(spacing:6) {
                            StudioFilterThumbnail(source:session.source,filter:name).frame(height:70).clipShape(RoundedRectangle(cornerRadius:10))
                                .overlay(RoundedRectangle(cornerRadius:10).stroke(session.recipe.filter == name ? tint : .clear,lineWidth:2))
                            Text(["original":"原图","sunny":"晴日","mint":"薄荷","film":"胶片"][name]!).font(.caption)
                        }.frame(maxWidth:.infinity)
                    }
                } }
                if colorTab == "滤镜" { recipeSlider("滤镜强度",\.intensity,0...1) }
            }
        }
    }
    var repairPanel: some View {
        VStack(spacing:14) {
            HStack { Text("轻轻涂抹，擦去小遗憾").font(.headline); Spacer(); Text("\(Int(zoom*100))%").font(.caption).foregroundStyle(.secondary) }
            HStack {
                Button("画笔",systemImage:"paintbrush.pointed") { erasing = false }.buttonStyle(.bordered).tint(erasing ? .gray : tint)
                Button("擦除选区",systemImage:"eraser") { erasing = true }.buttonStyle(.bordered).tint(erasing ? tint : .gray)
                Spacer()
                Button("重置缩放") { zoom = 1; zoomStart = 1 }.font(.caption)
            }
            HStack { Text("画笔大小").font(.footnote); Slider(value:$brush,in:0.001...0.08); Text("\(Int(brush*1200))").font(.footnote).monospacedDigit() }
            HStack {
                Button("撤销选区",systemImage:"arrow.uturn.backward") { if !pendingStrokes.isEmpty { pendingStrokes.removeLast() } }.disabled(pendingStrokes.isEmpty)
                Spacer()
                Button("预览修复",action:applyRepairs)
                    .buttonStyle(.borderedProminent).foregroundStyle(.white).disabled(pendingStrokes.isEmpty || session.busy)
            }.font(.subheadline)
            Text("双指缩放查看细节；选区只应用于当前照片。") .font(.caption).foregroundStyle(.secondary)
        }
    }
    func applyRepairs() {
        guard !pendingStrokes.isEmpty else { return }
        let original = UIImage(data:session.source)?.size ?? fullDimensions
        let scale = min(fullDimensions.width,fullDimensions.height) / max(1,min(original.width,original.height))
        let strokes = pendingStrokes.map { stroke in
            ImageStudioStroke(id:stroke.id,points:stroke.points.map { ImageEditSupport.sourcePoint($0,recipe:session.recipe) },radius:min(0.08,max(0.001,stroke.radius*scale)))
        }
        change { $0.strokes.append(contentsOf:strokes) }; pendingStrokes = []
    }
    var exportButton: some View {
        Button(panel == .batch ? "保存 \(session.selected.count) 张照片" : "保存副本") { Task {
            if panel == .batch {
                await session.save(batch:true,syncColor:syncColor,syncSize:syncSize,syncText:syncText,syncCrop:syncCrop)
                await saveToPhotos(Array(session.completed.values))
            } else {
                await session.save(batch:false)
                if let url = session.completed[0] { await saveToPhotos([url]) }
            }
        } }.buttonStyle(QuantumPrimaryButtonStyle())
            .disabled(session.busy || session.filename.trimmingCharacters(in:.whitespaces).isEmpty || (panel == .batch && session.selected.isEmpty))
            .accessibilityIdentifier(panel == .batch ? "studio-save-batch" : "studio-save-copy")
    }
    var savePanel: some View {
        VStack(spacing:18) {
            if let preview = session.preview { Image(uiImage:preview).resizable().scaledToFit().frame(height:130).clipShape(RoundedRectangle(cornerRadius:14)) }
            VStack(alignment:.leading,spacing:16) {
                tabs(["jpg","png"],selection:$session.format)
                if session.format == "jpg" { recipeSlider("图片质量",\.quality,0.1...1) }
                HStack { Text("尺寸"); Spacer(); Text("\(Int(exportScale*100))%").monospacedDigit() }.font(.subheadline)
                Slider(value:$exportScale,in:0.1...1,onEditingChanged:{ active in
                    if active { sliderStart = session.recipe }
                    else { resizeOutput(); if let before = sliderStart { session.remember(before); sliderStart = nil } }
                }).accessibilityLabel("输出尺寸百分比")
                HStack {
                    dimensionField("宽度",width:true)
                    Image(systemName:"link").foregroundStyle(tint).accessibilityLabel("宽高保持比例")
                    dimensionField("高度",width:false)
                    Text("px").foregroundStyle(.secondary)
                }
                TextField("文件名",text:$session.filename).textInputAutocapitalization(.never).padding(12).background(AppTheme.Colors.background,in:RoundedRectangle(cornerRadius:12))
                HStack { Text("文件大小"); Spacer(); Text(encodedSize).foregroundStyle(.secondary) }.font(.footnote)
                Text(session.format == "png" ? "PNG 保留透明背景" : "JPG 的透明区域将填充为白色").font(.caption).foregroundStyle(.secondary)
                Toggle("保留可编辑草稿",isOn:$session.keepDraft)
                Toggle("移除位置信息",isOn:$session.recipe.removeLocation)
            }.padding(20).background(.white,in:RoundedRectangle(cornerRadius:24))
            if let url = session.completed[0] {
                Label("已保存到作品文件",systemImage:"checkmark.circle.fill").foregroundStyle(tint)
                HStack { ShareLink(item:url) { Label("导出 / 分享",systemImage:"square.and.arrow.up") }; Spacer()
                    Button(photoSaved ? "已存入相册" : "保存到相册") { Task { await saveToPhotos([url]) } }.disabled(photoSaved || session.busy)
                }.font(.subheadline).padding(.vertical,8)
            }
            Button("批量处理更多照片") { panel = .batch }.frame(minHeight:44)
        }.padding(20).task(id:session.edit) { await calculateSize() }
    }
    var fullDimensions: CGSize {
        let image = UIImage(data:session.source)
        if let crop = session.recipe.crops.last { return CGSize(width:crop.width,height:crop.height) }
        return image.map { CGSize(width:$0.size.width*$0.scale,height:$0.size.height*$0.scale) } ?? CGSize(width:1,height:1)
    }
    func resizeOutput() {
        session.recipe.outputWidth = max(1,Int(fullDimensions.width*exportScale))
        session.recipe.outputHeight = max(1,Int(fullDimensions.height*exportScale))
    }
    func dimensionField(_ label:String,width:Bool) -> some View {
        TextField(label,value:Binding(get:{ width ? session.recipe.outputWidth ?? Int(fullDimensions.width) : session.recipe.outputHeight ?? Int(fullDimensions.height) },set:{ value in
            let maximum = width ? fullDimensions.width : fullDimensions.height
            let before = session.recipe; exportScale = min(1,max(0.1,Double(value)/maximum)); resizeOutput(); session.remember(before)
        }),format:.number).keyboardType(.numberPad).padding(10).background(AppTheme.Colors.background,in:RoundedRectangle(cornerRadius:10)).accessibilityLabel(label)
    }
    func calculateSize() async {
        encodedSize = "计算中…"
        let data = session.source, edit = session.edit, assets = session.assets
        do {
            try await Task.sleep(for:.milliseconds(300)); try Task.checkCancellation()
            let bytes = try await Task.detached(priority:.utility) { try ImageEditSupport.renderStudio(data,edit:edit,assets:assets) }.value
            guard !Task.isCancelled, session.currentAccount else { return }
            encodedSize = ByteCountFormatter.string(fromByteCount:Int64(bytes.count),countStyle:.file)
        } catch is CancellationError { } catch { if !Task.isCancelled { encodedSize = error.localizedDescription } }
    }
    var batchPanel: some View {
        VStack(alignment:.leading,spacing:18) {
            HStack { Text("已选择 \(session.selected.count) 张").font(.subheadline); Spacer() }
            LazyVGrid(columns:Array(repeating:GridItem(.flexible()),count:3),spacing:10) {
                ForEach(session.photos.indices,id:\.self) { index in
                    Button { if session.selected.contains(index) { session.selected.remove(index) } else { session.selected.insert(index) } } label: {
                        ZStack(alignment:.topTrailing) {
                            StudioLayerThumbnail(layer:nil,data:session.photos[index]).frame(height:108).clipped()
                            Image(systemName:session.selected.contains(index) ? "checkmark.circle.fill" : "circle").foregroundStyle(.white,tint).padding(5)
                            if index == 0 { Text("样张").font(.caption2).padding(5).background(tint).foregroundStyle(.white).frame(maxWidth:.infinity,maxHeight:.infinity,alignment:.bottomLeading) }
                            if session.completed[index] != nil { Image(systemName:"checkmark.seal.fill").foregroundStyle(.white,tint).frame(maxWidth:.infinity,maxHeight:.infinity,alignment:.center) }
                        }.clipShape(RoundedRectangle(cornerRadius:12))
                    }.accessibilityLabel("照片 \(index+1)，\(session.selected.contains(index) ? "已选中" : "未选中")")
                }
                PhotosPicker(selection:$morePhotos,maxSelectionCount:max(1,20-session.photos.count),matching:.images) { Image(systemName:"plus").font(.title2).frame(maxWidth:.infinity,minHeight:108).background(.white,in:RoundedRectangle(cornerRadius:12)) }.disabled(session.photos.count >= 20 || session.busy)
            }
            VStack(alignment:.leading,spacing:12) {
                Text("同步当前样张的设置").font(.headline)
                Toggle("调色与滤镜",isOn:$syncColor)
                Toggle("尺寸与质量",isOn:$syncSize)
                Toggle("文字水印",isOn:$syncText)
                Toggle("相同构图",isOn:$syncCrop)
                Text("抠图、修复选区和图片贴图仅保留在样张；文字按相对位置应用。") .font(.caption).foregroundStyle(.secondary)
            }.padding(20).background(.white,in:RoundedRectangle(cornerRadius:24))
            if !session.completed.isEmpty {
                Text("已完成 \(session.completed.count) 张").font(.subheadline)
                ShareLink(items:session.completed.keys.sorted().compactMap { session.completed[$0] }) { Label("导出已完成的照片",systemImage:"square.and.arrow.up") }
                Button("保存已完成照片到相册") { Task { await saveToPhotos(Array(session.completed.values)) } }.disabled(session.busy || photoSaved)
            }
            ForEach(session.failures.keys.sorted(),id:\.self) { index in Text("第 \(index+1) 张：\(session.failures[index] ?? "")").font(.caption).foregroundStyle(.red) }
            if !session.failures.isEmpty { Text("再次保存会重试失败项，已完成的照片不会重复保存。") .font(.caption).foregroundStyle(.secondary) }
        }.padding(20).disabled(session.busy)
            .onChange(of:syncColor) { _,_ in session.completed = [:] }.onChange(of:syncSize) { _,_ in session.completed = [:] }
            .onChange(of:syncText) { _,_ in session.completed = [:] }.onChange(of:syncCrop) { _,_ in session.completed = [:] }
    }
    func saveToPhotos(_ urls:[URL]) async {
        guard !session.busy, session.currentAccount else { return }
        let pending = urls.filter { !albumSaved.contains($0) }
        guard !pending.isEmpty else { return }
        session.busy = true; defer { session.busy = false }
        let status = await PHPhotoLibrary.requestAuthorization(for:.addOnly)
        guard status == .authorized || status == .limited else { session.error = "请在系统设置中允许添加照片；也可以使用导出保存到文件。"; return }
        guard session.currentAccount else { return }
        do {
            try await PHPhotoLibrary.shared().performChanges { for url in pending { PHAssetChangeRequest.creationRequestForAssetFromImage(atFileURL:url) } }
            if session.currentAccount { albumSaved.formUnion(pending); photoSaved = session.completed.values.allSatisfy { albumSaved.contains($0) } }
        } catch { session.error = error.localizedDescription }
    }
}

private struct StudioFilterThumbnail: View {
    let source: Data
    let filter: String
    @State private var image: UIImage?
    var body: some View {
        Group { if let image { Image(uiImage:image).resizable().scaledToFill() } else { Color(hex:"DDECE2") } }
            .task(id:filter) {
                guard let thumbnail = ImageCard.thumbnailData(from:source,maxPixelSize:240) else { return }
                var recipe = ImageStudioRecipe(); recipe.filter = filter
                var edit = ImageEditDTO(format:"jpg",aspectRatio:"original",extractSubject:false,focusX:0.5,focusY:0.5); edit.studio = recipe
                let result = try? await Task.detached(priority:.utility) { try ImageEditSupport.studioImage(thumbnail,edit:edit,preview:true) }.value
                if !Task.isCancelled { image = result }
            }
    }
}

private struct StudioLayerThumbnail: View {
    let layer: ImageStudioLayer?
    let data: Data?
    @State private var image: UIImage?
    var body: some View {
        Group {
            if layer?.kind == "text" { Text("T").font(.system(size:24,design:.serif)).frame(maxWidth:.infinity,maxHeight:.infinity).background(.white.opacity(0.8)) }
            else if let image { Image(uiImage:image).resizable().scaledToFill() }
            else { Color(hex:"DDECE2") }
        }.clipShape(RoundedRectangle(cornerRadius:6)).task(id:layer?.assetId) {
            guard let data else { return }
            let thumb = await Task.detached(priority:.utility) { ImageCard.thumbnailData(from:data,maxPixelSize:240) }.value
            if !Task.isCancelled { image = thumb.flatMap(UIImage.init(data:)) }
        }
    }
}
