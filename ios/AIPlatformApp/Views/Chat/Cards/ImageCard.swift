//
//  ImageCard.swift
//  AIPlatformApp
//
//  图片卡片：仅支持本地 assetName，UIImage(named:) 严格判空，
//  资源缺失时渲染灰底占位框（图标 + 文件名），杜绝运行时崩溃。
//

import SwiftUI
import ImageIO

public struct ImageCard: View {
    public let block: ImageBlock
    @State private var decodedImage: UIImage?

    public init(block: ImageBlock) {
        self.block = block
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            // 图片主体（优先运行时数据，其次本地资源；均判空降级）
            if let uiImage = decodedImage {
                Image(uiImage: uiImage)
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
            } else if block.imageData != nil {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 120)
            } else if let uiImage = UIImage(named: block.assetName) {
                Image(uiImage: uiImage)
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
            } else {
                placeholderView
            }

            // 图注
            if !block.caption.isEmpty {
                Text(block.caption)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.Colors.textSecondary)
            }
        }
        .padding(AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.Colors.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous)
                .stroke(AppTheme.Colors.border, lineWidth: 0.5)
        )
        .pressBorderGlow(cornerRadius: AppTheme.Radius.md)
        .task(id: block.id) {
            guard let data = block.imageData else {
                decodedImage = nil
                return
            }
            let thumbnailData = await Task.detached(priority: .utility) {
                Self.thumbnailData(from: data)
            }.value
            guard !Task.isCancelled else { return }
            decodedImage = thumbnailData.flatMap(UIImage.init(data:))
        }
    }

    /// 资源缺失优雅占位框（灰底 + 占位图标 + 文件名）
    private var placeholderView: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "photo")
                .font(.system(size: 32))
                    .foregroundColor(AppTheme.Icons.tertiary)
            Text(block.assetName)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(AppTheme.Colors.textSecondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 120)
        .background(AppTheme.Colors.tertiaryBackground)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
    }

    nonisolated private static func thumbnailData(from data: Data) -> Data? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceShouldCacheImmediately: false,
            kCGImageSourceThumbnailMaxPixelSize: 1_600,
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else {
            return nil
        }
        return UIImage(cgImage: image).jpegData(compressionQuality: 0.86)
    }
}

// MARK: - Xcode #Preview

#Preview("ImageCard - Missing Asset Fallback") {
    ImageCard(block: ImageBlock(assetName: "nonexistent_asset", caption: "缺失资源占位示例"))
        .padding()
        .background(AppTheme.Colors.groupedBackground)
}
