//
//  Theme.swift
//  AIPlatformApp
//
//  Design System Tokens & Styling Definitions
//  iOS 17+ light-only interface. Imported documents keep their original colors.
//

import SwiftUI

#if os(iOS)
import UIKit
#endif

public enum AppTheme {
    
    // MARK: - Color Palette
    public enum Colors {
        // Logo 原色只用于品牌标记和数据序列；界面交互使用下方 Aurora 语义色。
        public static let quantumCyan = Color(hex: "78AEB0")
        public static let quantumBlue = Color(hex: "58758E")
        public static let quantumViolet = Color(hex: "7A80AE")
        public static let auroraViolet = Color(hex: "7A80AE")
        public static let auroraBlue = Color(hex: "58758E")
        public static let auroraCyan = Color(hex: "78AEB0")
        public static let auroraPink = Color(hex: "D9A8A0")
        public static let emberOrange = Color(hex: "E97942")
        public static let emberAmber = Color(hex: "F2A15F")
        public static let emberCream = Color(hex: "FFF7EC")
        public static let emberInk = Color(hex: "2B1811")
        /// 历史命名兼容：交互入口沿用当前蓝紫语义色。
        public static let interactiveBlue = Color(hex: "3F7278")
        public static let interactiveViolet = Color(hex: "6673A6")

        // 语义别名（收敛到 Quantum 真值，杜绝双源漂移）
        public static let brandPrimary = quantumBlue
        public static let brandSecondary = quantumViolet
        public static let brandTertiary = quantumCyan

