import SwiftUI
import UIKit

struct QuantumSectionHeading: View {
    let eyebrow: String
    let title: String
    var detail: String = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(eyebrow).font(.system(size: 10, weight: .semibold)).tracking(1.8)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            Text(title).font(.custom(AppTheme.Typography.editorialName, size: 34, relativeTo: .largeTitle))
                .foregroundStyle(AppTheme.Colors.textPrimary).lineSpacing(4)
            if !detail.isEmpty {
                Text(detail).font(.system(size: 14)).foregroundStyle(AppTheme.Colors.textSecondary)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Shared, inert photography catalog from the approved prototype. These are
/// visual inspiration, never evidence of a user's destination or actual visits.
struct QuantumSceneryMagazine: View {
    struct Photo: Decodable, Identifiable { let id: String; let caption: String; let alt: String }
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var phase
    @State private var photos: [Photo] = []
    @State private var page = 0
    @State private var lastInteraction = Date()
    private let timer = Timer.publish(every: 5.5, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 14) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("下一段灵感").font(.system(size: 10)).foregroundStyle(AppTheme.Colors.textSecondary)
                    Text("留给想去的地方").font(.custom(AppTheme.Typography.editorialName, size: 23, relativeTo: .title2))
                }
                Spacer()
                Text("01—06\n风景来信").font(.system(size: 9)).foregroundStyle(AppTheme.Colors.textSecondary)
            }.padding(.horizontal, 18).padding(.top, 18)
            TabView(selection: $page) {
                ForEach(Array(photos.enumerated()), id: \.element.id) { index, photo in
                    GeometryReader { geometry in
                    ZStack(alignment: .bottomLeading) {
                        if let url = Bundle.main.url(forResource: photo.id, withExtension: "jpg", subdirectory: "TravelSpace/magazine"),
                           let image = UIImage(contentsOfFile: url.path) {
                            Image(uiImage: image).resizable().scaledToFill()
                                .frame(width: geometry.size.width, height: geometry.size.height)
                                .clipped().accessibilityLabel(photo.alt)
                        }
                        LinearGradient(colors: [.clear, .black.opacity(0.62)], startPoint: .center, endPoint: .bottom)
                        VStack(alignment: .leading, spacing: 8) {
                            Text(String(format: "%02d / 06", index + 1)).font(.system(size: 9)).tracking(1.5)
                            Text(photo.caption).font(.custom(AppTheme.Typography.editorialName, size: 24, relativeTo: .title2))
                            Text("把片刻的风景，留给下一次出发。").font(.system(size: 11))
                        }.foregroundStyle(.white).padding(22)
                    }.frame(width: geometry.size.width, height: geometry.size.height).clipped()
                    }.tag(index).clipShape(RoundedRectangle(cornerRadius: 22))
                }
            }.tabViewStyle(.page(indexDisplayMode: .never)).frame(height: 256)
                .simultaneousGesture(DragGesture(minimumDistance: 3).onChanged { _ in lastInteraction = Date() })
                .padding(.horizontal, 10)
            HStack(spacing: 5) {
                ForEach(photos.indices, id: \.self) { index in
                    Button {
                        lastInteraction = Date()
                        withAnimation(reduceMotion ? nil : AppTheme.Motion.spring) { page = index }
                    } label: {
                        Capsule().fill(AppTheme.Colors.primary.opacity(page == index ? 0.7 : 0.25))
                            .frame(width: page == index ? 24 : 6, height: 4)
                            .frame(minWidth: 30, minHeight: 44)
                    }.accessibilityLabel("查看第\(index + 1)张风景照片")
                        .accessibilityAddTraits(page == index ? .isSelected : [])
                }
            }.padding(.bottom, 2)
        }
        .quantumCard()
        .onAppear {
            guard photos.isEmpty, let url = Bundle.main.url(forResource: "catalog", withExtension: "json", subdirectory: "TravelSpace"),
                  let data = try? Data(contentsOf: url), let catalog = try? JSONDecoder().decode([Photo].self, from: data) else { return }
            photos = Array(catalog.shuffled().prefix(6))
        }
        .onReceive(timer) { _ in
            guard !reduceMotion, phase == .active, !photos.isEmpty, Date().timeIntervalSince(lastInteraction) > 5.5 else { return }
            withAnimation(AppTheme.Motion.spring) { page = (page + 1) % photos.count }
        }
    }
}
