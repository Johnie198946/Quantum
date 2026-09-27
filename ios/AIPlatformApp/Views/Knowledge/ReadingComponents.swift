import SwiftUI

// Reading-only presentation tokens. Shared app colors and business state remain authoritative.
extension AppTheme {
    enum Reading {
        static let paper = Color(hex: "FCFCFA")
        static let ink = Color(hex: "182126")
        static let border = Color(hex: "E3E5ED")
        static let peach = Color(hex: "FBEDE2")
        static let lilac = Color(hex: "F0EBF7")
        static let secondary = Colors.textSecondary
        static let radius: CGFloat = 14
        static let gutter: CGFloat = 20
    }
}

struct ReadingArtwork: View {
    enum Kind: String { case notes, reading, growth }
    let kind: Kind
    var width: CGFloat = 112
    var height: CGFloat = 76

    var body: some View {
        Image("reading_\(kind.rawValue)")
            .resizable().scaledToFit()
            .frame(width: width, height: height)
            .accessibilityHidden(true)
            .allowsHitTesting(false)
    }
}

struct ReadingSectionHeading: View {
    let title: String
    var artwork: ReadingArtwork.Kind? = nil

    var body: some View {
        HStack {
            Text(title).font(.title3.weight(.bold)).foregroundStyle(AppTheme.Reading.ink)
            Spacer(minLength: 8)
            if let artwork { ReadingArtwork(kind: artwork, width: 76, height: 42) }
        }
        .frame(minHeight: 44)
        .accessibilityAddTraits(.isHeader)
    }
}

struct ReadingChip: View {
    let title: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title).font(.caption.weight(.medium))
                .foregroundStyle(selected ? AppTheme.Reading.ink : AppTheme.Reading.secondary)
                .padding(.horizontal, 14).padding(.vertical, 10)
                .background(selected ? AppTheme.Colors.mistMint : .white, in: Capsule())
                .overlay(Capsule().stroke(selected ? AppTheme.Colors.primary.opacity(0.15) : AppTheme.Reading.border, lineWidth: 0.7))
                .frame(minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

struct ReadingPaperCorner: Shape {
    func path(in rect: CGRect) -> Path {
        Path { path in
            path.move(to: CGPoint(x: rect.maxX, y: rect.minY))
            path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
            path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
            path.closeSubpath()
        }
    }
}

struct ReadingNoteTile<Content: View>: View {
    let open: () -> Void
    let pin: () -> Void
    let trash: () -> Void
    @ViewBuilder let content: () -> Content
    @State private var suppressOpeningUntil = Date.distantPast

    var body: some View {
        Button {
            guard Date() > suppressOpeningUntil else { return }
            open()
        } label: { content() }
        .buttonStyle(.plain)
        .simultaneousGesture(DragGesture(minimumDistance: 10)
            .onChanged { _ in suppressOpeningUntil = Date().addingTimeInterval(0.5) }
            .onEnded { value in
                suppressOpeningUntil = Date().addingTimeInterval(0.5)
                guard abs(value.translation.width) > 60,
                      abs(value.translation.width) > abs(value.translation.height) * 2 else { return }
                if value.translation.width > 0 { pin() } else { trash() }
            })
    }
}

struct ReadingNoteCard: View {
    let note: KnowledgeNote
    let preview: String
    let backlinkCount: Int
    let index: Int

    private var surface: Color {
        switch index % 3 {
        case 1: return AppTheme.Reading.peach
        case 2: return AppTheme.Reading.lilac
        default: return .white
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 4) {
                Text(note.title).font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppTheme.Reading.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if note.isPinned {
                    Image(systemName: "pin.fill").font(.caption2).foregroundStyle(AppTheme.Colors.primary)
                }
            }
            if !preview.isEmpty {
                Text(preview).font(.footnote).lineLimit(3)
                    .foregroundStyle(AppTheme.Reading.secondary)
            }
            Spacer(minLength: 14)
            VStack(alignment: .leading, spacing: 4) {
                Text(note.updatedAt, style: .relative)
                if !note.tags.isEmpty {
                    Text(note.tags.prefix(2).map { "#\($0)" }.joined(separator: " ")).lineLimit(2)
                }
                if backlinkCount > 0 { Label("\(backlinkCount)", systemImage: "link") }
            }
            .font(.caption).foregroundStyle(AppTheme.Reading.secondary)
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 172, alignment: .topLeading)
        .background(surface, in: RoundedRectangle(cornerRadius: AppTheme.Reading.radius))
        .overlay(RoundedRectangle(cornerRadius: AppTheme.Reading.radius).stroke(AppTheme.Reading.border.opacity(0.8), lineWidth: 0.6))
        .overlay(alignment: .bottomTrailing) {
            ReadingPaperCorner().fill(AppTheme.Colors.mistLilac).frame(width: 18, height: 18)
                .clipShape(UnevenRoundedRectangle(bottomTrailingRadius: AppTheme.Reading.radius))
                .accessibilityHidden(true).allowsHitTesting(false)
        }
        .overlay(alignment: .top) {
            if index % 3 == 1 {
                Rectangle().fill(AppTheme.Colors.mistMint.opacity(0.85))
                    .frame(width: 46, height: 10).offset(y: -5)
                    .accessibilityHidden(true).allowsHitTesting(false)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityHint("打开笔记；左右轻扫或长按可置顶、移到废纸篓")
    }
}

#if DEBUG
// Deterministic, local-only fixtures for the approved layout; never used for production data.
extension SubscriptionCenterResponse {
    static var readingDesignPreview: Self {
        var center = bookshelfPreview
        let titles = [
            "AI 把会议纪要变成任务表之后，先别点“导入”",
            "两座码头的金色账簿", "群岛灯塔的潮汐日志", "七座门为什么同时打开了",
            "没有人改过账本，为什么昨天变了", "当钟声只剩一个数字", "万路城的最后一张地图"
        ]
        let books = titles.enumerated().map { index, title in
            KnowledgeBookDTO(id: "reading-design-\(index)", title: title, author: "Quantumn",
                             authorSource: "raw", summary: title, coverTheme: index == 0 ? "science" : "history",
                             coverVariant: index, coverVersion: 1, securityLevel: "green", knowledgeLevel: "K5",
                             freshness: "current", sourceCount: 1,
                             seriesId: index == 0 ? "practice" : "fables",
                             seriesTitle: index == 0 ? "趣味 AI 落地经历" : "概念寓言",
                             issueDate: "2026-09-\(20 + index)", publicationFormat: "chapter")
        }
        center.bookshelves = [.init(id: "reading-design", title: "概念寓言", securityLevel: "green", bookCount: books.count, books: books)]
        return center
    }
}
#endif

struct ReadingPublicationDisclosureStyle: DisclosureGroupStyle {
    func makeBody(configuration: Configuration) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { configuration.isExpanded.toggle() } label: {
                HStack {
                    configuration.label
                    Spacer(minLength: 8)
                    Image(systemName: configuration.isExpanded ? "chevron.up" : "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.primary)
                }
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityValue(configuration.isExpanded ? "已展开" : "已折叠")
            if configuration.isExpanded { configuration.content }
        }
    }
}