        // Quantum 光谱只用于品牌标识；结构性操作使用暖色 Ember 渐变。
        public static let quantumGradient = LinearGradient(
            colors: [Color(hex: "6673A6"), Color(hex: "58758E"), Color(hex: "78A596")],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        public static let actionGradient = LinearGradient(
            colors: [Color(hex: "3F7278"), Color(hex: "557B92"), Color(hex: "6673A6")],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        public static let userBubbleGradient = LinearGradient(
            colors: [Color(hex: "557B92"), Color(hex: "6673A6")],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )

        // primary / accent 统一为 Quantum Blue（主 CTA / 链接 / TabBar 选中高亮）
        public static let primary = interactiveBlue
        public static let accent = interactiveViolet
        // onPrimary：primary（饱和蓝）之上的文字与图标——亮暗恒为白字，保证 WCAG AA 对比
        public static let onPrimary = Color(hex: "FFFFFF")
        // onSemantic：语义色（黄/绿）按钮上的深色文字——亮暗通用（浅色底必须深字才达 AA）
        public static let onSemantic = Color(hex: "1F1F1F")

        // 对话气泡系统：用户气泡三色流光渐变（白字），助手卡片冷岩/深曜石底 + 量子青/蓝微光细边框
        public static let userBubbleBackground = Color(hex: "557B92")
        public static let assistantBubbleBorder = adaptive("8FB4AE", "78AEB0")
        
        // Security Classification Three-Color Tokens (红黄绿三色安全徽章) → System Semantic Colors
        public static var securityRed: Color {
            #if os(iOS)
            Color(uiColor: .systemRed)
            #else
            Color.red
            #endif
        }
        public static var securityYellow: Color {
            #if os(iOS)
            Color(uiColor: .systemYellow)
            #else
            Color.yellow
            #endif
        }
        public static var securityGreen: Color {
            #if os(iOS)
            Color(uiColor: .systemGreen)
            #else
            Color.green
            #endif
        }
        
        // Semantic Status Colors → System Semantic Colors
        public static var statusIdle: Color { adaptive("7B849E", "9EA7C4") }
        public static var statusRunning: Color { adaptive("C9572D", "F08A4B") }
        public static var statusCompleted: Color { adaptive("199B75", "4DD5A8") }
        public static var statusError: Color { adaptive("D94A67", "FF7690") }
        public static var statusWarning: Color { adaptive("C98214", "F3B64F") }
        
        // Third-Party Brand Colors (收敛进 Token 域)
        public static let thirdPartyWeChat = Color(hex: "07C160")
        public static let thirdPartyAlipay = Color(hex: "1677FF")
        
        // Code Window & Syntax Colors (功能性例外 · 豁免低饱和)
        public static let codeWindowRed = Color(hex: "FF5F56")
        public static let codeWindowYellow = Color(hex: "FFBD2E")
        public static let codeWindowGreen = Color(hex: "27C93F")
        public static let codeSyntaxForeground = Color(hex: "E6EDF3")
        
        // V3–V5 原型的暖象牙纸面与清新知识色。
        public static var background: Color { adaptive("F7F5EF", "17141F") }
        public static var secondaryBackground: Color { adaptive("F2F3EF", "211D2B") }
        public static var tertiaryBackground: Color { adaptive("E9EFEE", "2B2637") }
        public static var cardBackground: Color { adaptive("FFFFFF", "24202E") }
        public static var surfaceElevated: Color { adaptive("FFFFFF", "302A3B") }
        public static var groupedBackground: Color { background }
        public static var surfaceTint: Color { adaptive("EEF3F0", "352E42") }
        public static var selectionTint: Color { adaptive("E3EEEB", "403652") }
        public static let paper = Color(hex: "F7F5EF")
        public static let mistSky = Color(hex: "DFEBED")
        public static let mistMint = Color(hex: "DDECE2")
        public static let mistLilac = Color(hex: "E7E6F1")
        public static let mistRose = Color(hex: "F3E2DE")
        public static let dawnPeach = Color(hex: "F3CDAE")
        public static let leaf = Color(hex: "78947E")
        public static var successSurface: Color { adaptive("E7F8F2", "17342D") }
        public static var warningSurface: Color { adaptive("FFF4DF", "462B1B") }
        public static var dangerSurface: Color { adaptive("FDECEF", "3D1D22") }
        public static var focusRing: Color { interactiveBlue.opacity(0.28) }
        public static var scrim: Color { Color.black.opacity(0.52) }

        // 头像自适应托盘：暗色下底板 #121316 < 托盘 #16171D < 卡片 #1A1C22（三级亮度递增，杜绝暗色白斑）
        public static let avatarBackplate = adaptive("FFFFFF", "16171D")
        
        // Code Block and Monospace Surfaces
        public static let codeBlockBackground = Color(hex: "1C1C1E")
        public static let codeBlockHeader = Color(hex: "2C2C2E")
        public static let codeSyntaxKeyword = Color(hex: "FF7AB2")
        public static let codeSyntaxString = Color(hex: "FF8170")
        public static let codeSyntaxComment = Color(hex: "7F8C8D")
        public static let codeSyntaxType = Color(hex: "6BDFFF")
        
        // Dynamic Label Colors — Quantum 同源文字（亮 #333333 · 暗 #F5F5F7）
        public static var textPrimary: Color { adaptive("1F2D2E", "F8F4FF") }
        public static var textSecondary: Color { adaptive("667373", "D1C9DC") }
        public static var textTertiary: Color { adaptive("8A9693", "A69BB2") }
        
        // Border & Divider — Quantum 冷调发丝线
        public static var border: Color { adaptive("D8E0DD", "51475E") }

        // Soft Intelligence Bento accent fills（彩色卡片始终搭配指定前景色）
        public static let bentoLavender = Color(hex: "E9E0FB")
        public static let bentoSky = Color(hex: "DDF3FB")
        public static let bentoRose = Color(hex: "F8E4F1")
        public static let bentoAmber = Color(hex: "FFF1D9")
        
        // MARK: - 双模式自适应色辅助
        private static func adaptive(_ light: String, _ dark: String) -> Color {
            return Color(hex: light)
        }
    }

    // MARK: - Semantic Icon Palette
    /// SF Symbols 只引用语义角色，不直接选择品牌原色。
    /// 品牌色只保留给数据可视化与第三方品牌；导航、操作、智能、状态各用一个稳定入口。
    public enum Icons {
        public static var primary: Color { Colors.textPrimary }
        public static var secondary: Color { Colors.textSecondary }
        public static var tertiary: Color { Colors.textTertiary }
        public static let interactive = Colors.interactiveBlue
        public static let intelligence = Colors.quantumViolet
        public static let live = Colors.quantumCyan
        public static var success: Color { Colors.statusCompleted }
        public static var warning: Color { Colors.securityYellow }
        public static var destructive: Color { Colors.statusError }
        public static let onAccent = Colors.onPrimary
        public static var navigationInactive: Color { Colors.textTertiary }
    }
    
    // MARK: - Spacing Tokens
    public enum Spacing {
        public static let xxs: CGFloat = 2
        public static let xs: CGFloat = 4
        public static let sm: CGFloat = 8
        public static let md: CGFloat = 12
        public static let lg: CGFloat = 16
        public static let xl: CGFloat = 20
        public static let xxl: CGFloat = 24
        public static let xxxl: CGFloat = 32
        public static let section: CGFloat = 40
    }

    // MARK: - Semantic Type (Dynamic Type by default)
    public enum Typography {
        public static let hero = Font.system(.largeTitle, design: .rounded, weight: .bold)
        public static let screenTitle = Font.system(.title, design: .rounded, weight: .bold)
        public static let sectionTitle = Font.system(.title2, design: .rounded, weight: .semibold)
        public static let cardTitle = Font.system(.headline, design: .rounded, weight: .semibold)
        public static let body = Font.body
        public static let supporting = Font.subheadline
        public static let label = Font.caption.weight(.semibold)
        public static let micro = Font.caption2.weight(.medium)
    }

    public enum Metrics {
        public static let minimumTouchTarget: CGFloat = 44
        public static let inputHeight: CGFloat = 52
        public static let contentGutter: CGFloat = 20
        public static let readableContentWidth: CGFloat = 720
        public static let floatingTabBarHeight: CGFloat = 64
        public static let panelRadius: CGFloat = 20
    }

    public enum Motion {
        public static let quick = Animation.easeOut(duration: 0.18)
        public static let standard = Animation.easeOut(duration: 0.24)
        public static let spring = Animation.spring(response: 0.36, dampingFraction: 0.90)
    }
    
    // MARK: - Corner Radius Tokens
    public enum Radius {
        public static let xs: CGFloat = 8
        public static let sm: CGFloat = 12
        public static let md: CGFloat = 16
        public static let lg: CGFloat = 20
        public static let xl: CGFloat = 24
        public static let full: CGFloat = 999
    }
    
    // MARK: - Shadows
    public enum Shadows {
        public static func card(colorScheme: ColorScheme) -> some ViewModifier {
            CardShadowModifier(colorScheme: colorScheme)
        }
    }
}

// MARK: - Component Content Assets

/// Generated content artwork used by cards and covers. Interactive controls stay on SF Symbols.
public enum ContentAssetLibrary {
    public static let avatarNames = [
        "avatar_youth_01", "avatar_youth_02", "avatar_youth_03", "avatar_youth_04",
    ]

    public static func avatarAssetName(for value: String?) -> String? {
        guard let value, avatarNames.contains(value) else { return nil }
        return value
    }

    public static func bookCoverName(theme: String?, title: String, variant: Int? = nil) -> String {
        let normalizedTitle = title.lowercased()
        if containsAny(normalizedTitle, ["travel", "trip", "旅行", "京都"]) { return "book_cover_travel" }
        if containsAny(normalizedTitle, ["science", "research", "technology", "ai ", "科学", "研究", "技术", "能源"]) { return "book_cover_science" }
        if containsAny(normalizedTitle, ["history", "strategy", "历史", "战略", "竞品"]) { return "book_cover_history" }
        if let variant {
            let variants = ["book_cover_growth", "book_cover_literature", "book_cover_science", "book_cover_history"]
            let index = (variant % variants.count + variants.count) % variants.count
            return variants[index]
        }
        let normalizedTheme = theme?.lowercased() ?? ""
        if containsAny(normalizedTheme, ["history", "strategy", "competitor"]) { return "book_cover_history" }
        if containsAny(normalizedTheme, ["science", "research", "technology"]) { return "book_cover_science" }
        if containsAny(normalizedTheme, ["product", "methodology", "customer", "growth"]) { return "book_cover_growth" }
        return "book_cover_literature"
    }

    /// Curated, content-specific covers for already published serials. New editions use the
    /// authenticated publication-cover endpoint; these bundled assets govern the existing shelf.
    public static func publicationCoverAssetName(for bookID: String) -> String? {
        [
            "publication-9e5e04c6c07dc21ce840680202c9e15a": "book_publication_receipt",
            "publication-a997229a1b1efd600b9d21e69080d669": "book_publication_gpu_wait",
            "publication-0a002a4a42c4dc9a1d0962ea13950675": "book_publication_seven_gates",
            "publication-01f24971feeb023d69da79e2f05e6129": "book_publication_attention",
            "publication-e7cb8f3397988e37367ecbeeaf754e20": "book_publication_recoverable_files",
            "publication-e1e02beb258aa637301e7f757a954674": "book_publication_merkle_ledger",
        ][bookID]
    }

    public struct BookCoverIdentity: Equatable {
        public let palette: Int
        public let motif: Int
        public let accent: Int
    }

    /// Stable across launches so an existing publication keeps its visual identity while every
    /// newly published book gets a distinct cover without a network or image-generation request.
    public static func bookCoverIdentity(
        theme: String?,
        title: String,
        seed: String,
        variant: Int? = nil
    ) -> BookCoverIdentity {
        let themeFamily = coverThemeFamily(theme: theme, title: title)
        let value = stableHash("\(themeFamily)|\(seed)|\(title)|\(variant ?? 0)")
        return BookCoverIdentity(
            palette: (themeFamily + Int(value % 3)) % 8,
            motif: variant.map { abs($0) % 6 } ?? Int((value >> 8) % 6),
            accent: Int((value >> 16) % 5)
        )
    }

    public static func journalCoverName(tags: [String], title: String) -> String {
        let haystack = (tags + [title]).joined(separator: " ").lowercased()
        if containsAny(haystack, ["travel", "trip", "旅行", "京都"]) { return "journal_cover_travel" }
        if containsAny(haystack, ["idea", "inspiration", "design", "想法", "灵感", "设计"]) { return "journal_cover_ideas" }
        return "journal_cover_reading"
    }

    public static func contentIconName(for intent: String) -> String {
        let value = intent.lowercased()
        if containsAny(value, ["travel", "trip", "旅行"]) { return "content_icon_travel" }
        if containsAny(value, ["research", "science", "研究", "科学"]) { return "content_icon_research" }
        if containsAny(value, ["idea", "inspiration", "建议", "灵感"]) { return "content_icon_inspiration" }
        if containsAny(value, ["read", "article", "阅读", "文章", "整理"]) { return "content_icon_reading" }
        if containsAny(value, ["life", "daily", "生活", "日记"]) { return "content_icon_life" }
        return "content_icon_learning"
    }

    private static func containsAny(_ value: String, _ candidates: [String]) -> Bool {
        candidates.contains(where: value.contains)
    }

    private static func coverThemeFamily(theme: String?, title: String) -> Int {
        let value = "\(theme ?? "") \(title)".lowercased()
        if containsAny(value, ["travel", "trip", "旅行", "京都"]) { return 5 }
        if containsAny(value, ["math", "数学", "代数", "分析", "定理"]) { return 2 }
        if containsAny(value, ["science", "research", "technology", "ai", "科学", "研究", "技术", "能源"]) { return 3 }
        if containsAny(value, ["history", "strategy", "历史", "战略", "竞品"]) { return 6 }
        if containsAny(value, ["growth", "psychology", "成长", "心理", "习惯"]) { return 1 }
        if containsAny(value, ["practice", "methodology", "教程", "实践", "方法"]) { return 4 }
        return 0
    }

    private static func stableHash(_ value: String) -> UInt64 {
        value.utf8.reduce(UInt64(14_695_981_039_346_656_037)) { hash, byte in
            (hash ^ UInt64(byte)) &* 1_099_511_628_211
        }
    }
}

public struct UserAvatarView: View {
    private let value: String?
    private let size: CGFloat

    public init(value: String?, size: CGFloat) {
        self.value = value
        self.size = size
    }

    public var body: some View {
        Group {
            if let asset = ContentAssetLibrary.avatarAssetName(for: value) {
                Image(asset).resizable().scaledToFill()
            } else if let value, let url = URL(string: value), ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
                AsyncImage(url: url) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    avatarFallback
                }
            } else {
                Image(systemName: value ?? "person.crop.circle.fill")
                    .resizable()
                    .scaledToFit()
                    .padding(size * 0.18)
                    .foregroundStyle(AppTheme.Icons.interactive)
                    .background(AppTheme.Colors.surfaceTint)
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .overlay { Circle().stroke(Color.white.opacity(0.84), lineWidth: 1) }
        .accessibilityLabel("用户头像")
    }

    private var avatarFallback: some View {
        Image(systemName: "person.crop.circle.fill")
            .resizable()
            .scaledToFit()
            .padding(size * 0.18)
            .foregroundStyle(AppTheme.Icons.interactive)
            .background(AppTheme.Colors.surfaceTint)
    }
}

public struct IllustratedBookCover: View {
    private let title: String
    private let author: String
    private let theme: String?
    private let variant: Int?
    private let seed: String
    private let width: CGFloat
    private let image: UIImage?

    public init(title: String, author: String, theme: String?, variant: Int? = nil, seed: String? = nil, width: CGFloat, image: UIImage? = nil) {
        self.title = title
        self.author = author
        self.theme = theme
        self.variant = variant
        self.seed = seed ?? title
        self.width = width
        self.image = image
    }

    public var body: some View {
        let identity = ContentAssetLibrary.bookCoverIdentity(
            theme: theme, title: title, seed: seed, variant: variant
        )
        let colors = coverPalette(identity.palette)
        ZStack(alignment: .topLeading) {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
                    .accessibilityHidden(true)
                LinearGradient(
                    colors: [.clear, Color.white.opacity(0.18), Color(hex: "FFFDF7").opacity(0.96)],
                    startPoint: .top,
                    endPoint: .bottom
                )
            } else if let asset = ContentAssetLibrary.publicationCoverAssetName(for: seed) {
                Image(asset)
                    .resizable()
                    .scaledToFill()
                    .accessibilityHidden(true)
                LinearGradient(
                    colors: [.clear, Color.white.opacity(0.18), Color(hex: "FFFDF7").opacity(0.96)],
                    startPoint: .top,
                    endPoint: .bottom
                )
            } else {
                LinearGradient(colors: colors, startPoint: .topLeading, endPoint: .bottomTrailing)
                coverMotif(identity: identity, foreground: colors.last ?? AppTheme.Colors.leaf)
                    .accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: width < 100 ? 4 : 7) {
                Text(coverKicker)
                    .font(.system(size: width < 100 ? 6 : 8, weight: .bold, design: .rounded))
                    .tracking(width < 100 ? 0.4 : 0.8)
                    .textCase(.uppercase)
                    .opacity(0.58)
                Spacer(minLength: 2)
                Text(title)
                    .font(.system(size: width < 100 ? 10 : 15, weight: .bold, design: .serif))
                    .lineLimit(width < 80 ? 2 : 3)
                Text(author)
                    .font(.system(size: width < 100 ? 7 : 9, weight: .medium))
                    .lineLimit(1)
                    .opacity(0.62)
            }
            .foregroundStyle(Color(hex: "132A35"))
            .padding(width < 80 ? 7 : 10)
        }
        .frame(width: width, height: width * 1.42)
        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: 6).stroke(Color.white.opacity(0.74), lineWidth: 0.7) }
        .shadow(color: AppTheme.Colors.primary.opacity(0.12), radius: 12, x: 3, y: 8)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("《\(title)》，\(author)")
    }

    private var coverKicker: String {
        let normalized = "\(theme ?? "") \(title)".lowercased()
        if normalized.contains("math") || normalized.contains("数学") { return "STUDY SERIES" }
        if normalized.contains("travel") || normalized.contains("旅行") { return "FIELD NOTES" }
        if normalized.contains("ai") || normalized.contains("技术") { return "QUANTUM EDITIONS" }
        return "QUANTUM LIBRARY"
    }

    private func coverPalette(_ index: Int) -> [Color] {
        let palettes: [[Color]] = [
            [Color(hex: "F7F0DF"), Color(hex: "B8D6C4")],
            [Color(hex: "FFF3E5"), Color(hex: "E8B7A8")],
            [Color(hex: "EAF3F8"), Color(hex: "9CC7DE")],
            [Color(hex: "EEF0FA"), Color(hex: "AEB6E4")],
            [Color(hex: "EAF7F0"), Color(hex: "8DCEB3")],
            [Color(hex: "F4EFE7"), Color(hex: "C6B39B")],
            [Color(hex: "F6ECE8"), Color(hex: "D5A896")],
            [Color(hex: "EDF3E7"), Color(hex: "A8C48F")],
        ]
        return palettes[(index % palettes.count + palettes.count) % palettes.count]
    }

    @ViewBuilder
    private func coverMotif(identity: ContentAssetLibrary.BookCoverIdentity, foreground: Color) -> some View {
        let opacity = 0.24 + Double(identity.accent) * 0.025
        GeometryReader { proxy in
            let size = proxy.size
            ZStack {
                Circle()
                    .fill(Color.white.opacity(0.28))
                    .frame(width: size.width * 0.78)
                    .offset(x: size.width * 0.34, y: -size.height * 0.26)
                switch identity.motif {
                case 0:
                    Image(systemName: "leaf.fill")
                        .font(.system(size: size.width * 0.48, weight: .thin))
                        .rotationEffect(.degrees(-18))
                case 1:
                    Image(systemName: "function")
                        .font(.system(size: size.width * 0.43, weight: .light, design: .serif))
                case 2:
                    Image(systemName: "atom")
                        .font(.system(size: size.width * 0.46, weight: .thin))
                case 3:
                    Image(systemName: "book.closed.fill")
                        .font(.system(size: size.width * 0.38, weight: .light))
                        .rotationEffect(.degrees(-8))
                case 4:
                    Image(systemName: "globe.asia.australia.fill")
                        .font(.system(size: size.width * 0.43, weight: .thin))
                default:
                    Image(systemName: "sparkles")
                        .font(.system(size: size.width * 0.42, weight: .thin))
                }
            }
            .foregroundStyle(foreground.opacity(opacity))
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
            .offset(x: size.width * 0.18, y: size.height * 0.14)
        }
    }
}

// MARK: - Color Hex Initializer
public extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue:  Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

// MARK: - UIColor Hex Initializer (for dynamicProvider)
#if os(iOS)
public extension UIColor {
    convenience init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            red: CGFloat(r) / 255,
            green: CGFloat(g) / 255,
            blue: CGFloat(b) / 255,
            alpha: CGFloat(a) / 255
        )
    }
}
#endif

// MARK: - Helper Modifiers
private struct CardShadowModifier: ViewModifier {
    let colorScheme: ColorScheme
    
    func body(content: Content) -> some View {
        content
            .shadow(
                color: Color(hex: "49637A").opacity(0.08),
                radius: 14,
                x: 0,
                y: 6
            )
    }
}

public extension View {
    func cardShadow(colorScheme: ColorScheme) -> some View {
        modifier(AppTheme.Shadows.card(colorScheme: colorScheme))
    }
}

// MARK: - Press Feedback Button Style (Taste-skill :active 规则移植 SwiftUI ButtonStyle)
public struct SoftButtonStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init() {}
    
    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .opacity(configuration.isPressed ? 0.86 : 1.0)
            .animation(reduceMotion ? nil : AppTheme.Motion.quick, value: configuration.isPressed)
    }
}

public struct QuantumCardModifier: ViewModifier {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    public func body(content: Content) -> some View {
        content
            .background(.ultraThinMaterial)
            .background(AppTheme.Colors.cardBackground.opacity(reduceTransparency ? 1 : 0.72))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(Color.white.opacity(0.76), lineWidth: 0.8)
            }
            .contentShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .shadow(
                color: Color(hex: "385A58").opacity(0.10),
                radius: 18,
                x: 0,
                y: 6
            )
    }
}

public extension View {
    func quantumCard() -> some View {
        modifier(QuantumCardModifier())
    }

    func minimumTouchTarget() -> some View {
        frame(minWidth: AppTheme.Metrics.minimumTouchTarget, minHeight: AppTheme.Metrics.minimumTouchTarget)
            .contentShape(Rectangle())
    }

    /// 保留调用兼容性，但全局关闭发光反馈。
    func pressBorderGlow(cornerRadius: CGFloat = AppTheme.Radius.md) -> some View {
        self
    }
}

/// Aurora Workbench 主操作按钮。仅用于每个区域唯一的主动作。
public struct QuantumPrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init() {}

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline.weight(.semibold))
            .foregroundStyle(AppTheme.Colors.onPrimary)
            .frame(maxWidth: .infinity, minHeight: AppTheme.Metrics.inputHeight)
            .padding(.horizontal, AppTheme.Spacing.xl)
            .background(AppTheme.Colors.actionGradient.opacity(isEnabled ? 1 : 0.46))
            .clipShape(Capsule())
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .opacity(configuration.isPressed ? 0.92 : 1)
            .animation(reduceMotion ? nil : AppTheme.Motion.quick, value: configuration.isPressed)
    }
}

/// 晨光自然底景：复用现有学习场景图，并用渐变遮罩控制信息可读性。
public struct QuantumMistBackground: View {

    public init() {}

    public var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color(hex: "EDF3F0"), Color(hex: "F7F5EF"), Color(hex: "F4E9E1")],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            GeometryReader { proxy in
                Image("knowledge_home_hero")
                    .resizable()
                    .scaledToFill()
                    .frame(width: proxy.size.width, height: min(420, proxy.size.height * 0.48))
                    .clipped()
                    .opacity(0.20)
                    .mask {
                        LinearGradient(colors: [.black, .clear], startPoint: .top, endPoint: .bottom)
                    }
                Circle()
                    .fill(AppTheme.Colors.mistLilac.opacity(0.54))
                    .frame(width: 250, height: 250)
                    .offset(x: proxy.size.width - 120, y: -80)
                Ellipse()
                    .fill(AppTheme.Colors.dawnPeach.opacity(0.28))
                    .frame(width: 300, height: 360)
                    .offset(x: -150, y: proxy.size.height * 0.58)
            }
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }
}
