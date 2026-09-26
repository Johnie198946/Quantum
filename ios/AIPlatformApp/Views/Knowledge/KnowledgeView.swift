//
//  KnowledgeView.swift
//  AIPlatformApp
//
//  Notion-like interface backed by an Obsidian-compatible local Markdown vault.
//

import SwiftUI
import UIKit
import PhotosUI
import MapKit

private enum NoteScope: String, CaseIterable, Identifiable {
    case all = "全部"
    case pinned = "已置顶"
    case daily = "日记"

    var id: String { rawValue }
}

private enum NoteEditorMode: String, CaseIterable, Identifiable {
    case edit = "编辑"
    case preview = "阅读"

    var id: String { rawValue }
}

public struct KnowledgeView: View {
    @EnvironmentObject private var appState: AppState
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @StateObject private var store = KnowledgeNoteStore.shared

    @State private var path: [String] = []
    @State private var searchText = ""
    @State private var scope: NoteScope = .all
    @State private var selectedTags: Set<String> = []
    @State private var notePendingTrash: KnowledgeNote?
    @State private var showingTrashConfirmation = false
    @State private var showingArchive = false
    @State private var showingTrash = false
    @State private var showingNoteOrganizer = false
    @State private var showingBookshelf = false
    @State private var showingSessionOrganizer = false
    @State private var bookSubscriptions: [KnowledgeBookSubscriptionDTO] = []
    @State private var inspectedBook: KnowledgeBookDTO?
    @State private var busyBookID: String?
    @State private var contentRevealed = false

    public init() {}

    public var body: some View {
        let visibleNotes = store.search(searchText, tags: selectedTags).filter { note in
            switch scope {
            case .all: return true
            case .pinned: return note.isPinned
            case .daily: return note.isDailyNote
            }
        }
        let pinnedNotes = visibleNotes.filter(\.isPinned)
        let recentNotes = visibleNotes.filter { !$0.isPinned || scope != .all }

        return NavigationStack(path: $path) {
            List {
                libraryHeader
                if let error = store.lastError,
                   !ProcessInfo.processInfo.arguments.contains("-knowledgeHomePreview") {
                    syncErrorBanner(error)
                }
                if showingBookshelf {
                    subscribedBookshelf
                } else {
                    knowledgeSearchField
                    scopePicker
                    if !store.allTags.isEmpty { tagFilter }
                    if store.isLoading && store.notes.isEmpty {
                        loadingRow
                    } else if visibleNotes.isEmpty {
                        emptyState
                    } else {
                        if scope == .all && !pinnedNotes.isEmpty {
                            noteSection(title: "置顶", systemImage: "pin", notes: pinnedNotes)
                        }
                        if !recentNotes.isEmpty {
                            noteSection(title: scope == .all ? "最近修改" : scope.rawValue,
                                        systemImage: scope == .daily ? "calendar" : "clock",
                                        notes: recentNotes)
                        }
                    }
                }

            }
            .listStyle(.plain)
            .scrollContentBackground(.hidden)
            .background(AppTheme.Colors.background)
            .navigationTitle("")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar(.hidden, for: .navigationBar)
            .refreshable {
                await refreshNotes()
                await loadBookSubscriptions()
            }
            .navigationDestination(for: String.self) { noteID in
                KnowledgeNoteEditor(noteID: noteID)
            }
            .confirmationDialog(
                "将“\(notePendingTrash?.title ?? "这篇笔记")”移到废纸篓？",
                isPresented: $showingTrashConfirmation,
                titleVisibility: .visible
            ) {
                Button("移到废纸篓", role: .destructive) {
                    if let notePendingTrash {
                        store.moveToTrash(id: notePendingTrash.id)
                    }
                    notePendingTrash = nil
                }
                Button("取消", role: .cancel) {
                    notePendingTrash = nil
                }
            } message: {
                Text("可在更多菜单的“最近删除”中恢复本机笔记。云端副本不受影响。")
            }
            .task {
                if !contentRevealed {
                    withAnimation(reduceMotion ? nil : .spring(response: 0.46, dampingFraction: 0.88)) {
                        contentRevealed = true
                    }
                }
                #if DEBUG
                let arguments = ProcessInfo.processInfo.arguments
                let previewPage = arguments.firstIndex(of: "-prototypePreview")
                    .flatMap { arguments.indices.contains($0 + 1) ? arguments[$0 + 1] : nil }
                if arguments.contains("-knowledgeHomePreview") || previewPage == "v3/06-knowledge-home-p01" {
                    seedKnowledgeHomePreview()
                    return
                }
                #endif
                await refreshNotes()
                await loadBookSubscriptions()
            }
            #if DEBUG
            .fullScreenCover(isPresented: .constant(ProcessInfo.processInfo.arguments.contains("-noteIllustrationChatPreview"))) {
                NoteIllustrationChatPreview()
            }
            #endif
            .fullScreenCover(item: $inspectedBook) { book in
                KnowledgeBookReaderView(
                    book: book,
                    isSubscribed: bookSubscriptions.contains { $0.book.id == book.id },
                    isBusy: busyBookID == book.id,
                    onToggleSubscription: { Task { await removeBook(book) } },
                    onSaveExcerpt: { saveBookSummaryToNote(book) },
                    onDismiss: { inspectedBook = nil }
                )
            }
            .sheet(isPresented: $showingArchive) { KnowledgeArchiveView() }
            .sheet(isPresented: $showingTrash) { KnowledgeArchiveView(isTrash: true) }
            .sheet(isPresented: $showingNoteOrganizer) {
                NoteOrganizationPicker { notes in
                    appState.navigateToChatWithPrompt(
                        "请整理我选中的 \(notes.count) 篇笔记，保留来源，先生成 knowledge_action_v1 待确认卡。未经确认不得写入、归档或删除笔记。",
                        contextScope: localOnlyContext(notes: notes)
                    )
                }
            }
            .sheet(isPresented: $showingSessionOrganizer) {
                SessionOrganizationPicker { sessionIDs in
                    beginSessionOrganization(sessionIDs)
                }
            }
            .onChange(of: appState.pendingKnowledgeNavigation) { _, target in
                guard let target else { return }
                applyNavigation(target)
                appState.pendingKnowledgeNavigation = nil
            }
        }
    }

    private func syncErrorBanner(_ message: String) -> some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            Image(systemName: "arrow.trianglehead.2.clockwise.rotate.90")
                .foregroundStyle(AppTheme.Colors.securityYellow)
            VStack(alignment: .leading, spacing: 3) {
                Text("笔记操作未完成")
                    .font(.subheadline.weight(.semibold))
                Text(message)
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineLimit(2)
            }
            Spacer(minLength: 0)
            Button("重试") { Task { await refreshNotes() } }
                .font(.subheadline.weight(.semibold))
                .minimumTouchTarget()
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.Colors.securityYellow.opacity(0.09), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .listRowInsets(EdgeInsets(top: 4, leading: AppTheme.Metrics.contentGutter, bottom: 4, trailing: AppTheme.Metrics.contentGutter))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
    }

    #if DEBUG
    private func seedKnowledgeHomePreview() {
        store.activate(tenantKey: "knowledge-preview", userId: ProcessInfo.processInfo.environment["AI_LAB_E2E_NOTE_NAMESPACE"] ?? "preview")
        let fixtures: [(String, String, String, [String])] = [
            ("preview-reading", "阅读的意义", "阅读不是逃离，而是带着新的目光重新回到生活。", ["阅读"]),
            ("preview-design", "设计思考", "好的界面让信息自然出现，也让复杂能力保持克制。", ["灵感"]),
            ("preview-idea", "一些想法", "把零散灵感变成可以继续生长的知识。", ["学习"])
        ]
        for item in fixtures {
            _ = store.createNote(id: item.0, title: item.1, body: item.2, tags: item.3)
        }
        let books = SubscriptionCenterResponse.bookshelfPreview.bookshelves?
            .flatMap(\.books).prefix(2) ?? []
        bookSubscriptions = books.enumerated().map { index, book in
            KnowledgeBookSubscriptionDTO(
                book: book,
                edition: 1,
                contentVersion: "preview-v1",
                progress: index == 0 ? 0.68 : 0.12,
                subscribedAt: "2026-09-17T00:00:00Z",
                lastReadAt: "2026-09-17T00:00:00Z"
            )
        }
    }
    #endif

    private func applyNavigation(_ target: KnowledgeNavigationTarget) {
        showingBookshelf = false
        switch target.destination {
        case "knowledge_home":
            path.removeAll(); showingArchive = false
        case "note":
            if let id = target.noteId, store.note(id: id) != nil { path.append(id) }
        case "daily_note":
            openDailyNote()
        case "search":
            path.removeAll(); showingArchive = false; searchText = target.query ?? ""
        case "archive":
            path.removeAll(); showingArchive = true
        default:
            break
        }
    }

    private var subscribedBookshelf: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) { bookshelfHeading }
            } else {
                HStack { bookshelfHeading }
            }

            if bookSubscriptions.isEmpty {
                NavigationLink {
                    SubscriptionCenterView()
                } label: {
                    HStack(alignment: .bottom, spacing: AppTheme.Spacing.lg) {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                            Text("空书架也该被看见")
                                .font(.headline)
                                .foregroundStyle(AppTheme.Colors.textPrimary)
                            Text("订阅后，书会留在这里。")
                                .font(.subheadline)
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                        Spacer()
                        Image(systemName: "books.vertical")
                            .font(.system(size: 42, weight: .light))
                            .foregroundStyle(AppTheme.Colors.primary.opacity(0.42))
                            .rotationEffect(.degrees(7))
                    }
                    .padding(AppTheme.Spacing.xl)
                    .frame(maxWidth: .infinity, minHeight: 142, alignment: .leading)
                    .background(AppTheme.Colors.selectionTint.opacity(0.58))
                    .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
                }
                .buttonStyle(SoftButtonStyle())
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: AppTheme.Spacing.lg) {
                        ForEach(Array(bookSubscriptions.enumerated()), id: \.element.book.id) { _, item in
                            Button { inspectedBook = item.book } label: {
                                VStack(alignment: .leading, spacing: 8) {
                                    KnowledgeBookCover(book: item.book, width: dynamicTypeSize.isAccessibilitySize ? 220 : 126)
                                    Text(item.book.title)
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(AppTheme.Colors.textPrimary)
                                        .lineLimit(2)
                                        .frame(width: dynamicTypeSize.isAccessibilitySize ? 220 : 126, alignment: .leading)
                                    ProgressView(value: min(max(item.progress, 0), 1))
                                        .tint(AppTheme.Colors.primary)
                                        .frame(width: dynamicTypeSize.isAccessibilitySize ? 220 : 126)
                                    Text(item.progress > 0 ? "已读 \(Int(item.progress * 100))%" : "开始阅读")
                                        .font(.caption2)
                                        .foregroundStyle(AppTheme.Colors.textSecondary)
                                }
                                .padding(10)
                                .background(AppTheme.Colors.cardBackground.opacity(0.74), in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
                                .overlay {
                                    RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                                        .stroke(Color.white.opacity(0.82), lineWidth: 0.8)
                                }
                                .shadow(color: AppTheme.Colors.primary.opacity(0.08), radius: 14, y: 7)
                            }
                            .buttonStyle(SoftButtonStyle())
                            .accessibilityLabel("打开《\(item.book.title)》")
                        }
                    }
                    .padding(.horizontal, 6)
                    .padding(.vertical, 8)
                }
                .padding(.vertical, AppTheme.Spacing.xs)
            }
        }
        .padding(.vertical, AppTheme.Spacing.xl)
        .opacity(contentRevealed ? 1 : 0)
        .offset(y: contentRevealed ? 0 : 18)
        .listRowInsets(pageInsets(vertical: AppTheme.Spacing.sm))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
    }

    @ViewBuilder
    private var bookshelfHeading: some View {
        Text("我的书架")
            .font(.title2.bold())
            .foregroundStyle(AppTheme.Colors.textPrimary)
        if !dynamicTypeSize.isAccessibilitySize { Spacer() }
        NavigationLink("管理书架") { SubscriptionCenterView() }
            .font(.body)
            .frame(minHeight: 44)
            .accessibilityLabel("打开知识书架")
    }

    private func loadBookSubscriptions() async {
        if let items = try? await APIClient.shared.fetchBookSubscriptions() {
            bookSubscriptions = items
        }
    }

    private func removeBook(_ book: KnowledgeBookDTO) async {
        guard busyBookID == nil else { return }
        busyBookID = book.id
        defer { busyBookID = nil }
        do {
            try await APIClient.shared.unsubscribeBook(id: book.id)
            bookSubscriptions.removeAll { $0.book.id == book.id }
            inspectedBook = nil
        } catch {
            // The book remains visible, so the user can retry without losing context.
        }
    }

    private func saveBookSummaryToNote(_ book: KnowledgeBookDTO) {
        let body = """
        > [!abstract] 书籍摘录
        > 《\(book.title)》 · \(book.author)
        > Quantum 编研版 · \(book.knowledgeLevel) · \(book.sourceCount) 个来源

        \(book.summary)

        ---
        来源书籍 ID：`\(book.id)`
        """
        guard let note = store.createNote(
            title: "\(book.title)｜概述摘录", body: body,
            tags: ["书籍摘录", "quantum-books"]
        ) else { return }
        syncInBackground(note)
        inspectedBook = nil
        path.append(note.id)
    }

    private var libraryHeader: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("阅读与记录")
                        .font(.system(.largeTitle, design: .rounded).weight(.bold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    if !dynamicTypeSize.isAccessibilitySize {
                        Text(showingBookshelf ? "继续读，慢慢积累。" : "小灵感，慢慢长成大想法。")
                            .font(.subheadline)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                    }
                }
                Spacer(minLength: 8)
                knowledgeMenu
                    .background(AppTheme.Colors.cardBackground, in: Circle())
            }
            Picker("阅读内容", selection: $showingBookshelf) {
                Text("笔记").tag(false)
                Text("书架").tag(true)
            }
            .pickerStyle(.segmented)
            .accessibilityIdentifier("knowledge-section")
            if !showingBookshelf {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) { noteActions }
                } else {
                    HStack { noteActions }
                }
            }
        }
        .padding(.vertical, AppTheme.Spacing.md)
        .listRowInsets(pageInsets(vertical: 0))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
    }

    @ViewBuilder
    private var noteActions: some View {
        Button(action: createNote) {
            Label("新建笔记", systemImage: "square.and.pencil")
                .font(.body.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.onPrimary)
                .frame(maxWidth: .infinity, minHeight: 56)
                .background(AppTheme.Colors.primary, in: RoundedRectangle(cornerRadius: 20))
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityIdentifier("note-create")
        Button(action: openDailyNote) {
            Label("今日日记", systemImage: "sun.max")
                .font(.body.weight(.medium))
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .frame(maxWidth: .infinity, minHeight: 56)
                .background(AppTheme.Colors.mistMint, in: RoundedRectangle(cornerRadius: 20))
        }
        .buttonStyle(SoftButtonStyle())
    }

    private var knowledgeMenu: some View {
        Menu {
            Button { showingNoteOrganizer = true } label: {
                Label("整理选中笔记", systemImage: "sparkles")
            }
            .disabled(store.notes.isEmpty)
            Button { showingSessionOrganizer = true } label: {
                Label("从对话生成笔记", systemImage: "bubble.left.and.text.bubble.right")
            }
            Button {
                if let note = store.createNote(title: "我的旅行", body: "{\"stops\":[],\"journal\":\"\"}", tags: ["旅行"]) {
                    path.append(note.id)
                }
            } label: { Label("新建旅行笔记", systemImage: "suitcase.rolling") }
            Divider()
            Button { showingArchive = true } label: {
                Label("归档（\(store.archivedNotes.count)）", systemImage: "archivebox")
            }
            Button { showingTrash = true } label: {
                Label("最近删除（本机）", systemImage: "trash")
            }
        } label: {
            Image(systemName: "ellipsis")
                .font(.title3)
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .frame(width: 44, height: 44)
        }
        .accessibilityLabel("更多笔记操作")
        .accessibilityIdentifier("knowledge-more")
    }

    private var knowledgeSearchField: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(AppTheme.Colors.textSecondary)
            TextField("搜索笔记", text: $searchText)
                .accessibilityIdentifier("note-search")
                .textInputAutocapitalization(.never)
                .submitLabel(.search)
            if !searchText.isEmpty {
                Button { searchText = "" } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("清除搜索")
            }
        }
        .padding(.leading, AppTheme.Spacing.lg)
        .padding(.trailing, AppTheme.Spacing.sm)
        .frame(minHeight: 52)
        .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
        .listRowInsets(pageInsets(vertical: AppTheme.Spacing.xs))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
    }

    private var tagFilter: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppTheme.Spacing.sm) {
                tagButton(title: "全部标签", tag: nil)
                ForEach(store.allTags, id: \.self) { tag in
                    tagButton(title: "#\(tag)", tag: tag)
                }
            }
            .padding(.vertical, AppTheme.Spacing.xs)
        }
        .listRowInsets(pageInsets(vertical: AppTheme.Spacing.xs))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
        .accessibilityLabel("标签筛选")
    }

    private func tagButton(title: String, tag: String?) -> some View {
        let selected = tag == nil ? selectedTags.isEmpty : selectedTags.contains(tag!)
        return Button {
            withAnimation(reduceMotion ? nil : AppTheme.Motion.quick) {
                if let tag {
                    if selectedTags.contains(tag) {
                        selectedTags.remove(tag)
                    } else {
                        selectedTags.insert(tag)
                    }
                } else {
                    selectedTags.removeAll()
                }
            }
        } label: {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(selected ? AppTheme.Colors.primary : AppTheme.Colors.textSecondary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                .background(selected ? AppTheme.Colors.mistMint : AppTheme.Colors.cardBackground)
                .overlay(Capsule().stroke(selected ? AppTheme.Colors.primary.opacity(0.35) : .clear, lineWidth: 1))
                .clipShape(Capsule())
        }
        .buttonStyle(SoftButtonStyle())
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private var scopePicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppTheme.Spacing.lg) {
                ForEach(NoteScope.allCases) { item in
                    Button { scope = item } label: {
                        VStack(spacing: 6) {
                            Text(item.rawValue)
                                .font(.subheadline.weight(scope == item ? .bold : .medium))
                                .foregroundStyle(scope == item ? AppTheme.Colors.textPrimary : AppTheme.Colors.textSecondary)
                            Capsule()
                                .fill(scope == item ? AppTheme.Colors.primary : .clear)
                                .frame(width: 20, height: 3)
                        }
                        .frame(minWidth: 44, minHeight: 44)
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(scope == item ? .isSelected : [])
                }
            }
        }
        .accessibilityLabel("笔记范围")
        .listRowInsets(pageInsets(vertical: 0))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
    }

    private func noteSection(title: String, systemImage: String, notes: [KnowledgeNote]) -> some View {
        Section {
            ForEach(notes) { note in
                NavigationLink(value: note.id) {
                    KnowledgeNoteRow(note: note, preview: store.index.previewsByNoteID[note.id] ?? note.preview,
                                     backlinkCount: store.index.backlinkCountsByNoteID[note.id] ?? 0)
                }
                .accessibilityIdentifier("note-row-\(note.id)")
                .buttonStyle(.plain)
                .swipeActions(edge: .leading, allowsFullSwipe: true) {
                    Button {
                        store.togglePin(id: note.id)
                    } label: {
                        Label(note.isPinned ? "取消置顶" : "置顶", systemImage: note.isPinned ? "pin.slash" : "pin")
                    }
                    .tint(AppTheme.Colors.primary)
                }
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    Button(role: .destructive) {
                        notePendingTrash = note
                        showingTrashConfirmation = true
                    } label: {
                        Label("移到废纸篓", systemImage: "trash")
                    }
                }
                .listRowInsets(EdgeInsets(
                    top: AppTheme.Spacing.sm,
                    leading: AppTheme.Metrics.contentGutter + 16,
                    bottom: AppTheme.Spacing.sm,
                    trailing: AppTheme.Metrics.contentGutter + 12
                ))
                .listRowSeparator(.hidden)
                .listRowBackground(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .fill(AppTheme.Colors.cardBackground)
                        .padding(.horizontal, AppTheme.Metrics.contentGutter)
                        .padding(.vertical, 4)
                )
            }
        } header: {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .textCase(nil)
        }
    }

    private var loadingRow: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            ProgressView()
            Text("正在读取本地笔记…")
                .font(.subheadline)
                .foregroundStyle(AppTheme.Colors.textSecondary)
        }
        .frame(minHeight: 120)
        .listRowSeparator(.hidden)
        .listRowBackground(AppTheme.Colors.cardBackground)
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label(store.notes.isEmpty ? "记下第一个想法" : "没有匹配的笔记", systemImage: "note.text")
        } description: {
            Text(store.notes.isEmpty ? "一句话也值得留下。" : "换个关键词，或清除筛选再试。")
        } actions: {
            if store.notes.isEmpty {
                Button("写第一篇笔记", action: createNote).buttonStyle(.borderedProminent)
            } else {
                Button("清除搜索与筛选") { searchText = ""; selectedTags.removeAll(); scope = .all }
                    .frame(minHeight: 44)
            }
        }
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
    }

    private func pageInsets(vertical: CGFloat) -> EdgeInsets {
        EdgeInsets(
            top: vertical,
            leading: AppTheme.Metrics.contentGutter,
            bottom: vertical,
            trailing: AppTheme.Metrics.contentGutter
        )
    }

    private func createNote() {
        guard let note = store.createNote() else { return }
        syncInBackground(note)
        path.append(note.id)
    }

    private func openDailyNote() {
        guard let note = store.dailyNote() else { return }
        syncInBackground(note)
        path.append(note.id)
    }

    private func localOnlyContext(notes selectedNotes: [KnowledgeNote] = []) -> ChatContextScopeDTO {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let notes = selectedNotes.map { note in
            ChatLocalNoteDTO(
                id: note.id,
                title: note.title,
                markdown: store.markdown(for: note),
                updatedAt: formatter.string(from: note.updatedAt)
            )
        }
        return ChatContextScopeDTO(mode: .localOnly, localNotes: Array(notes))
    }

    private func beginSessionOrganization(_ sessionIDs: [String]) {
        guard !sessionIDs.isEmpty else { return }
        let manager = SessionManager.shared
        let destination = manager.createSession(agentId: "knowledge", agentName: "知识整理")
        let context = manager.organizationContext(
            sourceSessionIDs: sessionIDs,
            destinationSessionId: destination
        )
        manager.switchTo(destination)
        let prompt = """
        请整理我刚刚明确选择的 \(sessionIDs.count) 个来源会话。先调用 session_context_read，读取全部 source_sessions；不要只整理当前或最新会话。排除明显无关内容后，将所有相关主题归纳为一篇结构清晰的综合笔记（仅当我明确要求拆分时才创建多篇）。笔记必须在 Markdown 中保留 source_session_ids 与带 session_id 前缀的 source_message_ids，冲突信息单独列出。先生成 knowledge_action_v1 待确认卡，不得直接写入，也不得删除、归档来源会话。
        """
        appState.navigateToChatWithPrompt(
            prompt,
            contextScope: localOnlyContext(),
            sessionContext: context
        )
    }

    private func syncInBackground(_ note: KnowledgeNote) {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("-knowledgeHomePreview") { return }
        #endif
        let markdown = store.markdown(for: note)
        let credentialGeneration = APIClient.shared.currentCredentialGeneration()
        Task {
            _ = try? await APIClient.shared.syncKnowledgeNote(
                id: note.id, markdown: markdown, updatedAt: note.updatedAt,
                credentialGeneration: credentialGeneration
            )
        }
    }

    private func syncLocalNotes() async {
        let credentialGeneration = APIClient.shared.currentCredentialGeneration()
        let account = store.accountFingerprint
        for note in store.notes {
            guard account == store.accountFingerprint,
                  credentialGeneration == APIClient.shared.currentCredentialGeneration() else { return }
            _ = try? await APIClient.shared.syncKnowledgeNote(
                id: note.id,
                markdown: store.markdown(for: note),
                updatedAt: note.updatedAt,
                credentialGeneration: credentialGeneration
            )
        }
        for note in store.archivedNotes {
            guard account == store.accountFingerprint,
                  credentialGeneration == APIClient.shared.currentCredentialGeneration() else { return }
            guard let mergedIntoNoteId = note.mergedIntoNoteId else { continue }
            do {
                _ = try await APIClient.shared.syncKnowledgeNote(
                    id: note.id,
                    markdown: store.markdown(for: note),
                    updatedAt: note.updatedAt,
                    credentialGeneration: credentialGeneration
                )
                guard account == store.accountFingerprint,
                      credentialGeneration == APIClient.shared.currentCredentialGeneration() else { return }
                try await APIClient.shared.archiveKnowledgeNote(
                    id: note.id, mergedIntoNoteId: mergedIntoNoteId
                )
            } catch is CancellationError {
                return
            } catch {}
        }
    }

    /// Pull first so server notes created by a Hermes-backed chat run appear
    /// immediately. iOS only owns local Markdown presentation and transport.
    private func refreshNotes() async {
        await store.restoreFromCloud()
        guard store.lastError == nil else { return }
        await syncLocalNotes()
    }
}

private struct KnowledgeBookCover: View {
    let book: KnowledgeBookDTO
    let width: CGFloat

    var body: some View {
        IllustratedBookCover(
            title: book.title,
            author: book.author,
            theme: book.coverTheme,
            variant: book.coverVariant,
            width: width
        )
    }
}

private struct NoteOrganizationPicker: View {
    @ObservedObject private var store = KnowledgeNoteStore.shared
    @Environment(\.dismiss) private var dismiss
    @State private var selected: Set<String> = []
    @State private var query = ""
    let onStart: ([KnowledgeNote]) -> Void

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("选择要整理的笔记，最多 8 篇。AI 会先给出方案，由你确认后保存。")
                        .font(.subheadline)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                Section("已选 \(selected.count)/8 篇") {
                    ForEach(store.search(query)) { note in
                        Button {
                            if selected.contains(note.id) { selected.remove(note.id) }
                            else if selected.count < 8 { selected.insert(note.id) }
                        } label: {
                            HStack {
                                Image(systemName: selected.contains(note.id) ? "checkmark.circle.fill" : "circle")
                                Text(note.title).foregroundStyle(AppTheme.Colors.textPrimary)
                                Spacer()
                            }
                            .frame(minHeight: 44)
                            .contentShape(Rectangle())
                        }
                        .disabled(selected.count == 8 && !selected.contains(note.id))
                        .accessibilityAddTraits(selected.contains(note.id) ? .isSelected : [])
                    }
                }
            }
            .navigationTitle("整理选中笔记")
            .navigationBarTitleDisplayMode(.inline)
            .searchable(text: $query, prompt: "搜索笔记")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("整理 \(selected.count) 篇") {
                        let notes = store.notes.filter { selected.contains($0.id) }
                        dismiss()
                        onStart(notes)
                    }
                    .disabled(selected.isEmpty)
                }
            }
        }
    }
}

private struct SessionOrganizationPicker: View {
    @ObservedObject private var manager = SessionManager.shared
    @Environment(\.dismiss) private var dismiss
    @State private var selected: Set<String> = []
    @State private var searchText = ""
    let onStart: ([String]) -> Void

    private var available: [String] {
        manager.sortedSessionIDs(status: .active, query: searchText)
            .filter { manager.messageCount(for: $0) > 0 }
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("AI 只读取你明确选中的会话，先按主题分组，再生成待确认的知识操作。不会自动归档或删除。")
                        .font(.subheadline)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                Section("快捷范围") {
                    Button("当前会话") {
                        selected = Set([manager.activeSessionID()].filter { manager.messageCount(for: $0) > 0 })
                    }
                    Button("当前会话及相关分支") {
                        let active = manager.activeSessionID()
                        let parent = manager.topicSessions[active]?.parentSessionId ?? active
                        let related = manager.sortedSessionIDs().filter { id in
                            id == active || id == parent || manager.topicSessions[id]?.parentSessionId == parent
                        }
                        selected = Set(related.prefix(30))
                    }
                    Button("最近 7 天") {
                        let cutoff = Date().addingTimeInterval(-7 * 86_400)
                        selected = Set(manager.sortedSessionIDs().filter {
                            (manager.sessionUpdatedAt[$0] ?? .distantPast) >= cutoff && manager.messageCount(for: $0) > 0
                        }.prefix(30))
                    }
                    Button("全部未整理会话") {
                        selected = Set(manager.sortedSessionIDs().filter {
                            manager.sessionOrganizedAt[$0] == nil && manager.messageCount(for: $0) > 0
                        }.prefix(30))
                    }
                }
                Section("手动选择 · 已选 \(selected.count)/30 个") {
                    ForEach(available, id: \.self) { id in
                        Button {
                            if selected.contains(id) {
                                selected.remove(id)
                            } else if selected.count < 30 {
                                selected.insert(id)
                            }
                        } label: {
                            HStack(spacing: AppTheme.Spacing.sm) {
                                Image(systemName: selected.contains(id) ? "checkmark.square.fill" : "square")
                                    .foregroundStyle(selected.contains(id) ? AppTheme.Icons.interactive : AppTheme.Colors.textTertiary)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(manager.title(for: id)).lineLimit(1)
                                    Text("\(manager.messageCount(for: id)) 条消息\(manager.sessionOrganizedAt[id] == nil ? "" : " · 已整理过")")
                                        .font(.caption)
                                        .foregroundStyle(AppTheme.Colors.textSecondary)
                                }
                            }
                        }
                        .buttonStyle(SoftButtonStyle())
                    }
                }
            }
            .navigationTitle("选择整理范围")
            .navigationBarTitleDisplayMode(.inline)
            .searchable(text: $searchText, prompt: "搜索会话标题或内容")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("开始整理") {
                        let ids = manager.sortedSessionIDs().filter(selected.contains)
                        dismiss()
                        onStart(ids)
                    }
                    .disabled(selected.isEmpty)
                }
            }
            .onAppear {
                guard selected.isEmpty else { return }
                let active = manager.activeSessionID()
                if manager.messageCount(for: active) > 0 { selected.insert(active) }
            }
        }
    }
}

private struct KnowledgeArchiveView: View {
    var isTrash = false
    @State private var recoveryError: String?
    private var recoveryNotes: [KnowledgeNote] { isTrash ? store.trashedNotes : store.archivedNotes }
    @Environment(\.dismiss) private var dismiss
    @StateObject private var store = KnowledgeNoteStore.shared

    var body: some View {
        NavigationStack {
            List {
                if recoveryNotes.isEmpty {
                    ContentUnavailableView(
                        isTrash ? "最近没有删除笔记" : "没有归档笔记",
                        systemImage: isTrash ? "trash" : "archivebox",
                        description: Text(isTrash ? "本机删除的笔记可在这里恢复。" : "合并整理后的旧笔记会保留在这里。")
                    )
                } else {
                    Section {
                        ForEach(recoveryNotes) { note in
                            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                                    Text(note.title)
                                        .font(.body.weight(.semibold))
                                    if !note.preview.isEmpty {
                                        Text(note.preview)
                                            .font(.subheadline)
                                            .foregroundStyle(AppTheme.Colors.textSecondary)
                                            .lineLimit(2)
                                    }
                                }
                                Spacer(minLength: AppTheme.Spacing.sm)
                                Button("恢复") { restore(note) }
                                    .buttonStyle(.bordered)
                                    .pressBorderGlow(cornerRadius: AppTheme.Radius.sm)
                                    .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                            }
                            .swipeActions(edge: .leading, allowsFullSwipe: false) {
                                Button {
                                    restore(note)
                                } label: {
                                    Label("恢复", systemImage: "arrow.uturn.backward")
                                }
                                .tint(AppTheme.Colors.primary)
                            }
                            .accessibilityAction(named: "恢复笔记") { restore(note) }
                        }
                    } footer: {
                        Text(isTrash ? "恢复后回到笔记列表；这里仅包含本机保留的副本。" : "归档不会删除内容；向右轻扫可恢复到当前笔记列表。")
                    }
                }
            }
            .navigationTitle(isTrash ? "最近删除（本机）" : "归档")
            .alert("恢复未完成", isPresented: Binding(get: { recoveryError != nil }, set: { if !$0 { recoveryError = nil } })) {
                Button("知道了") { recoveryError = nil }
            } message: { Text(recoveryError ?? "") }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
        }
    }

    private func restore(_ note: KnowledgeNote) {
        let restored = isTrash ? store.restoreTrashedNote(id: note.id) : store.restoreArchivedNote(id: note.id)
        guard restored != nil else { recoveryError = store.lastError ?? "请稍后重试。"; return }
        guard !isTrash else { return }
        Task {
            do { try await APIClient.shared.restoreKnowledgeNote(id: note.id) }
            catch { recoveryError = "已恢复到本机，云端恢复暂未完成。" }
        }
    }
}

private struct KnowledgeNoteRow: View {
    let note: KnowledgeNote
    let preview: String
    let backlinkCount: Int

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            Image(systemName: note.isDailyNote ? "calendar" : "doc.text")
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(note.isDailyNote ? AppTheme.Icons.intelligence : AppTheme.Icons.interactive)
                .frame(width: 40, height: 40)
                .background(note.isDailyNote ? AppTheme.Colors.mistLilac : AppTheme.Colors.mistMint)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.xs) {
                    Text(note.title)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    if note.isPinned {
                        Image(systemName: "pin.fill")
                            .font(.caption2)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .accessibilityLabel("已置顶")
                    }
                }

                if !preview.isEmpty {
                    Text(preview)
                        .font(.subheadline)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(2)
                }

                HStack(spacing: AppTheme.Spacing.sm) {
                    Text(note.updatedAt, style: .relative)
                    if !note.tags.isEmpty {
                        Text("·")
                        Text(note.tags.prefix(2).map { "#\($0)" }.joined(separator: "  "))
                    }
                    if backlinkCount > 0 {
                        Text("·")
                        Label("\(backlinkCount)", systemImage: "link")
                    }
                }
                .font(.caption)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .lineLimit(1)
            }
        }
        .padding(.vertical, AppTheme.Spacing.sm)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(note.title)，\(note.tags.map { "标签 \($0)" }.joined(separator: "，"))")
        .accessibilityHint("打开笔记")
    }
}

private struct KnowledgeNoteEditor: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @EnvironmentObject private var api: APIClient
    @ObservedObject private var store = KnowledgeNoteStore.shared
    @StateObject private var speechService = SpeechRecognizerService()

    let noteID: String

    @State private var title = ""
    @State private var noteContent = ""
    @State private var selectedRange = NSRange(location: 0, length: 0)
    @State private var tagsText = ""
    @State private var isPinned = false
    @State private var mode: NoteEditorMode = .edit
    @State private var isLoaded = false
    @State private var saveStatus = "已保存到本地"
    @State private var saveTask: Task<Void, Never>?
    @State private var showingTrashConfirmation = false
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var photoImportError: String?
    @State private var travelPhotoDraft: TravelPhotoDraft?
    @State private var showingCamera = false
    @State private var selectedExcerpt = ""
    @State private var annotationDraft = ""
    @State private var isWritingAnnotation = false
    @State private var showingQuestion = false
    @State private var inspectedNoteAnnotation: NoteInlineAnnotation?
    @State private var showingRelations = false
    @State private var isSaving = false
    @State private var draftRevision = 0
    @State private var loadedAccount = ""
    @State private var lastVoiceTranscript = ""
    @State private var showingIllustration = false
    @State private var illustrationAnchor = ""
    @State private var illustrationLocationError: String?
    @State private var bodyEditorFocused = false
    @FocusState private var titleFocused: Bool
    @FocusState private var tagsFocused: Bool

    private var note: KnowledgeNote? { store.note(id: noteID) }

    var body: some View {
        editorContent
        .navigationTitle(mode == .edit ? "" : (title.isEmpty ? "笔记" : title))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .navigationBarBackButtonHidden(true)
        .toolbar { editorToolbar }
        .task(id: noteID) { loadNote() }
        .onChange(of: title) { _, _ in scheduleSave() }
        .onChange(of: noteContent) { _, value in store.activeNoteDrafts[noteID] = value; scheduleSave() }
        .onChange(of: store.note(id: noteID)?.body) { old, new in
            if let new, noteContent == old { noteContent = new }
        }
        .sheet(isPresented: $showingIllustration) {
            NoteIllustrationSheet(noteID: noteID, anchor: illustrationAnchor)
        }
        .alert("选择配图位置", isPresented: Binding(get: { illustrationLocationError != nil }, set: { if !$0 { illustrationLocationError = nil } })) {
            Button("知道了") { illustrationLocationError = nil }
        } message: { Text(illustrationLocationError ?? "") }
        .onChange(of: tagsText) { _, _ in scheduleSave() }
        .onChange(of: selectedRange) { _, _ in updateSelectedExcerpt() }
        .onChange(of: selectedPhoto) { _, item in
            guard let item else { return }
            Task { await importPhoto(item) }
        }
        .onChange(of: speechService.state) { oldState, newState in
            guard oldState == .processing, newState == .idle else { return }
            insertVoiceTranscriptIfNeeded()
        }
        .onDisappear {
            saveTask?.cancel()
            speechService.cancel()
            saveNow()
            store.activeNoteDrafts[noteID] = nil
        }
        .confirmationDialog(
            "将这篇笔记移到废纸篓？",
            isPresented: $showingTrashConfirmation,
            titleVisibility: .visible
        ) {
            Button("移到废纸篓", role: .destructive) {
                saveTask?.cancel()
                if store.moveToTrash(id: noteID) { dismiss() }
                else { saveStatus = "保存失败：" + (store.lastError ?? "无法删除笔记") }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("可在“最近删除”中恢复本机笔记。云端副本不受影响。")
        }
        .safeAreaInset(edge: .bottom) { bottomDock }
        .sheet(isPresented: $showingQuestion) {
            ReaderQuestionSheet(
                excerpt: selectedExcerpt,
                sourceTitle: title,
                sourceSubtitle: "当前笔记",
                onSaveAnswer: { question, answer, _ in
                    saveQuestionAnswerAnnotation(question: question, answer: answer)
                    return store.lastError == nil
                }
            ) { question, sessionID in
                try await askAboutSelection(question, sessionID: sessionID)
            }
        }
        .sheet(item: $inspectedNoteAnnotation) {
            NoteAnnotationDetailSheet(annotation: $0, noteTitle: title)
        }
        .sheet(isPresented: $showingRelations) {
            NavigationStack {
                ScrollView {
                    if let note { relationSection(note: note).padding(AppTheme.Metrics.contentGutter) }
                }
                .background(AppTheme.Colors.background)
                .scrollDismissesKeyboard(.interactively)
                .background {
                    Color.clear
                        .contentShape(Rectangle())
                        .onTapGesture { dismissEditorKeyboard() }
                }
                .navigationTitle("关联内容")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { showingRelations = false } } }
            }
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
        }
    }

    @ViewBuilder
    private var editorContent: some View {
        Group {
            if let note {
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                        editorHeader(note: note)
                        if let job = store.illustrationJobs[noteID], !job.message.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                Label(job.message, systemImage: "sparkles").font(.subheadline)
                                HStack {
                                    Button("查看配图") { illustrationAnchor = job.request.anchor; showingIllustration = true }
                                    if job.applied { Button("撤销配图") { store.undoIllustrations(id: noteID) } }
                                }
                                .font(.subheadline).frame(minHeight: 44)
                            }
                            .foregroundStyle(AppTheme.Colors.primary)
                            .padding(14)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(AppTheme.Colors.mistLilac.opacity(0.6), in: RoundedRectangle(cornerRadius: 18))
                        }

                        if mode == .edit {
                            editorBody
                        } else {
                            if isTravelNote {
                                TravelNoteReadingView(
                                    title: title,
                                    content: noteContent,
                                    baseURL: store.vaultDirectory,
                                    onSelection: selectExcerpt,
                                    onIllustrate: { anchor in openIllustration(anchor: anchor) }
                                )
                            } else {
                                NoteReadingView(
                                    content: noteContent,
                                    baseURL: store.vaultDirectory,
                                    onSelection: selectExcerpt,
                                    onAskSelection: { excerpt in
                                        selectExcerpt(excerpt)
                                        showingQuestion = true
                                    },
                                    onHighlightSelection: saveSelectionHighlight,
                                    onAnnotateSelection: { excerpt in
                                        selectExcerpt(excerpt)
                                        isWritingAnnotation = true
                                    },
                                    onAnnotationTap: { inspectedNoteAnnotation = $0 }
                                )
                            }
                        }

                        if let photoImportError {
                            Label(photoImportError, systemImage: "exclamationmark.triangle.fill")
                                .font(AppTheme.Typography.supporting)
                                .foregroundStyle(AppTheme.Colors.statusError)
                        }

                    }
                    .frame(maxWidth: AppTheme.Metrics.readableContentWidth, alignment: .leading)
                    .padding(.horizontal, AppTheme.Metrics.contentGutter)
                    .padding(.top, AppTheme.Spacing.lg)
                    .padding(.bottom, 120)
                    .frame(maxWidth: .infinity, alignment: .center)
                }
                .background(AppTheme.Colors.background)
                .sheet(item: $travelPhotoDraft) { draft in
                    TravelMomentComposer(
                        imagePath: draft.path,
                        baseURL: store.vaultDirectory,
                        onInsert: { markdown in
                            insertMarkdown(markdown, selecting: "__no_selection__")
                            travelPhotoDraft = nil
                        }
                    )
                }
                .fullScreenCover(isPresented: $showingCamera) {
                    TravelCameraPicker { image in
                        showingCamera = false
                        Task { await importCapturedPhoto(image) }
                    } onCancel: {
                        showingCamera = false
                    }
                    .ignoresSafeArea()
                }
            } else {
                ContentUnavailableView(
                    "笔记不存在",
                    systemImage: "doc.questionmark",
                    description: Text("文件可能已被移动或删除。")
                )
            }
        }
    }

    @ToolbarContentBuilder
    private var editorToolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            Button { if note == nil || saveNow() { dismiss() } } label: {
                Label("返回", systemImage: "chevron.left")
            }
            .accessibilityIdentifier("note-back")
        }
        ToolbarItemGroup(placement: .topBarTrailing) {
            if mode == .edit {
                Button { UIApplication.shared.sendAction(#selector(UndoManager.undo), to: nil, from: nil, for: nil) } label: {
                    Image(systemName: "arrow.uturn.backward")
                }
                .accessibilityLabel("撤销")
                .frame(minWidth: 44, minHeight: 44)
                Button { UIApplication.shared.sendAction(#selector(UndoManager.redo), to: nil, from: nil, for: nil) } label: {
                    Image(systemName: "arrow.uturn.forward")
                }
                .accessibilityLabel("重做")
                .frame(minWidth: 44, minHeight: 44)
                Button("完成") {
                    if saveNow() {
                        dismissEditorKeyboard()
                        mode = .preview
                        store.startIllustrations(id: noteID)
                    }
                }
                .accessibilityIdentifier("note-done")
                .buttonStyle(.borderedProminent)
                .tint(AppTheme.Colors.textPrimary)
            } else {
                if let note {
                    ShareLink(item: note.fileURL) {
                        Image(systemName: "square.and.arrow.up")
                            .frame(width: AppTheme.Metrics.minimumTouchTarget, height: AppTheme.Metrics.minimumTouchTarget)
                    }
                    .accessibilityLabel("分享 Markdown 文件")
                }
                Menu {
                    Toggle("保存时自动配图", isOn: Binding(get: { store.automaticIllustrationsEnabled(noteID) }, set: { store.setAutomaticIllustrations($0, id: noteID) }))
                    Button("自动为这篇配图", systemImage: "sparkles") { store.startIllustrations(id: noteID, retry: true) }
                    if !isTravelNote {
                        Button("使用旅行版式", systemImage: "suitcase.rolling") {
                            guard saveNow() else { return }
                            if NoteIllustrationPlacement.travelObject(noteContent) == nil {
                                noteContent = NoteIllustrationPlacement.json(["stops": [], "journal": noteContent]) ?? noteContent
                            }
                            tagsText = (parsedTags + ["旅行"]).joined(separator: ", ")
                            _ = saveNow()
                        }
                    }
                    Button("关联内容", systemImage: "link") { showingRelations = true }
                    Button {
                        isPinned.toggle()
                        scheduleSave()
                    } label: {
                        Label(isPinned ? "取消置顶" : "置顶", systemImage: isPinned ? "pin.slash" : "pin")
                    }
                    Button(role: .destructive) {
                        showingTrashConfirmation = true
                    } label: {
                        Label("移到废纸篓", systemImage: "trash")
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .frame(width: AppTheme.Metrics.minimumTouchTarget, height: AppTheme.Metrics.minimumTouchTarget)
                }
                .accessibilityLabel("更多笔记操作")
            }
        }
    }

    private func editorHeader(note: KnowledgeNote) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            if !isTravelNote || mode == .edit {
            TextField("无标题", text: $title, axis: .vertical)
                .font(.system(.largeTitle, design: isTravelNote ? .serif : .rounded).weight(isTravelNote ? .semibold : .bold))
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .textFieldStyle(.plain)
                .focused($titleFocused)
                .disabled(mode == .preview)
                .accessibilityLabel("笔记标题")
                .accessibilityIdentifier("note-title")
            }
            HStack(alignment: .top) {
                Text(isSaving ? "保存中…" : saveStatus)
                    .font(.caption)
                    .foregroundStyle(saveStatus.hasPrefix("保存失败") ? AppTheme.Colors.statusError : AppTheme.Colors.textSecondary)
                    .accessibilityIdentifier("note-save-status")
                Spacer(minLength: 8)
                if saveStatus.hasPrefix("保存失败") || saveStatus.contains("待确认") {
                    Button("重试") { saveNow(retrySync: true) }.frame(minHeight: 44)
                }
            }
            if mode == .edit {
                DisclosureGroup("标签\(parsedTags.isEmpty ? "" : " · " + parsedTags.joined(separator: "、"))") {
                    TextField("用逗号分隔，例如：学习，灵感", text: $tagsText)
                        .font(.body)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($tagsFocused)
                        .frame(minHeight: 44)
                        .accessibilityLabel("笔记标签")
                        .accessibilityIdentifier("note-tags")
                }
                .font(.subheadline)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm)
                .background(AppTheme.Colors.mistMint.opacity(0.55), in: RoundedRectangle(cornerRadius: 16))
            } else {
                Text(note.updatedAt.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                if !parsedTags.isEmpty {
                    Text(parsedTags.map { "#" + $0 }.joined(separator: "  "))
                        .font(.subheadline)
                        .foregroundStyle(AppTheme.Colors.primary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(AppTheme.Colors.mistMint, in: RoundedRectangle(cornerRadius: 12))
                }
            }
            Rectangle()
                .fill(AppTheme.Colors.border)
                .frame(height: 1)
        }
    }

    private var parsedTags: [String] { KnowledgeNoteStore.parseTags(tagsText) }

    private var editableText: Binding<String> {
        Binding(get: {
            if isTravelNote, let object = NoteIllustrationPlacement.travelObject(noteContent) { return object["journal"] as? String ?? "" }
            return noteContent
        }, set: { value in
            if isTravelNote, var object = NoteIllustrationPlacement.travelObject(noteContent) {
                object["journal"] = value
                noteContent = NoteIllustrationPlacement.json(object) ?? noteContent
            } else { noteContent = value }
        })
    }

    private var editorBody: some View {
        VStack(alignment: .leading, spacing: 16) {
            if isTravelNote, NoteIllustrationPlacement.travelObject(noteContent) != nil {
                TextField("目的地", text: Binding(get: { NoteIllustrationPlacement.travelObject(noteContent)?["destination"] as? String ?? "" }, set: { value in
                    guard var object = NoteIllustrationPlacement.travelObject(noteContent) else { return }
                    object["destination"] = value
                    noteContent = NoteIllustrationPlacement.json(object) ?? noteContent
                }))
                .textFieldStyle(.roundedBorder)
                TextField("旅行日期", text: Binding(get: { TravelPlanDocument.decode(noteContent)?.dateRange ?? "" }, set: { value in
                    guard var object = NoteIllustrationPlacement.travelObject(noteContent) else { return }
                    object.removeValue(forKey: "dateRange")
                    object["date_range"] = value
                    noteContent = NoteIllustrationPlacement.json(object) ?? noteContent
                }))
                .textFieldStyle(.roundedBorder)
                Text("旅行手记").font(.headline)
            }
        MarkdownTextEditor(text: editableText, selectedRange: $selectedRange, isFocused: $bodyEditorFocused)
            .frame(minHeight: 360, alignment: .topLeading)
            .overlay(alignment: .topLeading) {
                if editableText.wrappedValue.isEmpty {
                    Text("写下你的想法…")
                        .font(.body)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .padding(.top, 8)
                        .padding(.leading, 4)
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)
                }
            }
            .accessibilityIdentifier("note-body")
        }
    }

    private var isTravelNote: Bool {
        parsedTags.contains { ["旅行", "travel", "trip"].contains($0.lowercased()) }
    }

    private var usesEnglishSelectionUI: Bool {
        ReadingLanguagePresentation.isEnglish(selectedExcerpt)
    }

    @ViewBuilder
    private var selectionDock: some View {
        if isWritingAnnotation,
           !selectedExcerpt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            ReaderSelectionActionDock(
                excerpt: selectedExcerpt,
                isEnglish: usesEnglishSelectionUI,
                annotationDraft: $annotationDraft,
                isWritingAnnotation: $isWritingAnnotation,
                onClose: clearSelection,
                onAsk: { showingQuestion = true },
                onSave: saveSelectionAnnotation
            )
        }
    }

    @ViewBuilder
    private var bottomDock: some View {
        if mode == .preview && !selectedExcerpt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && isWritingAnnotation {
            selectionDock
        } else if mode == .edit {
            VStack(spacing: AppTheme.Spacing.xs) {
                if speechService.state != .idle {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Image(systemName: "waveform")
                            .foregroundStyle(AppTheme.Colors.quantumViolet)
                        Text(speechService.transcript.isEmpty ? "正在聆听…" : speechService.transcript)
                            .font(AppTheme.Typography.supporting)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(2)
                        Spacer()
                        Text(timeString(speechService.elapsedSeconds))
                            .font(AppTheme.Typography.micro.monospacedDigit())
                        Button("完成") { speechService.stop() }
                            .font(AppTheme.Typography.micro.weight(.bold))
                    }
                    .padding(.horizontal, AppTheme.Spacing.md)
                }

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: AppTheme.Spacing.md) {
                        Menu {
                            Button("标题", systemImage: "textformat.size") { beginInsert("## 标题", selecting: "标题") }
                            Button("待办", systemImage: "checklist") { beginInsert("- [ ] 待办事项", selecting: "待办事项") }
                            Button("引用", systemImage: "quote.opening") { beginInsert("> 内容", selecting: "内容") }
                            Button("双链", systemImage: "link") { beginInsert("[[页面名称]]", selecting: "页面名称") }
                            Button("提示块", systemImage: "lightbulb") { beginInsert("> [!note] 重点\n> 写下重点内容", selecting: "写下重点内容") }
                            Button("卡片", systemImage: "rectangle.on.rectangle") { beginInsert("> [!abstract] 卡片标题\n> 卡片内容", selecting: "卡片内容") }
                            Button("代码块", systemImage: "chevron.left.forwardslash.chevron.right") { beginInsert("```text\n代码内容\n```", selecting: "代码内容") }
                            Button("图表", systemImage: "chart.bar") { insertChartTemplate() }
                        } label: { noteTool("格式", icon: "slider.horizontal.3") }
                        Button { openIllustration() } label: { noteTool("AI 配图", icon: "sparkles") }
                            .accessibilityIdentifier("note-illustrate")
                        PhotosPicker(selection: $selectedPhoto, matching: .images) { noteTool("图片", icon: "photo") }
                        Button { toggleVoiceInput() } label: {
                            noteTool(speechService.state == .recording ? "停止录音" : "语音", icon: speechService.state == .recording ? "stop.fill" : "mic")
                        }
                    }
                }
                .padding(.horizontal, AppTheme.Spacing.md)
            }
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(.ultraThinMaterial)
        } else {
            HStack {
                Spacer()
                Button {
                    clearSelection()
                    withAnimation(reduceMotion ? nil : AppTheme.Motion.standard) { mode = .edit }
                    bodyEditorFocused = true
                } label: {
                    Label("编辑", systemImage: "pencil")
                        .font(.headline)
                        .foregroundStyle(.white)
                        .padding(.horizontal, 22)
                        .frame(minHeight: 52)
                        .background(AppTheme.Colors.primary, in: Capsule())
                }
                .accessibilityLabel("编辑笔记")
                .accessibilityIdentifier("note-edit")
                .padding(.trailing, AppTheme.Metrics.contentGutter)
                .padding(.bottom, AppTheme.Spacing.sm)
            }
        }
    }

    private func noteTool(_ title: String, icon: String) -> some View {
        Label(title, systemImage: icon)
            .font(.subheadline.weight(.medium))
            .foregroundStyle(AppTheme.Colors.primary)
            .padding(.horizontal, 16)
            .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
            .background(AppTheme.Colors.mistMint.opacity(0.65), in: Capsule())
    }

    private func openIllustration(anchor: String? = nil) {
        guard saveNow() else { return }
        if isTravelNote {
            guard NoteIllustrationPlacement.travelObject(noteContent) != nil else {
                illustrationLocationError = "旅行内容不是有效行程，请先修复内容；原文仍保留。"; return
            }
            illustrationAnchor = anchor ?? "overview"
        } else {
            guard let selected = NoteIllustrationPlacement.anchor(in: noteContent, selection: selectedRange) else {
                illustrationLocationError = "请把光标放在一段文字中。代码块、空行或重复段落需要先选择明确的位置。"; return
            }
            illustrationAnchor = selected
        }
        dismissEditorKeyboard()
        showingIllustration = true
    }

    private func beginInsert(_ template: String, selecting placeholder: String) {
        bodyEditorFocused = true
        insertMarkdown(template, selecting: placeholder)
    }

    private func dismissEditorKeyboard() {
        titleFocused = false
        tagsFocused = false
        bodyEditorFocused = false
    }

    private func insertChartTemplate() {
        beginInsert(
            """
            ```chart
            {"title":"学习进度","type":"bar","points":[{"label":"周一","value":30},{"label":"周二","value":48},{"label":"周三","value":72}],"summary":"本周学习节奏持续提升。"}
            ```
            """,
            selecting: "学习进度"
        )
    }

    private func toggleVoiceInput() {
        if speechService.state == .idle {
            lastVoiceTranscript = ""
            Task { await speechService.start(autoStopOnSilence: false) }
        } else {
            speechService.stop()
        }
    }

    private func insertVoiceTranscriptIfNeeded() {
        let transcript = speechService.transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !transcript.isEmpty, transcript != lastVoiceTranscript else { return }
        lastVoiceTranscript = transcript
        beginInsert(
            "> [!note] 语音记录 · \(timeString(speechService.elapsedSeconds))\n> \(transcript.replacingOccurrences(of: "\n", with: "\n> "))",
            selecting: "__no_selection__"
        )
    }

    private func timeString(_ seconds: Int) -> String {
        String(format: "%02d:%02d", seconds / 60, seconds % 60)
    }

    private func selectExcerpt(_ excerpt: String) {
        selectedExcerpt = String(excerpt.trimmingCharacters(in: .whitespacesAndNewlines).prefix(4_000))
        annotationDraft = ""
        isWritingAnnotation = false
    }

    private func updateSelectedExcerpt() {
        guard selectedRange.length > 0 else { return }
        let source = noteContent as NSString
        guard selectedRange.location >= 0, NSMaxRange(selectedRange) <= source.length else { return }
        selectExcerpt(source.substring(with: selectedRange))
    }

    private func clearSelection() {
        selectedExcerpt = ""
        annotationDraft = ""
        isWritingAnnotation = false
        selectedRange = NSRange(location: min(selectedRange.location, noteContent.utf16.count), length: 0)
    }

    private func saveSelectionAnnotation() {
        let annotation = annotationDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !annotation.isEmpty else { return }
        appendInlineAnnotation(detail: annotation)
    }

    private func saveSelectionHighlight(_ excerpt: String) {
        selectExcerpt(excerpt)
        appendInlineAnnotation(detail: "")
    }

    private func saveQuestionAnswerAnnotation(question: String, answer: String) {
        appendInlineAnnotation(detail: "我的问题\n\(question)\n\nAI 回答摘要\n\(answer)")
    }

    private func appendInlineAnnotation(detail: String) {
        let excerpt = selectedExcerpt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !excerpt.isEmpty else { return }
        let isEnglish = ReadingLanguagePresentation.isEnglish(excerpt)
        let quote = excerpt.replacingOccurrences(of: "\n", with: "\n> ")
        let note = detail.replacingOccurrences(of: "\n", with: "\n> ")
        let id = UUID().uuidString.lowercased()
        noteContent += "\n\n<!-- quantum-annotation:\(id) -->\n> [!quote] \(isEnglish ? "Selected passage" : "选文")\n> \(quote)\n\n> [!note] \(isEnglish ? "My annotation" : "我的批注")\n> \(note)\n<!-- /quantum-annotation -->"
        clearSelection()
    }

    @MainActor
    private func askAboutSelection(
        _ question: String,
        sessionID: String?
    ) async throws -> AsyncThrowingStream<APIClient.StreamEvent, Error> {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let localNote = ChatLocalNoteDTO(
            id: noteID,
            title: title,
            markdown: noteContent,
            updatedAt: note.map { formatter.string(from: $0.updatedAt) }
        )
        return api.chatStream(
            question: question,
            sessionId: sessionID,
            quotedContext: String(selectedExcerpt.prefix(2_000)),
            contextScope: ChatContextScopeDTO(mode: .localOnly, localNotes: [localNote])
        )
    }

    @MainActor
    private func importPhoto(_ item: PhotosPickerItem) async {
        do {
            guard let original = try await item.loadTransferable(type: Data.self) else {
                throw CocoaError(.fileReadCorruptFile)
            }
            await persistPhoto(original)
        } catch {
            photoImportError = "照片添加失败：\(error.localizedDescription)"
        }
        selectedPhoto = nil
    }

    @MainActor
    private func importCapturedPhoto(_ image: UIImage) async {
        guard let original = image.jpegData(compressionQuality: 0.92) else {
            photoImportError = "照片添加失败：无法读取照片。"
            return
        }
        await persistPhoto(original)
    }

    @MainActor
    private func persistPhoto(_ original: Data) async {
        photoImportError = nil
        do {
            let decodedImageData = await Task.detached(priority: .utility) {
                InboxFileManager.shared.downsampleImage(data: original, maxDimension: 1_600, compressionQuality: 0.84)
            }.value
            guard let imageData = decodedImageData else { throw CocoaError(.fileReadCorruptFile) }
            let attachments = store.vaultDirectory.appendingPathComponent("Attachments", isDirectory: true)
            try FileManager.default.createDirectory(at: attachments, withIntermediateDirectories: true)
            let filename = "\(isTravelNote ? "travel" : "note")-\(UUID().uuidString.lowercased()).jpg"
            try imageData.write(to: attachments.appendingPathComponent(filename), options: [.atomic, .completeFileProtection])
            let path = "Attachments/\(filename)"
            if isTravelNote {
                travelPhotoDraft = TravelPhotoDraft(path: path)
            } else {
                beginInsert("\n\n![笔记图片](\(path))\n\n", selecting: "__no_selection__")
            }
        } catch {
            photoImportError = "照片添加失败：\(error.localizedDescription)"
        }
    }

    @ViewBuilder
    private func relationSection(note: KnowledgeNote) -> some View {
        let resolvedLinks = note.outgoingLinks.compactMap { store.note(matchingLink: $0) }
        let backlinks = store.backlinks(to: note)
        let unresolved = store.unresolvedLinks(in: note)

        if !resolvedLinks.isEmpty || !backlinks.isEmpty || !unresolved.isEmpty {
            Divider()
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                Text("连接")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)

                if !resolvedLinks.isEmpty {
                    relationGroup(title: "链接到", systemImage: "arrow.up.right") {
                        ForEach(resolvedLinks) { linked in
                            NavigationLink(value: linked.id) {
                                relationRow(title: linked.title, detail: linked.preview)
                            }
                            .buttonStyle(SoftButtonStyle())
                        }
                    }
                }

                if !backlinks.isEmpty {
                    relationGroup(title: "反向链接", systemImage: "arrow.uturn.backward") {
                        ForEach(backlinks) { linked in
                            NavigationLink(value: linked.id) {
                                relationRow(title: linked.title, detail: linked.preview)
                            }
                            .buttonStyle(SoftButtonStyle())
                        }
                    }
                }

                if !unresolved.isEmpty {
                    relationGroup(title: "尚未创建", systemImage: "questionmark.diamond") {
                        ForEach(unresolved, id: \.self) { link in
                            Button {
                                if let created = store.createNote(title: link) {
                                    noteContent = noteContent.replacingOccurrences(of: "[[\(link)]]", with: "[[\(created.title)]]")
                                }
                            } label: {
                                HStack {
                                    Text(link)
                                    Spacer()
                                    Label("创建", systemImage: "plus")
                                        .font(.caption.weight(.semibold))
                                }
                                .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(SoftButtonStyle())
                            .foregroundStyle(AppTheme.Icons.interactive)
                        }
                    }
                }
            }
        }
    }

    private func relationGroup<Content: View>(
        title: String,
        systemImage: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textSecondary)
            content()
        }
    }

    private func relationRow(title: String, detail: String) -> some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: "doc.text")
                .foregroundStyle(AppTheme.Colors.textTertiary)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                if !detail.isEmpty {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(1)
                }
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textTertiary)
        }
        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
        .contentShape(Rectangle())
    }

    private func loadNote() {
        guard let note else { return }
        saveTask?.cancel()
        title = note.title == "无标题" ? "" : note.title
        noteContent = note.body
        tagsText = note.tags.joined(separator: ", ")
        isPinned = note.isPinned
        mode = note.title == "无标题" && note.body.isEmpty ? .edit : .preview
        loadedAccount = store.accountFingerprint
        saveStatus = "已保存到本地"
        isLoaded = true
        store.activeNoteDrafts[noteID] = noteContent
        store.resumeIllustrations(id: noteID)
        if note.title == "无标题" {
            Task { @MainActor in titleFocused = true }
        }
    }

    private func scheduleSave() {
        guard isLoaded else { return }
        saveTask?.cancel()
        isSaving = true
        draftRevision += 1
        saveTask = Task {
            try? await Task.sleep(nanoseconds: 650_000_000)
            guard !Task.isCancelled else { return }
            await MainActor.run { _ = saveNow() }
        }
    }

    @discardableResult
    private func saveNow(retrySync: Bool = false) -> Bool {
        saveTask?.cancel()
        isSaving = false
        guard isLoaded, store.accountFingerprint == loadedAccount else { return false }
        let previous = note
        if let saved = store.save(id: noteID, title: title, body: noteContent, tags: parsedTags, isPinned: isPinned) {
            guard saved != previous || retrySync else {
                if saveStatus.hasPrefix("保存失败") { saveStatus = "已保存到本地" }
                return true
            }
            saveStatus = "已保存到本地"
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("-knowledgeHomePreview") { return true }
            #endif
            let revision = draftRevision
            let markdown = store.markdown(for: saved)
            let expectedContentHash = store.contentHash(for: saved)
            let expectedAccount = store.accountFingerprint
            let expectedCredentialGeneration = APIClient.shared.currentCredentialGeneration()
            Task { @MainActor in
                do {
                    guard draftRevision == revision, store.accountFingerprint == expectedAccount,
                          APIClient.shared.currentCredentialGeneration() == expectedCredentialGeneration,
                          store.note(id: saved.id).map(store.contentHash(for:)) == expectedContentHash else {
                        return
                    }
                    let receipt = try await APIClient.shared.syncKnowledgeNote(
                        id: saved.id, markdown: markdown, updatedAt: saved.updatedAt,
                        credentialGeneration: expectedCredentialGeneration
                    )
                    guard draftRevision == revision, store.accountFingerprint == expectedAccount,
                          receipt.noteId == saved.id,
                          receipt.contentHash == expectedContentHash,
                          store.note(id: saved.id).map(store.contentHash(for:)) == expectedContentHash else {
                        return
                    }
                    let status = try await APIClient.shared.fetchKnowledgeNoteStatus(
                        id: saved.id, credentialGeneration: expectedCredentialGeneration
                    )
                    guard draftRevision == revision, store.accountFingerprint == expectedAccount,
                          APIClient.shared.currentCredentialGeneration() == expectedCredentialGeneration,
                          status.noteId == saved.id,
                          store.note(id: saved.id).map(store.contentHash(for:)) == expectedContentHash else {
                        return
                    }
                    saveStatus = KnowledgeNoteStatusPolicy.message(
                        for: status, expectedContentHash: expectedContentHash
                    )
                } catch {
                    guard draftRevision == revision, store.accountFingerprint == expectedAccount,
                          store.note(id: saved.id).map(store.contentHash(for:)) == expectedContentHash else {
                        return
                    }
                    saveStatus = "已保存到本地，云端同步待确认"
                }
            }
            return true
        } else {
            saveStatus = "保存失败，请重试"
            return false
        }
    }

    private func insertMarkdown(_ template: String, selecting placeholder: String) {
        let source = editableText.wrappedValue as NSString
        let location = min(max(selectedRange.location, 0), source.length)
        let length = min(max(selectedRange.length, 0), source.length - location)
        let range = NSRange(location: location, length: length)
        let selectedText = source.substring(with: range)
        var replacement: String

        if !selectedText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            switch placeholder {
            case "页面名称": replacement = "[[\(selectedText)]]"
            case "标签": replacement = "#\(selectedText.replacingOccurrences(of: "#", with: ""))"
            case "标题": replacement = "## \(selectedText)"
            case "待办事项": replacement = "- [ ] \(selectedText)"
            case "内容": replacement = "> \(selectedText)"
            case "代码", "代码内容": replacement = "```text\n\(selectedText)\n```"
            case "写下重点内容": replacement = "> [!note] 重点\n> " + selectedText.replacingOccurrences(of: "\n", with: "\n> ")
            case "卡片内容": replacement = "> [!abstract] 卡片标题\n> " + selectedText.replacingOccurrences(of: "\n", with: "\n> ")
            default: replacement = template
            }
        } else {
            replacement = template
        }

        if replacement.hasPrefix(">") || replacement.hasPrefix("```") || replacement.hasPrefix("##") || replacement.hasPrefix("- ") || replacement.hasPrefix("![") {
            if location > 0 && !source.substring(to: location).hasSuffix("\n\n") { replacement = "\n\n" + replacement }
            if NSMaxRange(range) < source.length && !source.substring(from: NSMaxRange(range)).hasPrefix("\n\n") { replacement += "\n\n" }
        }
        editableText.wrappedValue = source.replacingCharacters(in: range, with: replacement)
        if let placeholderRange = replacement.range(of: placeholder) {
            let offset = replacement.utf16.distance(from: replacement.utf16.startIndex, to: placeholderRange.lowerBound)
            selectedRange = NSRange(location: location + offset, length: placeholder.utf16.count)
        } else {
            selectedRange = NSRange(location: location + (replacement as NSString).length, length: 0)
        }
    }
}

private struct TravelPhotoDraft: Identifiable {
    let id = UUID()
    let path: String
}

private struct TravelCameraPicker: UIViewControllerRepresentable {
    let onCapture: (UIImage) -> Void
    let onCancel: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(parent: self) }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.cameraCaptureMode = .photo
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        let parent: TravelCameraPicker

        init(parent: TravelCameraPicker) { self.parent = parent }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { parent.onCancel() }

        func imagePickerController(
            _ picker: UIImagePickerController,
            didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
        ) {
            guard let image = info[.originalImage] as? UIImage else {
                parent.onCancel()
                return
            }
            parent.onCapture(image)
        }
    }
}

private struct TravelMomentComposer: View {
    enum Stage { case write, arranging, preview }

    @Environment(\.dismiss) private var dismiss
    let imagePath: String
    let baseURL: URL
    let onInsert: (String) -> Void

    @State private var thought: String
    @State private var place: String
    @State private var mood: String
    @State private var stage: Stage
    @State private var style = 1

    init(
        imagePath: String,
        baseURL: URL,
        initialStage: Stage = .write,
        initialThought: String = "",
        initialPlace: String = "",
        initialMood: String = "平静",
        onInsert: @escaping (String) -> Void
    ) {
        self.imagePath = imagePath
        self.baseURL = baseURL
        self.onInsert = onInsert
        _thought = State(initialValue: initialThought)
        _place = State(initialValue: initialPlace)
        _mood = State(initialValue: initialMood)
        _stage = State(initialValue: initialStage)
    }

    var body: some View {
        NavigationStack {
            Group {
                switch stage {
                case .write: writeView
                case .arranging: arrangingView
                case .preview: previewView
                }
            }
            .navigationTitle(stage == .preview ? "笔记预览" : stage == .arranging ? "AI 整理中" : "写下此刻")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(stage == .preview ? "返回" : "取消") { dismiss() }
                }
                if stage == .write {
                    ToolbarItem(placement: .topBarTrailing) {
                        Text("草稿已保存")
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(AppTheme.Colors.textTertiary)
                    }
                }
            }
        }
        .background(AppTheme.Colors.background)
        .presentationDetents([.large])
    }

    private var photo: some View {
        Group {
            if !imagePath.isEmpty,
               let image = UIImage(contentsOfFile: baseURL.appendingPathComponent(imagePath).path) {
                Image(uiImage: image).resizable().scaledToFill()
            } else {
                Image("travel_kyoto_moment").resizable().scaledToFill()
            }
        }
        .frame(maxWidth: .infinity, minHeight: 180, maxHeight: 240)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .clipped()
    }

    private var writeView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                photo
                TextField("雨刚停，石板路反光很好看…", text: $thought, axis: .vertical)
                    .lineLimit(5...9)
                    .padding(AppTheme.Spacing.md)
                    .frame(minHeight: 132, alignment: .topLeading)
                    .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
                    .overlay(alignment: .bottomTrailing) {
                        Text("\(thought.count)/500")
                            .font(AppTheme.Typography.micro)
                            .foregroundStyle(AppTheme.Colors.textTertiary)
                            .padding(AppTheme.Spacing.md)
                    }
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    Label(Date.now.formatted(date: .abbreviated, time: .shortened), systemImage: "clock")
                    LabelField(title: "祇园白川", icon: "mappin.and.ellipse", text: $place)
                    Menu {
                        ForEach(["平静", "惊喜", "热闹", "治愈"], id: \.self) { value in
                            Button(value) { mood = value }
                        }
                    } label: {
                        Label("心情 · \(mood)", systemImage: "face.smiling")
                    }
                    Label("同行 · 2 人", systemImage: "person.2")
                }
                .font(.subheadline.weight(.medium))
                .foregroundStyle(AppTheme.Colors.textSecondary)
                Button("交给 AI 排版", systemImage: "sparkles") { arrange() }
                    .buttonStyle(QuantumPrimaryButtonStyle())
                    .controlSize(.large)
                    .disabled(thought.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(AppTheme.Metrics.contentGutter)
        }
    }

    private var arrangingView: some View {
        VStack(spacing: AppTheme.Spacing.lg) {
            VStack(alignment: .leading, spacing: 0) {
                arrangingRow("识别照片场景", "识别到：京都 · 祇园白川", "1/4", "checkmark.circle.fill", true)
                arrangingRow("校对地点时间", "匹配到 4月13日 16:42", "2/4", "circle.inset.filled", true)
                arrangingRow("润色但保留原意", "保持你的语气与真实感", "3/4", "circle.fill", false)
                arrangingRow("匹配当前篇章", "加入「京都5日行 · DAY 02」", "4/4", "circle.fill", false)
                Toggle("保留我的原话", isOn: .constant(true))
                    .font(.subheadline.weight(.semibold))
                    .padding(.top, AppTheme.Spacing.md)
            }
            .padding(AppTheme.Spacing.xl)
            .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous)
                    .stroke(AppTheme.Colors.border, lineWidth: 0.75)
            }
            Spacer()
            Image(systemName: "sparkles")
                .font(.title2)
                .foregroundStyle(AppTheme.Colors.quantumBlue)
            Text("正在为你整理…")
                .font(.subheadline.weight(.semibold))
        }
        .padding(AppTheme.Metrics.contentGutter)
    }

    private func arrangingRow(
        _ title: String,
        _ detail: String,
        _ progress: String,
        _ icon: String,
        _ active: Bool
    ) -> some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            Image(systemName: icon)
                .foregroundStyle(active ? AppTheme.Colors.quantumBlue : AppTheme.Colors.border)
                .font(.title3)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.subheadline.weight(.semibold))
                Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
            }
            Spacer()
            Text(progress).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary)
        }
        .padding(.vertical, AppTheme.Spacing.md)
    }

    private var previewView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                Label("已准备好加入", systemImage: "checkmark.circle.fill")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.statusCompleted)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                Text("雨后的\(place.isEmpty ? "祇园" : place)")
                    .font(.system(size: 30, weight: .semibold, design: .serif))
                HStack(spacing: AppTheme.Spacing.md) {
                    Label("4月13日 16:42", systemImage: "calendar")
                    Label(place.isEmpty ? "祇园白川" : place, systemImage: "mappin")
                    Label("阴转晴", systemImage: "cloud.sun")
                }
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                photo
                Text(thought.isEmpty ? "雨刚停，石板路反光很好看。抹茶有点苦，但巷子特别安静。走在这样的巷子里，仿佛时间也慢了下来。" : thought)
                    .font(.body)
                    .lineSpacing(6)
                Text("由 AI 整理 · 查看原文 〉")
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
                HStack(spacing: AppTheme.Spacing.sm) {
                    Label("换版式", systemImage: "rectangle.3.group")
                    Spacer()
                    Label("调整文字", systemImage: "character.cursor.ibeam")
                    Spacer()
                    Label("移动到其他天", systemImage: "calendar")
                }
                .font(AppTheme.Typography.micro)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                Divider()
                HStack(spacing: AppTheme.Spacing.sm) {
                    ForEach(Array(["电影感", "日记", "攻略卡"].enumerated()), id: \.offset) { index, name in
                        Button { style = index } label: {
                            VStack(spacing: 5) {
                                Image("travel_kyoto_moment")
                                    .resizable()
                                    .scaledToFill()
                                    .frame(height: 42)
                                    .clipped()
                                Text(name).font(AppTheme.Typography.micro)
                            }
                            .padding(4)
                            .frame(maxWidth: .infinity)
                            .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                            .overlay {
                                RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                                    .stroke(style == index ? AppTheme.Colors.quantumBlue : AppTheme.Colors.border, lineWidth: style == index ? 2 : 0.75)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
                Button("加入 DAY 02", systemImage: "plus.circle.fill") { onInsert(markdown) }
                    .buttonStyle(QuantumPrimaryButtonStyle())
                    .controlSize(.large)
            }
            .padding(AppTheme.Metrics.contentGutter)
        }
    }

    private var markdown: String {
        """
        ## 雨后的\(place.isEmpty ? "祇园" : place)

        \(place.isEmpty ? "" : "📍 \(place) · ")\(Date.now.formatted(date: .abbreviated, time: .shortened)) · \(mood)

        ![[\(imagePath)]]

        \(thought)

        > [!note] 此刻
        > 保留了你的原话，并按旅行日记版式整理。
        """
    }

    private func arrange() {
        stage = .arranging
        Task {
            try? await Task.sleep(for: .milliseconds(650))
            guard !Task.isCancelled else { return }
            stage = .preview
        }
    }
}

private struct LabelField: View {
    let title: String
    let icon: String
    @Binding var text: String

    var body: some View {
        HStack {
            Image(systemName: icon).foregroundStyle(AppTheme.Colors.quantumBlue)
            TextField(title, text: $text)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .frame(minHeight: AppTheme.Metrics.minimumTouchTarget)
        .background(AppTheme.Colors.surfaceTint, in: Capsule())
    }
}

private struct MarkdownTextEditor: UIViewRepresentable {
    @Binding var text: String
    @Binding var selectedRange: NSRange
    @Binding var isFocused: Bool

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> UITextView {
        let textView = UITextView()
        textView.delegate = context.coordinator
        textView.font = UIFont.preferredFont(forTextStyle: .body)
        textView.adjustsFontForContentSizeCategory = true
        textView.textColor = UIColor.label
        textView.backgroundColor = .clear
        textView.isScrollEnabled = true
        textView.alwaysBounceVertical = false
        textView.keyboardDismissMode = .interactive
        textView.textContainerInset = UIEdgeInsets(top: 8, left: 4, bottom: 8, right: 4)
        textView.accessibilityLabel = "Markdown 正文"
        MarkdownVisualStyle.apply(to: textView)
        return textView
    }

    func updateUIView(_ textView: UITextView, context: Context) {
        if textView.text != text {
            textView.text = text
            MarkdownVisualStyle.apply(to: textView)
        }
        let safeLocation = min(max(selectedRange.location, 0), textView.text.utf16.count)
        let safeLength = min(max(selectedRange.length, 0), textView.text.utf16.count - safeLocation)
        let safeRange = NSRange(location: safeLocation, length: safeLength)
        if textView.selectedRange != safeRange { textView.selectedRange = safeRange }
        if isFocused, !textView.isFirstResponder {
            DispatchQueue.main.async { textView.becomeFirstResponder() }
        } else if !isFocused, textView.isFirstResponder {
            DispatchQueue.main.async { textView.resignFirstResponder() }
        }
    }

    final class Coordinator: NSObject, UITextViewDelegate {
        var parent: MarkdownTextEditor

        init(_ parent: MarkdownTextEditor) { self.parent = parent }

        func textViewDidChange(_ textView: UITextView) {
            parent.text = textView.text
            parent.selectedRange = textView.selectedRange
            MarkdownVisualStyle.apply(to: textView)
        }

        func textViewDidChangeSelection(_ textView: UITextView) {
            parent.selectedRange = textView.selectedRange
        }

        func textViewDidBeginEditing(_ textView: UITextView) { parent.isFocused = true }
        func textViewDidEndEditing(_ textView: UITextView) { parent.isFocused = false }
    }
}

enum MarkdownVisualStyle {
    enum Kind: Equatable { case heading(Int), strong, quote, code, link }
    struct Span: Equatable { let range: NSRange; let kind: Kind }

    static func spans(in text: String) -> [Span] {
        let fullRange = NSRange(location: 0, length: (text as NSString).length)
        let patterns: [(String, (NSTextCheckingResult) -> Span?)] = [
            (#"(?m)^(#{1,3})\s+(.+)$"#, { $0.numberOfRanges > 2 ? Span(range: $0.range(at: 2), kind: .heading($0.range(at: 1).length)) : nil }),
            (#"\*\*(.+?)\*\*"#, { $0.numberOfRanges > 1 ? Span(range: $0.range(at: 1), kind: .strong) : nil }),
            (#"(?m)^>\s?.+$"#, { Span(range: $0.range, kind: .quote) }),
            (#"(?s)```.*?```"#, { Span(range: $0.range, kind: .code) }),
            (#"\[\[[^\]]+\]\]"#, { Span(range: $0.range, kind: .link) }),
        ]
        return patterns.flatMap { pattern, builder in
            (try? NSRegularExpression(pattern: pattern))?.matches(in: text, range: fullRange).compactMap(builder) ?? []
        }
    }

    static func apply(to textView: UITextView) {
        let selection = textView.selectedRange
        let fullRange = NSRange(location: 0, length: textView.textStorage.length)
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineSpacing = 5
        paragraph.paragraphSpacing = 5
        let base: [NSAttributedString.Key: Any] = [
            .font: UIFont.preferredFont(forTextStyle: .body),
            .foregroundColor: UIColor.label,
            .paragraphStyle: paragraph,
        ]
        textView.textStorage.setAttributes(base, range: fullRange)
        for span in spans(in: textView.text) where NSMaxRange(span.range) <= fullRange.length {
            switch span.kind {
            case .heading(let level):
                let style: UIFont.TextStyle = level == 1 ? .title1 : (level == 2 ? .title2 : .title3)
                textView.textStorage.addAttribute(.font, value: UIFont.preferredFont(forTextStyle: style).boldVariant(), range: span.range)
            case .strong:
                textView.textStorage.addAttribute(.font, value: UIFont.preferredFont(forTextStyle: .body).boldVariant(), range: span.range)
            case .quote:
                textView.textStorage.addAttributes([.foregroundColor: UIColor.secondaryLabel, .backgroundColor: UIColor.systemMint.withAlphaComponent(0.12)], range: span.range)
            case .code:
                textView.textStorage.addAttributes([.font: UIFont.monospacedSystemFont(ofSize: UIFont.preferredFont(forTextStyle: .body).pointSize * 0.92, weight: .regular), .backgroundColor: UIColor.secondarySystemBackground], range: span.range)
            case .link:
                textView.textStorage.addAttributes([.foregroundColor: UIColor.systemBlue, .underlineStyle: NSUnderlineStyle.single.rawValue], range: span.range)
            }
        }
        textView.selectedRange = selection
        textView.typingAttributes = base
    }
}

private extension UIFont {
    func boldVariant() -> UIFont {
        guard let descriptor = fontDescriptor.withSymbolicTraits(.traitBold) else { return self }
        return UIFont(descriptor: descriptor, size: pointSize)
    }
}

struct NoteInlineAnnotation: Identifiable, Hashable, Sendable {
    let id: String
    let quote: String
    let detail: String

    static func extract(from source: String) -> (body: String, annotations: [NoteInlineAnnotation]) {
        let lines = source.components(separatedBy: .newlines)
        var visible: [String] = []
        var annotations: [NoteInlineAnnotation] = []
        var index = 0

        while index < lines.count {
            let line = lines[index].trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("<!-- quantum-annotation:") {
                let id = line
                    .replacingOccurrences(of: "<!-- quantum-annotation:", with: "")
                    .replacingOccurrences(of: "-->", with: "")
                    .trimmingCharacters(in: .whitespaces)
                let end = lines[(index + 1)...].firstIndex {
                    $0.trimmingCharacters(in: .whitespaces) == "<!-- /quantum-annotation -->"
                } ?? lines.endIndex
                if let annotation = parsePair(in: lines, from: index + 1, before: end, id: id) {
                    annotations.append(annotation)
                    visible.append("")
                    index = end < lines.endIndex ? end + 1 : end
                    continue
                }
            }

            if let quote = callout(in: lines, at: index),
               quote.type == "quote",
               ["选文", "Selected passage"].contains(quote.title) {
                var noteIndex = quote.next
                while noteIndex < lines.count, lines[noteIndex].trimmingCharacters(in: .whitespaces).isEmpty {
                    noteIndex += 1
                }
                if let note = callout(in: lines, at: noteIndex),
                   note.type == "note",
                   ["我的批注", "My annotation"].contains(note.title) {
                    annotations.append(.init(id: "legacy-\(index)-\(quote.text.utf8.count)", quote: quote.text, detail: note.text))
                    visible.append("")
                    index = note.next
                    continue
                }
            }

            visible.append(lines[index])
            index += 1
        }

        return (visible.joined(separator: "\n"), annotations)
    }

    private static func parsePair(
        in lines: [String],
        from start: Int,
        before end: Int,
        id: String
    ) -> NoteInlineAnnotation? {
        guard start < end else { return nil }
        var cursor = start
        while cursor < end, lines[cursor].trimmingCharacters(in: .whitespaces).isEmpty { cursor += 1 }
        guard let quote = callout(in: lines, at: cursor), quote.type == "quote" else { return nil }
        cursor = quote.next
        while cursor < end, lines[cursor].trimmingCharacters(in: .whitespaces).isEmpty { cursor += 1 }
        guard let note = callout(in: lines, at: cursor), note.type == "note" else { return nil }
        return .init(id: id.isEmpty ? UUID().uuidString : id, quote: quote.text, detail: note.text)
    }

    private static func callout(
        in lines: [String],
        at index: Int
    ) -> (type: String, title: String, text: String, next: Int)? {
        guard lines.indices.contains(index) else { return nil }
        let header = lines[index].trimmingCharacters(in: .whitespaces)
        guard header.hasPrefix("> [!"), let close = header.firstIndex(of: "]") else { return nil }
        let typeStart = header.index(header.startIndex, offsetBy: 4)
        let type = String(header[typeStart..<close]).lowercased()
        let title = String(header[header.index(after: close)...]).trimmingCharacters(in: .whitespaces)
        var content: [String] = []
        var cursor = index + 1
        while cursor < lines.count {
            let line = lines[cursor].trimmingCharacters(in: .whitespaces)
            guard line.hasPrefix(">"), !line.hasPrefix("> [!") else { break }
            content.append(String(line.dropFirst()).trimmingCharacters(in: .whitespaces))
            cursor += 1
        }
        return (type, title, content.joined(separator: "\n"), cursor)
    }
}

private struct NoteReadingView: View {
    let content: String
    var baseURL: URL? = nil
    var onSelection: (String) -> Void = { _ in }
    var onAskSelection: (String) -> Void = { _ in }
    var onHighlightSelection: (String) -> Void = { _ in }
    var onAnnotateSelection: (String) -> Void = { _ in }
    var onAnnotationTap: (NoteInlineAnnotation) -> Void = { _ in }
    @State private var blocks: [NoteReadingBlock] = []
    @State private var annotations: [NoteInlineAnnotation] = []

    var body: some View {
        LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            if blocks.isEmpty && !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                ProgressView("正在排版…")
                    .frame(maxWidth: .infinity, minHeight: 120)
            } else if blocks.isEmpty {
                Text("这篇笔记还没有正文。")
                    .font(.body)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            } else {
                ForEach(blocks) { block in
                    block.view(
                        baseURL: baseURL,
                        annotations: annotations,
                        onSelection: onSelection,
                        onAskSelection: onAskSelection,
                        onHighlightSelection: onHighlightSelection,
                        onAnnotateSelection: onAnnotateSelection,
                        onAnnotationTap: onAnnotationTap
                    )
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .textSelection(.enabled)
        .task(id: content) {
            let parsed = await Task.detached(priority: .userInitiated) {
                let extraction = NoteInlineAnnotation.extract(from: content)
                return (NoteReadingBlock.parse(extraction.body), extraction.annotations)
            }.value
            guard !Task.isCancelled else { return }
            blocks = parsed.0
            annotations = parsed.1
        }
    }
}

private struct NoteAnnotationDetailSheet: View {
    let annotation: NoteInlineAnnotation
    let noteTitle: String
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xl) {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Image(systemName: "bookmark.fill")
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("我的批注")
                                .font(AppTheme.Typography.label)
                            Text(noteTitle)
                                .font(AppTheme.Typography.micro)
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                    }

                    HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(AppTheme.Colors.quantumBlue)
                            .frame(width: 4)
                        Text(annotation.quote)
                            .font(.system(.body, design: .serif, weight: .medium))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .lineSpacing(6)
                    }
                    .padding(AppTheme.Spacing.md)
                    .background(AppTheme.Colors.mistSky.opacity(0.72), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))

                    VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                        if let question = questionText {
                            Text("我的问题").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary)
                            Text(question).font(AppTheme.Typography.body)
                            Text("AI 回答摘要").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary)
                            MarkdownText(answerText ?? "").font(AppTheme.Typography.body).lineSpacing(6)
                        } else {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                            Label("我的读书笔记", systemImage: "pencil.line")
                                .font(.system(.headline, design: .rounded, weight: .bold))
                                .foregroundStyle(AppTheme.Colors.quantumBlue)
                            Text(annotation.detail)
                                .font(.system(.body, design: .serif))
                                .foregroundStyle(AppTheme.Colors.textPrimary)
                                .lineSpacing(9)
                                .textSelection(.enabled)
                        }
                        }
                    }
                    .padding(AppTheme.Spacing.lg)
                    .frame(minHeight: 220, alignment: .topLeading)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: AppTheme.Radius.lg))
                    .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.lg).stroke(AppTheme.Colors.border.opacity(0.55)) }

                    Label("返回原文后，点有颜色的下划线或页边书签即可再次查看。", systemImage: "hand.tap")
                        .font(AppTheme.Typography.supporting)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .background(Color.white.ignoresSafeArea())
            .navigationTitle("批注")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { dismiss() } } }
        }
        .presentationDetents([.medium, .large])
    }

    private var questionText: String? { splitDetail.0 }
    private var answerText: String? { splitDetail.1 }
    private var splitDetail: (String?, String?) {
        guard let questionRange = annotation.detail.range(of: "我的问题"),
              let answerRange = annotation.detail.range(of: "AI 回答摘要") else { return (nil, nil) }
        let question = annotation.detail[questionRange.upperBound..<answerRange.lowerBound]
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let answer = annotation.detail[answerRange.upperBound...]
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return (question.isEmpty ? nil : question, answer.isEmpty ? nil : answer)
    }
}

struct TravelNoteSaveSheet: View {
    @Environment(\.dismiss) private var dismiss
    let content: String
    let onSave: (String, String) -> Void

    @State private var noteTitle: String
    @State private var selectedCover = 0
    @State private var privacy = "公开"
    @State private var includesRoute = true
    @State private var includesPhotos = true
    @State private var includesPlaces = true

    private let covers = [
        "travel_kyoto_camera",
        "travel_kyoto_bamboo",
        "travel_kyoto_street",
        "travel_kyoto_bridge"
    ]

    init(title: String, content: String, onSave: @escaping (String, String) -> Void) {
        self.content = content
        self.onSave = onSave
        _noteTitle = State(initialValue: title.isEmpty ? "京都五日 · 春日行记" : title)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        Text("笔记标题").font(.caption.weight(.semibold))
                        TextField("旅行笔记标题", text: $noteTitle)
                            .textFieldStyle(.roundedBorder)
                            .overlay(alignment: .trailing) {
                                Text("\(noteTitle.count)/30")
                                    .font(AppTheme.Typography.micro)
                                    .foregroundStyle(AppTheme.Colors.textTertiary)
                                    .padding(.trailing, AppTheme.Spacing.sm)
                            }
                    }

                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        Text("封面照片").font(.caption.weight(.semibold))
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: AppTheme.Spacing.sm) {
                                ForEach(Array(covers.enumerated()), id: \.offset) { index, cover in
                                    Button { selectedCover = index } label: {
                                        Image(cover)
                                            .resizable()
                                            .scaledToFill()
                                            .frame(width: 72, height: 78)
                                            .clipped()
                                            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                                            .overlay {
                                                RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                                                    .stroke(selectedCover == index ? AppTheme.Colors.quantumBlue : Color.clear, lineWidth: 3)
                                            }
                                    }
                                    .buttonStyle(.plain)
                                    .accessibilityLabel("选择第 \(index + 1) 张封面")
                                }
                            }
                        }
                    }

                    saveOption(icon: "lock.fill", title: "隐私设置", detail: nil) {
                        Menu(privacy) {
                            ForEach(["公开", "仅自己", "同行可见"], id: \.self) { value in
                                Button(value) { privacy = value }
                            }
                        }
                    }
                    saveOption(icon: "list.bullet", title: "包含行程", detail: "已选择 5 天行程与地图") {
                        Toggle("包含行程", isOn: $includesRoute).labelsHidden()
                    }
                    saveOption(icon: "photo", title: "包含照片", detail: "已选择 28 张照片") {
                        Toggle("包含照片", isOn: $includesPhotos).labelsHidden()
                    }
                    saveOption(icon: "doc.text", title: "包含地点与推荐", detail: "收藏的景点、美食、住宿等") {
                        Toggle("包含地点与推荐", isOn: $includesPlaces).labelsHidden()
                    }

                    Button("生成旅行笔记", systemImage: "sparkles") {
                        onSave(noteTitle.trimmingCharacters(in: .whitespacesAndNewlines), content)
                        dismiss()
                    }
                    .buttonStyle(QuantumPrimaryButtonStyle())
                    .controlSize(.large)
                    .disabled(noteTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                    Text("你的旅程，值得被好好记录。")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textTertiary)
                        .frame(maxWidth: .infinity)
                }
                .padding(AppTheme.Metrics.contentGutter)
            }
            .background(AppTheme.Colors.background)
            .navigationTitle("保存为旅行笔记")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("关闭", systemImage: "xmark") { dismiss() } }
        }
        .presentationDetents([.fraction(0.72), .large])
    }

    private func saveOption<Trailing: View>(
        icon: String,
        title: String,
        detail: String?,
        @ViewBuilder trailing: () -> Trailing
    ) -> some View {
        HStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: icon)
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .frame(width: 28, height: 28)
                .background(AppTheme.Colors.surfaceTint, in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.semibold))
                if let detail {
                    Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary)
                }
            }
            Spacer()
            trailing()
        }
        .padding(.vertical, AppTheme.Spacing.xs)
    }
}

struct TravelNoteReadingView: View {
    enum Page: String, CaseIterable, Identifiable {
        case cover = "概览"
        case day = "行程"
        case place = "地点"
        case appendix = "检查"

        var id: Self { self }
    }

    let title: String
    let content: String
    let baseURL: URL
    let showsPagePicker: Bool
    let onSelection: (String) -> Void
    let onIllustrate: ((String) -> Void)?
    @State private var page: Page

    init(
        title: String,
        content: String,
        baseURL: URL,
        initialPage: Page = .cover,
        showsPagePicker: Bool = true,
        onSelection: @escaping (String) -> Void = { _ in },
        onIllustrate: ((String) -> Void)? = nil
    ) {
        self.title = title
        self.content = content
        self.baseURL = baseURL
        self.showsPagePicker = showsPagePicker
        self.onSelection = onSelection
        self.onIllustrate = onIllustrate
        _page = State(initialValue: initialPage)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            if showsPagePicker {
                Picker("旅行笔记页面", selection: $page) {
                    ForEach(Page.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
            }

            TravelPlanResultView(title: title, content: content, initialPage: resultPage, baseURL: baseURL, onIllustrate: onIllustrate)
                .id(page)
        }
    }

    private var resultPage: TravelPlanResultView.Page {
        switch page {
        case .cover: .overview
        case .day: .day
        case .place: .place
        case .appendix: .check
        }
    }

    private var coverPage: some View {
        GeometryReader { geometry in
            ZStack(alignment: .topLeading) {
                Image("travel_kyoto_camera")
                    .resizable()
                    .scaledToFill()
                    .frame(width: geometry.size.width, height: 650)
                    .offset(y: -24)
                LinearGradient(
                    colors: [Color.white.opacity(0.94), Color.clear, Color.black.opacity(0.58)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: AppTheme.Spacing.sm) {
                    Image("quantum_logo_icon")
                        .resizable()
                        .scaledToFit()
                        .frame(width: 38, height: 38)
                    VStack(alignment: .leading, spacing: 1) {
                        Image("quantum_wordmark")
                            .resizable()
                            .scaledToFit()
                            .frame(width: 112, alignment: .leading)
                        Text("知识，让世界更大")
                            .font(.system(size: 9, weight: .medium))
                            .tracking(2)
                    }
                    Spacer()
                    Text("KYOTO\nJAPAN")
                        .font(.system(size: 9, weight: .semibold, design: .monospaced))
                        .tracking(1.5)
                }
                .foregroundStyle(AppTheme.Colors.textPrimary)

                Text(title.isEmpty ? "京都五日 ·\n春日行记" : title.replacingOccurrences(of: "·", with: "·\n"))
                    .font(.system(size: 42, weight: .semibold, design: .serif))
                    .tracking(1)
                    .lineSpacing(3)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .padding(.top, 38)

                Text("4月12日 — 4月16日")
                    .font(.subheadline.weight(.semibold))
                    .padding(.top, AppTheme.Spacing.sm)

                Spacer()

                Text("在古都的春天里，\n走过寺院、巷弄与山丘。\n收藏一段温柔的时光。")
                    .font(.system(size: 17, weight: .medium, design: .serif))
                    .lineSpacing(5)
                    .foregroundStyle(.white)

                HStack {
                    Label("2人同行", systemImage: "person.2.fill")
                    Spacer()
                    Label("18°–22°", systemImage: "sun.max.fill")
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.top, AppTheme.Spacing.xl)
                }
                .padding(AppTheme.Spacing.xl)
                .frame(width: geometry.size.width, height: 610, alignment: .topLeading)
            }
            .frame(width: geometry.size.width, height: 610)
            .clipped()
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
        }
        .frame(height: 610)
        .accessibilityElement(children: .combine)
    }

    private var dayPage: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("DAY 02")
                        .font(.system(size: 28, weight: .semibold, design: .serif))
                    Text("岚山 · 竹林与渡月桥")
                        .font(.headline.weight(.semibold))
                }
                Spacer()
                Text("4月13日 周六")
                    .font(.caption)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }

            Text("清晨的岚山，空气里是竹叶与樱花的清香。沿着竹林小径缓步向前，阳光从高处洒下，光影在石阶上摇晃。过了渡月桥，河水静静流向远方。")
                .font(.body)
                .lineSpacing(5)

            HStack(spacing: 4) {
                Image("travel_kyoto_bamboo")
                    .resizable()
                    .scaledToFill()
                    .frame(maxWidth: .infinity, minHeight: 252)
                    .clipped()
                    .overlay(alignment: .bottomLeading) {
                        Text("行走的意义，\n更看见更大的自己。")
                            .font(.system(size: 17, weight: .medium, design: .serif))
                            .foregroundStyle(.white)
                            .padding(AppTheme.Spacing.md)
                    }
                VStack(spacing: 4) {
                    Image("travel_kyoto_bridge").resizable().scaledToFill().frame(height: 124).clipped()
                    Image("travel_kyoto_street").resizable().scaledToFill().frame(height: 124).clipped()
                }
                .frame(maxWidth: .infinity)
            }
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))

            HStack {
                routeStop("岚山站", "09:00", true)
                Spacer()
                routeStop("竹林小径", "09:30", false)
                Spacer()
                routeStop("渡月桥", "11:00", false)
            }
            .overlay(alignment: .top) {
                Rectangle()
                    .fill(AppTheme.Colors.border)
                    .frame(height: 2)
                    .padding(.horizontal, 32)
                    .offset(y: 5)
            }

            HStack(spacing: AppTheme.Spacing.md) {
                Image("travel_kyoto_bamboo")
                    .resizable()
                    .scaledToFill()
                    .frame(width: 78, height: 84)
                    .clipped()
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                VStack(alignment: .leading, spacing: 4) {
                    Text("竹林の小径").font(.headline)
                    Text("自然景观 · 免费 · 约 1–1.5 小时")
                        .font(AppTheme.Typography.micro)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                    Text("穿过高耸的竹林，感受京都最具代表性的宁静与诗意。")
                        .font(.caption)
                        .lineLimit(2)
                }
                Spacer()
                Image(systemName: "chevron.right")
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
            .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(AppTheme.Colors.border, lineWidth: 0.75) }

            if !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                NoteReadingView(content: content, baseURL: baseURL, onSelection: onSelection)
            }
        }
    }

    private func routeStop(_ title: String, _ time: String, _ selected: Bool) -> some View {
        VStack(spacing: 5) {
            Circle()
                .fill(selected ? AppTheme.Colors.quantumBlue : AppTheme.Colors.cardBackground)
                .overlay { Circle().stroke(AppTheme.Colors.quantumBlue, lineWidth: 2) }
                .frame(width: 12, height: 12)
            Text(title).font(.caption.weight(.semibold))
            Text(time).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary)
        }
        .zIndex(1)
    }

    private var appendixPage: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(spacing: AppTheme.Spacing.sm) {
                ForEach(["住", "食", "行", "提醒"], id: \.self) { item in
                    Label(item, systemImage: appendixIcon(item))
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(item == "住" ? AppTheme.Colors.quantumBlue : AppTheme.Colors.textSecondary)
                        .frame(maxWidth: .infinity, minHeight: 42)
                        .background(item == "住" ? AppTheme.Colors.mistSky : AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                }
            }

            Text("行程地图").font(.headline)
            TravelRouteMap()

            HStack {
                Text("已收藏的地点").font(.headline)
                Spacer()
                Text("共 12 个地点 〉").font(.caption).foregroundStyle(AppTheme.Colors.textSecondary)
            }
            HStack(spacing: AppTheme.Spacing.sm) {
                placeCard("清水寺", "寺庙 · 京都市", "travel_kyoto_bridge")
                placeCard("% Arabica", "咖啡 · 岚山", "travel_kyoto_bamboo")
                placeCard("锦市场", "美食 · 中京区", "travel_kyoto_street")
            }

            LazyVGrid(columns: [.init(.flexible()), .init(.flexible())], spacing: AppTheme.Spacing.sm) {
                TravelInfoCard(icon: "building.2.fill", title: "住宿", value: "¥8,400", detail: "4晚 · 京都市内", color: AppTheme.Colors.quantumBlue)
                TravelInfoCard(icon: "tram.fill", title: "交通", value: "¥2,360", detail: "地铁 · 巴士 · JR", color: AppTheme.Colors.quantumBlue)
                TravelInfoCard(icon: "fork.knife", title: "餐饮", value: "¥4,800", detail: "约 10 餐", color: AppTheme.Colors.statusError)
                TravelInfoCard(icon: "cross.case.fill", title: "其他与应急", value: "¥1,200", detail: "门票 · 购物 · 备用金", color: AppTheme.Colors.quantumBlue)
            }

            HStack(spacing: AppTheme.Spacing.sm) {
                Button("继续记录", systemImage: "pencil") {}
                    .buttonStyle(.bordered)
                Button("导出 PDF", systemImage: "doc") {}
                    .buttonStyle(.bordered)
                Button("分享", systemImage: "square.and.arrow.up") {}
                    .buttonStyle(.borderedProminent)
            }
            .frame(maxWidth: .infinity)
        }
    }

    private func placeCard(_ title: String, _ subtitle: String, _ image: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Image(image).resizable().scaledToFill().frame(height: 62).clipped()
            Text(title).font(.caption.weight(.semibold)).lineLimit(1)
            Text(subtitle).font(.system(size: 9)).foregroundStyle(AppTheme.Colors.textTertiary).lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
    }

    private func appendixIcon(_ item: String) -> String {
        switch item {
        case "住": "bed.double.fill"
        case "食": "fork.knife"
        case "行": "tram.fill"
        default: "bell.fill"
        }
    }
}

struct TravelRouteStop: Decodable, Hashable, Identifiable {
    let name: String
    let latitude: Double
    let longitude: Double

    var id: String { "\(name)-\(latitude)-\(longitude)" }
    var coordinate: CLLocationCoordinate2D { .init(latitude: latitude, longitude: longitude) }
}

struct TravelPlanDocument: Decodable, Equatable {
    let destination: String?
    let dateRange: String?
    let budget: String?
    let companions: Int?
    let style: String?
    let stops: [TravelRouteStop]

    private enum CodingKeys: String, CodingKey {
        case destination, dateRange, budget, companions, style, stops
    }

    init(destination: String?, dateRange: String?, budget: String?, companions: Int?, style: String?, stops: [TravelRouteStop]) {
        self.destination = destination
        self.dateRange = dateRange
        self.budget = budget
        self.companions = companions
        self.style = style
        self.stops = stops
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        destination = try values.decodeIfPresent(String.self, forKey: .destination)
        dateRange = try values.decodeIfPresent(String.self, forKey: .dateRange)
        budget = try values.decodeIfPresent(String.self, forKey: .budget)
        companions = try values.decodeIfPresent(Int.self, forKey: .companions)
        style = try values.decodeIfPresent(String.self, forKey: .style)
        stops = try values.decodeIfPresent([TravelRouteStop].self, forKey: .stops) ?? []
    }

    static func decode(_ content: String) -> Self? {
        let payload = NoteIllustrationPlacement.travelPayload(content)
        guard let data = payload.data(using: .utf8) else { return nil }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(Self.self, from: data)
    }

    static let kyotoPreview = Self(
        destination: "日本 · 京都",
        dateRange: "4月12日 – 4月16日（5天）",
        budget: "约 ¥8,000/人",
        companions: 2,
        style: "人文 · 美食",
        stops: [
            .init(name: "岚山", latitude: 35.0094, longitude: 135.6668),
            .init(name: "金阁寺", latitude: 35.0394, longitude: 135.7292),
            .init(name: "京都站", latitude: 34.9858, longitude: 135.7588),
            .init(name: "清水寺", latitude: 34.9949, longitude: 135.7850),
            .init(name: "伏见稻荷", latitude: 34.9671, longitude: 135.7727),
        ]
    )
}

struct TravelRouteMap: View {
    let stops: [TravelRouteStop]
    let height: CGFloat
    @State private var position: MapCameraPosition = .automatic

    init(stops: [TravelRouteStop] = TravelPlanDocument.kyotoPreview.stops, height: CGFloat = 190) {
        self.stops = stops
        self.height = height
    }

    var body: some View {
        Map(position: $position, interactionModes: [.pan, .zoom]) {
            MapPolyline(coordinates: stops.map(\.coordinate))
                .stroke(AppTheme.Colors.quantumBlue, style: StrokeStyle(lineWidth: 4, lineCap: .round, lineJoin: .round))
            ForEach(stops) { stop in
                Annotation("", coordinate: stop.coordinate, anchor: .bottom) {
                    VStack(spacing: 2) {
                        Image(systemName: "mappin.circle.fill")
                            .font(.title3)
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                        Text(stop.name)
                            .font(.system(size: 9, weight: .semibold))
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(.ultraThinMaterial, in: Capsule())
                    }
                }
            }
        }
        .mapStyle(.standard(elevation: .flat))
        .onAppear { position = .region(Self.region(for: stops)) }
        .frame(height: height)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.md, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.md).stroke(AppTheme.Colors.border, lineWidth: 0.75) }
        .accessibilityLabel("旅行路线地图，共 \(stops.count) 个地点")
    }

    private static func region(for stops: [TravelRouteStop]) -> MKCoordinateRegion {
        guard let first = stops.first else {
            return .init(center: .init(latitude: 35.0116, longitude: 135.7681), span: .init(latitudeDelta: 0.12, longitudeDelta: 0.16))
        }
        let latitudes = stops.map(\.latitude)
        let longitudes = stops.map(\.longitude)
        let minLatitude = latitudes.min() ?? first.latitude
        let maxLatitude = latitudes.max() ?? first.latitude
        let minLongitude = longitudes.min() ?? first.longitude
        let maxLongitude = longitudes.max() ?? first.longitude
        return .init(
            center: .init(latitude: (minLatitude + maxLatitude) / 2, longitude: (minLongitude + maxLongitude) / 2),
            span: .init(
                latitudeDelta: max((maxLatitude - minLatitude) * 1.65, 0.06),
                longitudeDelta: max((maxLongitude - minLongitude) * 1.45, 0.09)
            )
        )
    }
}

private struct TravelInfoCard: View {
    let icon: String
    let title: String
    let value: String
    let detail: String
    let color: Color

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            Image(systemName: icon).foregroundStyle(color).frame(width: 26, height: 26)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.caption.weight(.semibold))
                Text(value).font(.subheadline.weight(.bold))
                Text(detail).font(.system(size: 9)).foregroundStyle(AppTheme.Colors.textTertiary)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 76, alignment: .topLeading)
        .padding(AppTheme.Spacing.sm)
        .background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
        .overlay { RoundedRectangle(cornerRadius: AppTheme.Radius.sm).stroke(AppTheme.Colors.border, lineWidth: 0.75) }
    }
}

struct TravelPlanResultView: View {
    enum Page { case overview, day, place, check }

    @Environment(\.dismiss) private var dismiss
    let title: String
    let content: String
    @State private var page: Page
    let baseURL: URL?
    let onIllustrate: ((String) -> Void)?
    private var previewOnly: Bool { content.isEmpty && ProcessInfo.processInfo.arguments.contains("-prototypePreview") }

    init(title: String, content: String, initialPage: Page = .overview, baseURL: URL? = nil, onIllustrate: ((String) -> Void)? = nil) {
        self.title = title
        self.content = content
        self.baseURL = baseURL
        self.onIllustrate = onIllustrate
        _page = State(initialValue: initialPage)
    }

    private var plan: TravelPlanDocument {
        TravelPlanDocument.decode(content) ?? (previewOnly ? .kyotoPreview : TravelPlanDocument(destination: nil, dateRange: nil, budget: nil, companions: nil, style: nil, stops: []))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            if TravelPlanDocument.decode(content) == nil && !previewOnly {
                Label("旅行版式暂时无法读取，原文已保留。", systemImage: "exclamationmark.circle")
                    .font(.subheadline).foregroundStyle(AppTheme.Colors.textSecondary)
                NoteReadingView(content: content, baseURL: baseURL)
            } else {
                switch page {
                case .overview:
                    overview
                    travelImages("overview")
                    if let journal = NoteIllustrationPlacement.travelObject(content)?["journal"] as? String, !journal.isEmpty {
                        NoteReadingView(content: journal, baseURL: baseURL)
                    }
                case .day:
                    if previewOnly { dailyPlan } else { actualStops }
                case .place:
                    if previewOnly { placeDetail } else { actualStops }
                case .check:
                    if previewOnly { tripCheck } else {
                        VStack(alignment: .leading, spacing: 16) {
                            Text("行程检查").font(.title2.bold())
                            checkRow(!plan.stops.isEmpty, "行程地点", plan.stops.isEmpty ? "尚未填写" : "共 \(plan.stops.count) 个地点")
                            checkRow(plan.dateRange != nil, "旅行日期", plan.dateRange ?? "尚未填写")
                            checkRow(plan.budget != nil, "预算", plan.budget ?? "尚未填写")
                            Text("此处只核对笔记中已有信息，不代表机票、住宿或预约已确认。")
                                .font(.footnote).foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                    }
                }
            }
        }
        .animation(AppTheme.Motion.standard, value: page)
    }

    private var overview: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            ZStack(alignment: .bottomLeading) {
                GeometryReader { geometry in
                    if previewOnly {
                        Image("travel_kyoto_camera").resizable().scaledToFill()
                            .frame(width: geometry.size.width, height: geometry.size.height).clipped()
                    } else {
                        AppTheme.Colors.mistMint
                        Image(systemName: "map")
                            .font(.system(size: 150, weight: .ultraLight))
                            .foregroundStyle(AppTheme.Colors.quantumBlue.opacity(0.22))
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
                LinearGradient(colors: [.clear, .black.opacity(0.12), .black.opacity(0.78)], startPoint: .top, endPoint: .bottom)
                VStack(alignment: .leading, spacing: 4) {
                    Text(plan.destination ?? "我的旅行").font(.caption.weight(.semibold))
                    Text(title.isEmpty ? "我的旅行" : title).font(.system(size: 36, weight: .semibold, design: .serif))
                    Text(plan.dateRange ?? "日期待填写").font(.subheadline.weight(.medium))

                    HStack(alignment: .bottom) {
                        Text("在步履中，\n记录自己的风景。")
                            .font(.system(size: 18, weight: .medium, design: .serif))
                            .lineSpacing(5)
                        Spacer()
                        if previewOnly { HStack(spacing: 8) {
                            Image(systemName: "sun.max.fill").font(.title2).foregroundStyle(.orange)
                            VStack(alignment: .leading, spacing: 1) {
                                Text("18° 晴").font(.headline)
                                Text("12° / 22°").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .padding(.horizontal, AppTheme.Spacing.md)
                        .frame(minHeight: 66)
                        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md)) }
                    }
                    .padding(.top, AppTheme.Spacing.lg)
                }
                .foregroundStyle(.white).padding(AppTheme.Spacing.lg)

                if baseURL == nil { VStack {
                    HStack {
                        Button { dismiss() } label: {
                            Image(systemName: "chevron.left")
                                .frame(width: 42, height: 42)
                                .background(.ultraThinMaterial, in: Circle())
                        }
                        Spacer()
                        ShareLink(item: "\(title)\n\(content)") {
                            Image(systemName: "square.and.arrow.up")
                                .frame(width: 42, height: 42)
                                .background(.ultraThinMaterial, in: Circle())
                        }
                        Menu {
                            Button("查看每日行程", systemImage: "list.bullet") { page = .day }
                            Button("检查行程", systemImage: "checkmark.circle") { page = .check }
                        } label: {
                            Image(systemName: "ellipsis")
                                .frame(width: 42, height: 42)
                                .background(.ultraThinMaterial, in: Circle())
                        }
                    }
                    .font(.headline)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .padding(AppTheme.Spacing.md)
                    Spacer()
                } }
            }
            .frame(height: 430)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))

            HStack(spacing: AppTheme.Spacing.sm) {
                planStat("预算", plan.budget ?? "待填写", "yensign.circle.fill")
                planStat("同行", plan.companions.map { "\($0) 人" } ?? "待填写", "person.2.fill")
                planStat("旅行风格", plan.style ?? "自由探索", "camera.fill")
            }
            if !plan.stops.isEmpty { TravelRouteMap(stops: plan.stops, height: 270) }
            Button("查看完整行程  →") { page = .day }
                .buttonStyle(QuantumPrimaryButtonStyle())
        }
    }

    @ViewBuilder
    private func travelImages(_ anchor: String) -> some View {
        let images = (NoteIllustrationPlacement.travelObject(content)?["illustrations"] as? [[String: String]] ?? []).filter { $0["anchor"] == anchor }
        ForEach(Array(images.enumerated()), id: \.offset) { _, item in
            if let path = item["path"] { NoteReadingImage(url: baseURL?.appendingPathComponent(path), caption: item["alt"] ?? "AI 插图") }
        }
        if let onIllustrate {
            Button("为这里配图", systemImage: "sparkles") { onIllustrate(anchor) }
                .buttonStyle(.bordered).frame(minHeight: 44)
        }
    }

    private var actualStops: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(page == .place ? "沿途地点" : "我的行程").font(.title2.bold())
            if plan.stops.isEmpty {
                Text("还没有行程地点，可从聊天规划旅行后保存，也可在编辑中填写行程。")
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
            ForEach(Array(plan.stops.enumerated()), id: \.offset) { index, stop in
                planStop("\(index + 1)", "mappin", stop.name, "行程地点", nil, isLast: index == plan.stops.count - 1)
                travelImages("stop:\(index)")
                Button("在地图中查看", systemImage: "map") {
                    MKMapItem(placemark: MKPlacemark(coordinate: stop.coordinate)).openInMaps()
                }.frame(minHeight: 44)
            }
        }
    }

    private var dailyPlan: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                Button { page = .overview } label: { Image(systemName: "chevron.left") }
                Spacer()
                Text("京都 5 日行").font(.headline)
                Spacer()
                Button { page = .check } label: { Image(systemName: "plus") }
            }
            HStack(spacing: 5) {
                ForEach(1...5, id: \.self) { day in
                    VStack(spacing: 3) {
                        Text("第\(day)天").font(.caption.weight(.semibold))
                        Text("4/\(11 + day)").font(AppTheme.Typography.micro)
                    }
                    .foregroundStyle(day == 1 ? AppTheme.Colors.quantumBlue : AppTheme.Colors.textSecondary)
                    .frame(maxWidth: .infinity, minHeight: 54)
                    .background(day == 1 ? AppTheme.Colors.mistSky : AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                }
            }
            HStack(alignment: .firstTextBaseline) {
                Text("第 1 天").font(.title2.bold())
                Text("抵达 · 初见京都").font(.headline)
                Spacer()
                Text("4月12日 周五").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
            }
            VStack(spacing: 0) {
                planStop("09:00", "airplane", "抵达关西机场 (KIX)", "机场 → 京都站 · 约 75 分钟", nil)
                planStop("11:30", "tram.fill", "京都站 → 酒店", "约 15 分钟", nil)
                planStop("13:00", "fork.knife", "锦市场", "美食 · 1–2 小时", "travel_kyoto_street")
                Button { page = .place } label: {
                    planStop("15:30", "building.columns.fill", "清水寺", "经典 · 2–3 小时", "travel_kyoto_bridge")
                }
                .buttonStyle(.plain)
                planStop("18:30", "fork.knife", "祇园 · 花见小路", "散步 · 1–2 小时", "travel_kyoto_moment", isLast: true)
            }
        }
    }

    private var placeDetail: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            ZStack(alignment: .topLeading) {
                Image("travel_kyoto_bridge").resizable().scaledToFill().frame(height: 240).clipped()
                Button { page = .day } label: {
                    Image(systemName: "chevron.left").frame(width: 40, height: 40).background(.ultraThinMaterial, in: Circle())
                }.padding(AppTheme.Spacing.sm)
            }
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg))
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("清水寺").font(AppTheme.Typography.screenTitle)
                    Text("きよみずでら · Kiyomizu-dera").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
                }
                Spacer()
                Image(systemName: "bookmark").frame(width: 42, height: 42).background(AppTheme.Colors.surfaceTint, in: Circle())
            }
            HStack { tag("寺庙"); tag("世界文化遗产"); tag("京都市") }
            Text("★ 4.7  （3.2 万条评价）").font(AppTheme.Typography.supporting).foregroundStyle(.orange)
            Text("建于 778 年，依山而建的木造舞台是京都的象征，四季皆美，尤以樱花与红叶闻名。")
                .font(AppTheme.Typography.body).foregroundStyle(AppTheme.Colors.textSecondary)
            Text("为什么值得去").font(.headline)
            Text("站在清水舞台，俯瞰京都的街巷与远山，感受千年古都的宁静与生命力。")
                .font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
            HStack(spacing: AppTheme.Spacing.sm) {
                tip("sun.max", "最佳时间", "清晨或傍晚")
                tip("camera", "拍照建议", "从舞台侧面取景")
            }
            HStack(spacing: AppTheme.Spacing.sm) {
                Button("在地图中查看", systemImage: "map") {}.buttonStyle(.bordered)
                Button("✦ 加入行程") { page = .check }.buttonStyle(.borderedProminent)
            }
        }
    }

    private var tripCheck: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack {
                Button("取消") { page = .overview }
                Spacer(); Text("行程检查").font(.headline); Spacer(); Button("完成") {}
            }
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: "checkmark.circle.fill").font(.largeTitle).foregroundStyle(AppTheme.Colors.statusCompleted)
                VStack(alignment: .leading) { Text("准备就绪！").font(.title3.bold()); Text("你的京都 5 日行已准备好").font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary) }
            }
            .padding(AppTheme.Spacing.md).frame(maxWidth: .infinity, alignment: .leading)
            .background(AppTheme.Colors.statusCompleted.opacity(0.08), in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            checkRow(true, "机票与住宿", "已安排")
            checkRow(true, "每日行程", "共 5 天 · 12 个地点")
            checkRow(true, "预算估算", "约 ¥8,000/人")
            checkRow(false, "旅行保险", "建议提前购买")
            checkRow(false, "部分景点需预约", "清水寺、二条城等")
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack { Text("备注").font(.headline); Spacer(); Button("编辑") {} }
                Text("想在清水寺看日落，\n也想体验一次正宗的怀石料理。")
                    .font(AppTheme.Typography.supporting).foregroundStyle(AppTheme.Colors.textSecondary)
                    .padding(AppTheme.Spacing.md).frame(maxWidth: .infinity, alignment: .leading)
                    .background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
            }
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Text("保存到 Quantum").font(.headline)
                Label(title.isEmpty ? "京都 5 日行" : title, systemImage: "map.fill")
                HStack { tag("旅行"); tag("日本"); tag("京都") }
                Toggle("设为公开", isOn: .constant(false))
            }
            .padding(AppTheme.Spacing.md).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.md))
            HStack(spacing: AppTheme.Spacing.sm) {
                export("doc", "导出 PDF", "图文行程单")
                export("link", "复制链接", "分享行程")
                export("calendar", "重新生成", "调整第 N 天")
            }
        }
    }

    private func planStat(_ title: String, _ value: String, _ icon: String) -> some View {
        VStack(spacing: 4) { Image(systemName: icon).foregroundStyle(AppTheme.Icons.interactive); Text(title).font(AppTheme.Typography.micro); Text(value).font(.caption.weight(.semibold)).lineLimit(1) }
            .frame(maxWidth: .infinity, minHeight: 72).background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
    }

    private func planStop(_ time: String, _ icon: String, _ title: String, _ detail: String, _ image: String?, isLast: Bool = false) -> some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            Text(time).font(.caption.weight(.semibold)).frame(width: 45, alignment: .leading)
            ZStack(alignment: .top) {
                if !isLast {
                    Rectangle()
                        .fill(AppTheme.Colors.quantumBlue.opacity(0.48))
                        .frame(width: 2, height: image == nil ? 82 : 190)
                        .offset(y: 32)
                }
                Image(systemName: icon)
                    .foregroundStyle(icon == "fork.knife" || icon == "building.columns.fill" ? AppTheme.Colors.emberOrange : AppTheme.Icons.interactive)
                    .frame(width: 38, height: 38)
                    .background(icon == "fork.knife" || icon == "building.columns.fill" ? AppTheme.Colors.mistRose : AppTheme.Colors.mistSky, in: Circle())
            }
            VStack(alignment: .leading, spacing: 5) {
                Text(title).font(AppTheme.Typography.body.weight(.semibold))
                Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
                if let image { Image(image).resizable().scaledToFill().frame(height: 94).clipped().clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm)) }
            }
            Spacer()
            VStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "mappin.circle.fill")
                    .foregroundStyle(AppTheme.Colors.quantumBlue)
                    .frame(width: 34, height: 34)
                    .background(AppTheme.Colors.mistSky.opacity(0.72), in: Circle())
                Image(systemName: "line.3.horizontal").foregroundStyle(AppTheme.Colors.textTertiary)
            }
        }
        .padding(.vertical, AppTheme.Spacing.sm)
    }

    private func tag(_ text: String) -> some View {
        Text(text).font(AppTheme.Typography.micro).padding(.horizontal, 9).frame(minHeight: 26).background(AppTheme.Colors.mistSky, in: Capsule())
    }

    private func tip(_ icon: String, _ title: String, _ detail: String) -> some View {
        HStack(alignment: .top, spacing: 8) { Image(systemName: icon).foregroundStyle(AppTheme.Icons.interactive); VStack(alignment: .leading) { Text(title).font(.caption.weight(.semibold)); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) } }
            .frame(maxWidth: .infinity, minHeight: 64, alignment: .topLeading).padding(AppTheme.Spacing.sm).background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
    }

    private func checkRow(_ checked: Bool, _ title: String, _ detail: String) -> some View {
        HStack { Image(systemName: checked ? "checkmark.circle.fill" : "circle.fill").foregroundStyle(checked ? AppTheme.Colors.statusCompleted : AppTheme.Colors.textTertiary); Text(title).font(.subheadline.weight(.semibold)); Spacer(); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }
    }

    private func export(_ icon: String, _ title: String, _ detail: String) -> some View {
        VStack(spacing: 5) { Image(systemName: icon).font(.title3).foregroundStyle(AppTheme.Icons.interactive); Text(title).font(.caption.weight(.semibold)); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }
            .frame(maxWidth: .infinity, minHeight: 88).background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
    }
}

#if DEBUG
struct V5PrototypePreviewHost: View {
    let pageID: String

    var body: some View {
        switch pageID {
        case let value where value.hasPrefix("v3/01-auth-"):
            LoginView(prototypePageID: value)
        case let value where value.hasPrefix("v3/02-chat-core-") || value.hasPrefix("v3/03-compose-import-voice-") || value.hasPrefix("v3/04-clarify-status-cards-") || value.hasPrefix("v3/05-rich-content-"):
            V3ChatPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v3/06-knowledge-home-"):
            V3KnowledgePrototypeHost(pageID: value)
        case let value where value.hasPrefix("v3/07-note-editor-reader-"):
            V3NotePrototypeHost(pageID: value)
        case let value where value.hasPrefix("v3/08-workflow-plan-"):
            V4WorkflowPrototypeHost(pageID: "v4/04-workflow-simple-plan-v4-\(value.suffix(3))")
        case let value where value.hasPrefix("v3/09-workflow-execution-"):
            V3WorkflowExecutionPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v3/10-topology-evaluation-"):
            V3TopologyEvaluationPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v3/11-settings-agent-memory-"):
            V3SettingsMemoryPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v3/12-subscription-governance-"):
            V3SubscriptionPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v3/13-bookshelf-reader-"):
            V3BooksPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v4/01-auth-errors-v4-"):
            LoginView(prototypePageID: value)
        case let value where value.hasPrefix("v4/02-chat-reasoning-voice-v4-"):
            V4ChatPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v4/03-clarify-merge-preview-v4-"):
            V4ClarifyMergePrototypeHost(pageID: value)
        case let value where value.hasPrefix("v4/04-workflow-simple-plan-v4-") || value.hasPrefix("v4/05-workflow-agent-usage-v4-"):
            V4WorkflowPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v4/06-travel-chat-to-workflow-v4-"):
            V4TravelPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v4/07-travel-plan-output-v4-"):
            travelPlanResult(value)
        case let value where value.hasPrefix("v4/08-reader-question-annotation-v4-"):
            ReaderAnnotationPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v4/09-agent-chat-creation-v4-"):
            V4AgentCreationPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v4/10-agent-knowledge-tools-crud-v4-"):
            V4AgentManagementPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v4/11-workflow-canvas-comfy-v4-"):
            V4CanvasPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v4/12-node-detail-eval-compare-v4-"):
            V4NodeEvaluationPrototypeHost(pageID: value)
        case let value where value.hasPrefix("v4/13-smart-research-ppt-v4-"):
            V4SmartResearchPrototypeHost(pageID: value)
        case "v5/01-startup-clean-v5-p01":
            LoginView(prototypePageID: pageID)
        case "v5/02-travel-note-layout-v5-p01":
            TravelSavePreviewHost()
        case "v5/02-travel-note-layout-v5-p02":
            travelReader(.cover)
        case "v5/02-travel-note-layout-v5-p03":
            travelReader(.day)
        case "v5/02-travel-note-layout-v5-p04":
            travelReader(.appendix)
        case "v5/03-photo-thought-auto-layout-v5-p01":
            TravelCameraPrototypeView()
        case "v5/03-photo-thought-auto-layout-v5-p02":
            momentComposer(.write)
        case "v5/03-photo-thought-auto-layout-v5-p03":
            momentComposer(.arranging)
        case "v5/03-photo-thought-auto-layout-v5-p04":
            momentComposer(.preview)
        default:
            ContentUnavailableView("未找到原型状态", systemImage: "rectangle.slash", description: Text(pageID))
        }
    }

    private func travelReader(_ page: TravelNoteReadingView.Page) -> some View {
        NavigationStack {
            ScrollView {
                TravelNoteReadingView(
                    title: "京都五日 · 春日行记",
                    content: "",
                    baseURL: FileManager.default.temporaryDirectory,
                    initialPage: page,
                    showsPagePicker: false
                )
                .padding(AppTheme.Metrics.contentGutter)
            }
            .background(AppTheme.Colors.background)
            .navigationTitle(page == .appendix ? "实用附录" : page == .day ? "京都五日 · 春日行记" : "")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func momentComposer(_ stage: TravelMomentComposer.Stage) -> some View {
        TravelMomentComposer(
            imagePath: "",
            baseURL: FileManager.default.temporaryDirectory,
            initialStage: stage,
            initialThought: "雨刚停，石板路反光很好看。抹茶有点苦，但巷子特别安静。",
            initialPlace: "祇园白川",
            onInsert: { _ in }
        )
    }

    private func travelPlanResult(_ value: String) -> some View {
        let page: TravelPlanResultView.Page = if value.hasSuffix("p02") {
            .day
        } else if value.hasSuffix("p03") {
            .place
        } else if value.hasSuffix("p04") {
            .check
        } else {
            .overview
        }
        return ScrollView {
            TravelPlanResultView(title: "京都 5 日行", content: "", initialPage: page)
                .padding(AppTheme.Metrics.contentGutter)
        }
        .background(AppTheme.Colors.background)
    }
}

private struct V3KnowledgePrototypeHost: View {
    let pageID: String

    var body: some View {
        if page == 1 { KnowledgeView() }
        else {
            NavigationStack {
                ZStack {
                    QuantumMistBackground()
                    ScrollView {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                            if page == 2 { search }
                            else if page == 3 { organizer }
                            else { trash }
                        }
                        .padding(AppTheme.Metrics.contentGutter)
                        .padding(.bottom, 44)
                    }
                }
                .navigationTitle(page == 2 ? "搜索" : (page == 3 ? "智能整理" : "回收站"))
                .navigationBarTitleDisplayMode(.inline)
            }
        }
    }

    @ViewBuilder private var search: some View {
        TextField("人工智能", text: .constant("人工智能")).textFieldStyle(.roundedBorder)
        ScrollView(.horizontal, showsIndicators: false) { HStack { chip("全部 24", true); chip("笔记 12"); chip("书籍 8"); chip("文件 6"); chip("对话 4") } }
        HStack { Menu("时间") {}; Menu("标签") {}; Menu("类型") {}; Menu("相关度") {} }.buttonStyle(.bordered)
        Text("找到 24 条结果").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
        ForEach([("AI 与人类的协作边界", "真正的智能，是让更多人发挥自己的创造力…", "树.fill", "9月12日"), ("生成式 AI 的机会与挑战", "技术的价值在于增强而非替代。", "building.columns.fill", "9月10日"), ("从 ChatGPT 到 AGI", "一些值得记录的观察…", "mountain.2.fill", "9月8日"), ("智能时代的学习方法", "保持好奇，持续提问。", "leaf.fill", "9月6日")], id: \.0) { item in
            HStack(spacing: 12) { RoundedRectangle(cornerRadius: 10).fill(AppTheme.Colors.mistSky).frame(width: 76, height: 76).overlay { Image(systemName: item.2).font(.title2).foregroundStyle(AppTheme.Icons.interactive) }; VStack(alignment: .leading, spacing: 5) { Text(item.0).font(AppTheme.Typography.label); Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary).lineLimit(2); Text(item.3).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary) }; Spacer(); Image(systemName: "circle") }.padding().quantumCard()
        }
        Text("已选择 1 项 · 置顶 · 移动 · 删除 · 更多").font(AppTheme.Typography.supporting).padding().frame(maxWidth: .infinity).background(.ultraThinMaterial, in: Capsule())
    }

    @ViewBuilder private var organizer: some View {
        Text("选择内容范围，让知识更有条理。").foregroundStyle(AppTheme.Colors.textSecondary)
        Text("选择内容类型").font(AppTheme.Typography.cardTitle)
        LazyVGrid(columns: [.init(.flexible()), .init(.flexible())], spacing: 10) {
            ForEach([("对话", "聊天记录", "bubble.left.fill", true), ("笔记", "我的笔记", "doc.text.fill", true), ("文件", "上传的文件", "folder.fill", false), ("书籍", "阅读记录", "books.vertical.fill", true)], id: \.0) { item in
                VStack(alignment: .leading, spacing: 8) { HStack { Image(systemName: item.2).foregroundStyle(AppTheme.Icons.interactive); Spacer(); Image(systemName: item.3 ? "checkmark.circle.fill" : "circle").foregroundStyle(item.3 ? AppTheme.Icons.interactive : AppTheme.Icons.tertiary) }; Text(item.0).font(AppTheme.Typography.label); Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary) }.padding().frame(minHeight: 110).quantumCard()
            }
        }
        Text("时间范围").font(AppTheme.Typography.cardTitle)
        Label("最近 3 个月 · 2024年6月1日–9月12日", systemImage: "calendar").padding().frame(maxWidth: .infinity, alignment: .leading).quantumCard()
        Text("预览（预计 48 条内容）").font(AppTheme.Typography.cardTitle)
        HStack { ForEach([("note.text", "笔记 18"), ("bubble.left", "对话 12"), ("folder", "文件 8"), ("books.vertical", "书籍 10")], id: \.1) { item in VStack { Image(systemName: item.0).font(.title2); Text(item.1).font(AppTheme.Typography.micro) }.frame(maxWidth: .infinity, minHeight: 86).background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: 10)) } }
        Button("开始整理", systemImage: "sparkles") {}.buttonStyle(QuantumPrimaryButtonStyle()).controlSize(.large).frame(maxWidth: .infinity)
    }

    @ViewBuilder private var trash: some View {
        HStack { Label("云同步失败", systemImage: "exclamationmark.circle.fill").foregroundStyle(AppTheme.Colors.statusError); Spacer(); Button("重试") {} }.padding().background(AppTheme.Colors.dangerSurface, in: RoundedRectangle(cornerRadius: 12))
        ScrollView(.horizontal, showsIndicators: false) { HStack { chip("全部 12", true); chip("已删除笔记 8"); chip("已删除文件 3"); chip("已删除书籍 1") } }
        ForEach([("夏日的思考", "笔记 · 320 字", "7 天后永久删除", "note.text"), ("项目资料整理", "文件 · PDF · 2.4 MB", "12 天后永久删除", "doc.fill"), ("被讨厌的勇气（摘录）", "笔记 · 1.2k 字", "25 天后永久删除", "quote.opening"), ("旅行灵感", "笔记 · 560 字", "28 天后永久删除", "airplane")], id: \.0) { item in
            HStack { Image(systemName: item.3).foregroundStyle(AppTheme.Icons.interactive).frame(width: 54, height: 54).background(AppTheme.Colors.selectionTint, in: RoundedRectangle(cornerRadius: 10)); VStack(alignment: .leading) { Text(item.0).font(AppTheme.Typography.label); Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary); Text(item.2).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.statusError) }; Spacer(); Image(systemName: "ellipsis") }.padding().quantumCard()
        }
        HStack { Button("恢复", systemImage: "arrow.uturn.backward") {}; Spacer(); Button("永久删除", systemImage: "trash", role: .destructive) {} }.padding().background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 14))
    }

    private var page: Int { Int(pageID.suffix(2)) ?? 1 }
    private func chip(_ title: String, _ selected: Bool = false) -> some View { Text(title).font(AppTheme.Typography.micro).foregroundStyle(selected ? AppTheme.Icons.interactive : AppTheme.Colors.textSecondary).padding(.horizontal, 13).padding(.vertical, 8).background(selected ? AppTheme.Colors.selectionTint : AppTheme.Colors.surfaceTint, in: Capsule()) }
}

private struct V3NotePrototypeHost: View {
    let pageID: String

    var body: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        if page == 1 { editor }
                        else if page == 2 { reader }
                        else if page == 3 { relations }
                        else { deleted }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                    .padding(.bottom, 42)
                }
            }
            .navigationTitle(page == 1 ? "已保存" : (page == 2 ? "春天的图书馆" : (page == 3 ? "关联内容" : "")))
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    @ViewBuilder private var editor: some View {
        Text("春天的图书馆").font(.system(size: 31, weight: .semibold, design: .serif))
        HStack { noteTag("阅读", AppTheme.Colors.mistMint); noteTag("随笔", AppTheme.Colors.mistRose); noteTag("大学生活", AppTheme.Colors.mistLilac); Image(systemName: "plus.circle") }
        Text("阳光透过落地窗，洒在木质桌面上。\n在图书馆的角落，时间好像变慢了。\n\n“阅读不是逃离生活，而是让生活更丰富。”\n\n## 今日收获\n☑ 读完《被讨厌的勇气》第一章\n☐ 整理课程笔记\n☐ 下周阅读计划")
            .font(AppTheme.Typography.body).lineSpacing(8).padding().frame(maxWidth: .infinity, minHeight: 380, alignment: .topLeading).background(AppTheme.Colors.cardBackground, in: RoundedRectangle(cornerRadius: 14))
        RoundedRectangle(cornerRadius: 14).fill(LinearGradient(colors: [AppTheme.Colors.mistMint, AppTheme.Colors.mistSky], startPoint: .topLeading, endPoint: .bottomTrailing)).frame(height: 230).overlay { Image(systemName: "books.vertical.fill").font(.system(size: 78)).foregroundStyle(AppTheme.Colors.statusCompleted.opacity(0.6)) }
        HStack { ForEach([("格式", "textformat"), ("图片", "photo"), ("文件", "paperclip"), ("链接", "link"), ("录音", "waveform")], id: \.0) { item in VStack { Image(systemName: item.1); Text(item.0).font(AppTheme.Typography.micro) }.frame(maxWidth: .infinity) } }
    }

    @ViewBuilder private var reader: some View {
        Text("春天的图书馆").font(.system(size: 32, weight: .semibold, design: .serif))
        Text("9月12日 · 由我创建 · 大学生活").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary)
        HStack { noteTag("阅读", AppTheme.Colors.mistMint); noteTag("随笔", AppTheme.Colors.mistRose); noteTag("大学生活", AppTheme.Colors.mistLilac) }
        RoundedRectangle(cornerRadius: 16).fill(LinearGradient(colors: [AppTheme.Colors.mistSky, AppTheme.Colors.mistMint], startPoint: .top, endPoint: .bottom)).frame(height: 300).overlay { Image(systemName: "books.vertical.fill").font(.system(size: 96)).foregroundStyle(AppTheme.Colors.quantumBlue.opacity(0.48)) }
        Text("阳光透过落地窗，洒在木质桌面上。在图书馆的角落，时间好像变慢了。").lineSpacing(7)
        Text("“ 阅读不是逃离生活，\n而是让生活更丰富。 ”").font(.system(size: 21, design: .serif)).foregroundStyle(AppTheme.Colors.textSecondary).padding().frame(maxWidth: .infinity).background(AppTheme.Colors.surfaceTint, in: RoundedRectangle(cornerRadius: 12))
        Text("今日收获").font(AppTheme.Typography.sectionTitle)
        Text("• 读完《被讨厌的勇气》第一章\n• 整理课程笔记\n• 下周阅读计划").lineSpacing(8)
    }

    @ViewBuilder private var relations: some View {
        Picker("", selection: .constant(0)) { Text("提及我的 (3)").tag(0); Text("我提及的 (5)").tag(1) }.pickerStyle(.segmented)
        Text("被以下内容提及").font(AppTheme.Typography.cardTitle)
        relation("高效阅读方法", "在《春天的图书馆》中提到的，阅读让生活更丰富。", "doc.text")
        relation("大学生活清单", "图书馆是我最喜欢的地方", "photo")
        relation("被讨厌的勇气", "关于自由与幸福的思考", "books.vertical")
        Text("我提及的内容").font(AppTheme.Typography.cardTitle)
        relation("图书馆", "地点 · 9月1日", "mappin")
        relation("阅读的意义", "笔记 · 8月28日", "doc")
        relation("大学生活", "笔记 · 8月20日", "doc")
    }

    @ViewBuilder private var deleted: some View {
        Spacer().frame(height: 70)
        Image(systemName: "trash.slash.fill").font(.system(size: 78)).foregroundStyle(AppTheme.Colors.textTertiary).frame(maxWidth: .infinity)
        Text("笔记已删除").font(.system(size: 30, weight: .semibold, design: .serif)).frame(maxWidth: .infinity)
        Text("这条笔记在 3 天前被删除。").foregroundStyle(AppTheme.Colors.textSecondary).frame(maxWidth: .infinity)
        Button("恢复笔记") {}.buttonStyle(QuantumPrimaryButtonStyle()).controlSize(.large).frame(maxWidth: .infinity)
        Button("永久删除", role: .destructive) {}.frame(maxWidth: .infinity)
        VStack(spacing: 0) { Label("置顶笔记", systemImage: "pin").padding().frame(maxWidth: .infinity, alignment: .leading); Divider(); Label("分享", systemImage: "square.and.arrow.up").padding().frame(maxWidth: .infinity, alignment: .leading); Divider(); Label("删除", systemImage: "trash").foregroundStyle(AppTheme.Colors.statusError).padding().frame(maxWidth: .infinity, alignment: .leading) }.quantumCard()
    }

    private var page: Int { Int(pageID.suffix(2)) ?? 1 }
    private func noteTag(_ text: String, _ color: Color) -> some View { Text("# \(text)").font(AppTheme.Typography.micro).padding(.horizontal, 10).padding(.vertical, 7).background(color, in: Capsule()) }
    private func relation(_ title: String, _ detail: String, _ icon: String) -> some View { HStack { Image(systemName: icon).foregroundStyle(AppTheme.Icons.interactive).frame(width: 50, height: 50).background(AppTheme.Colors.selectionTint, in: RoundedRectangle(cornerRadius: 10)); VStack(alignment: .leading) { Text(title).font(AppTheme.Typography.label); Text(detail).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary).lineLimit(2) }; Spacer(); Image(systemName: "ellipsis") }.padding().quantumCard() }
}

private struct V3BooksPrototypeHost: View {
    let pageID: String

    var body: some View {
        NavigationStack {
            ZStack {
                QuantumMistBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        if page == 1 { shelf }
                        else if page == 2 { search }
                        else if page == 3 { detail }
                        else { reading }
                    }
                    .padding(AppTheme.Metrics.contentGutter)
                    .padding(.bottom, 50)
                }
            }
            .navigationTitle(page == 1 ? "书架" : (page == 2 ? "搜索" : (page == 3 ? "" : "我与地坛")))
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    @ViewBuilder private var shelf: some View {
        Picker("", selection: .constant(0)) { Text("在读").tag(0); Text("收藏").tag(1); Text("已读").tag(2) }.pickerStyle(.segmented)
        HStack(alignment: .top, spacing: 20) { bookCover("我与\n地坛", "史铁生", .green, 146); bookCover("人类\n简史", "Yuval Noah Harari", .brown, 146) }
        Text("为你推荐").font(AppTheme.Typography.sectionTitle)
        HStack(alignment: .top, spacing: 12) { bookCover("雪国", "川端康成", .blue, 92); bookCover("被讨厌的\n勇气", "岸见一郎", .cyan, 92); bookCover("Atomic\nHabits", "James Clear", .orange, 92); bookCover("明亮的\n世界", "", .teal, 92) }
    }

    @ViewBuilder private var search: some View {
        TextField("搜索书名、作者或关键词", text: .constant("")).textFieldStyle(.roundedBorder)
        HStack { Text("全部"); Text("图书"); Text("笔记"); Text("文章"); Spacer(); Label("筛选", systemImage: "line.3.horizontal.decrease") }.font(AppTheme.Typography.supporting)
        ForEach([("雪国", "川端康成", "文学 · 经典 · 日本", "8.9"), ("我与地坛", "史铁生", "文学 · 散文 · 成长", "9.1"), ("人类简史", "尤瓦尔·赫拉利", "历史 · 社科 · 人文", "9.2"), ("被讨厌的勇气", "岸见一郎", "心理 · 成长 · 哲学", "8.8"), ("原子习惯", "James Clear", "自我提升 · 习惯", "8.7")], id: \.0) { item in HStack { bookCover(item.0, item.1, .green, 74); VStack(alignment: .leading, spacing: 6) { Text(item.0).font(AppTheme.Typography.label); Text(item.1).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary); Text(item.2).font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textTertiary); Text("★ \(item.3)").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.statusWarning) }; Spacer(); Image(systemName: "heart") }.padding(.vertical, 4) }
    }

    @ViewBuilder private var detail: some View {
        HStack(alignment: .top, spacing: 18) { bookCover("我与\n地坛", "史铁生", .green, 132); VStack(alignment: .leading, spacing: 9) { Text("我与地坛").font(.system(size: 30, weight: .semibold, design: .serif)); Text("史铁生"); HStack { Text("文学"); Text("散文"); Text("成长") }.font(AppTheme.Typography.micro); Text("★ 9.1（28.7万人）").foregroundStyle(AppTheme.Colors.statusWarning); Text("出版社　人民文学出版社\n出版时间　2002年4月\n字数　12.5万字").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary).lineSpacing(6) } }
        HStack { Button("加入书架") {}.buttonStyle(.bordered); Button("继续阅读") {}.buttonStyle(QuantumPrimaryButtonStyle()) }
        Text("简介").font(AppTheme.Typography.cardTitle); Text("在寂静的地坛里，史铁生用温柔而坚韧的文字，记录生命的沉思与希望。").lineSpacing(7)
        HStack { Text("目录").font(AppTheme.Typography.cardTitle); Spacer(); Text("共 16 章").font(AppTheme.Typography.micro) }
        ForEach(["1　我与地坛", "2　记忆与城市", "3　病隙碎笔", "4　秋天的怀念"], id: \.self) { Label($0, systemImage: "chevron.right").labelStyle(V3TrailingLabelStyle()).padding(.vertical, 6); Divider() }
        Button("问问这本书", systemImage: "bubble.left") {}.frame(maxWidth: .infinity).buttonStyle(.bordered)
    }

    @ViewBuilder private var reading: some View {
        Text("第 3 章　病隙碎笔").font(AppTheme.Typography.micro).foregroundStyle(AppTheme.Colors.textSecondary).frame(maxWidth: .infinity)
        Text("秋天的怀念").font(.system(size: 34, weight: .semibold, design: .serif)).padding(.vertical, 18)
        Text("母亲喜欢花，可自从我的腿瘫痪后，她侍弄的那些花都死了。\n\n那年秋天，母亲推着我去地坛。阳光很好，树叶在风里沙沙地响。她忽然对我说：“北海的菊花开了，我们去看看吧。”\n\n我摇摇头。她沉默了一会儿，又说：“不，我推你去。”\n\n那天的阳光，至今仍在我心里。")
            .font(.system(size: 21, design: .serif)).lineSpacing(12)
        HStack { Circle().fill(.yellow).frame(width: 22, height: 22); Circle().fill(.green).frame(width: 22, height: 22); Circle().fill(.purple).frame(width: 22, height: 22); Circle().fill(.blue).frame(width: 22, height: 22); Spacer(); Label("笔记", systemImage: "note.text"); Label("保存", systemImage: "clock") }.font(AppTheme.Typography.micro).padding().background(.ultraThinMaterial, in: Capsule())
        ProgressView(value: 0.28).tint(AppTheme.Colors.textPrimary); HStack { Text("68 / 245"); Spacer(); Text("28%") }.font(AppTheme.Typography.micro)
        HStack { ForEach(["textformat.size", "circle.lefthalf.filled", "list.bullet.rectangle", "square.and.arrow.up"], id: \.self) { Image(systemName: $0).font(.title3).frame(maxWidth: .infinity) } }
    }

    private var page: Int { Int(pageID.suffix(2)) ?? 1 }
    private func bookCover(_ title: String, _ author: String, _ color: Color, _ width: CGFloat) -> some View { VStack(alignment: .leading, spacing: 5) { ZStack { LinearGradient(colors: [color.opacity(0.16), color.opacity(0.38)], startPoint: .top, endPoint: .bottom); VStack { Text(title).font(.system(size: width > 100 ? 25 : 15, weight: .semibold, design: .serif)).multilineTextAlignment(.center); Spacer(); Image(systemName: "tree.fill").foregroundStyle(color); Text(author).font(.system(size: 8)) }.padding(10) }.frame(width: width, height: width * 1.42).clipShape(RoundedRectangle(cornerRadius: 6)); if width > 100 { Text("已读 68%").font(AppTheme.Typography.micro) } } }
}

private struct V3TrailingLabelStyle: LabelStyle { func makeBody(configuration: Configuration) -> some View { HStack { configuration.title; Spacer(); configuration.icon } } }

private struct TravelSavePreviewHost: View {
    @State private var showingSave = false

    var body: some View {
        NavigationStack {
            VStack(spacing: AppTheme.Spacing.lg) {
                TravelRouteMap()
                Text("京都五日行程")
                    .font(AppTheme.Typography.screenTitle)
                Text("4月12日–4月16日")
                    .font(AppTheme.Typography.supporting)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                Spacer()
            }
            .padding(AppTheme.Metrics.contentGutter)
            .background(AppTheme.Colors.background)
            .task { showingSave = true }
            .sheet(isPresented: $showingSave) {
                TravelNoteSaveSheet(title: "京都五日 · 春日行记", content: "") { _, _ in }
                    .interactiveDismissDisabled()
            }
        }
    }
}

private struct TravelCameraPrototypeView: View {
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                Image("travel_kyoto_camera")
                    .resizable()
                    .scaledToFill()
                    .frame(width: geometry.size.width, height: geometry.size.height)
                    .clipped()
                LinearGradient(colors: [.black.opacity(0.26), .clear, .black.opacity(0.62)], startPoint: .top, endPoint: .bottom)

                VStack {
                    HStack {
                        cameraCircle("xmark")
                        Spacer()
                        cameraCircle("bolt.slash.fill")
                        cameraCircle("camera.filters")
                    }
                    .padding(.horizontal, AppTheme.Spacing.lg)
                    .padding(.top, max(12, geometry.safeAreaInsets.top + 6))
                    Spacer()
                    HStack(alignment: .center) {
                        Image("travel_kyoto_camera")
                            .resizable()
                            .scaledToFill()
                            .frame(width: 52, height: 52)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .overlay { RoundedRectangle(cornerRadius: 8).stroke(.white, lineWidth: 1) }
                        Spacer()
                        Circle()
                            .fill(.white)
                            .frame(width: 74, height: 74)
                            .overlay { Circle().stroke(.white.opacity(0.65), lineWidth: 5).padding(-7) }
                        Spacer()
                        cameraCircle("arrow.triangle.2.circlepath.camera.fill")
                    }
                    .padding(.horizontal, 32)
                    HStack(spacing: 34) {
                        Text("照片").foregroundStyle(.yellow)
                        Text("视频").foregroundStyle(.white)
                    }
                    .font(.subheadline.weight(.semibold))
                    .padding(.top, AppTheme.Spacing.lg)
                    Text("只写几句")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .frame(maxWidth: .infinity, minHeight: 58)
                        .background(.white)
                        .clipShape(UnevenRoundedRectangle(topLeadingRadius: 24, topTrailingRadius: 24))
                        .padding(.top, AppTheme.Spacing.lg)
                }
            }
        }
        .ignoresSafeArea()
    }

    private func cameraCircle(_ icon: String) -> some View {
        Image(systemName: icon)
            .font(.headline)
            .foregroundStyle(.white)
            .frame(width: 40, height: 40)
            .background(.black.opacity(0.45), in: Circle())
    }
}
#endif

private enum NoteReadingBlock: Identifiable, Sendable {
    case heading(level: Int, text: String, id: UUID = UUID())
    case paragraph(String, id: UUID = UUID())
    case list([String], ordered: Bool, id: UUID = UUID())
    case quote(String, id: UUID = UUID())
    case callout(type: String, title: String, text: String, id: UUID = UUID())
    case code(String, id: UUID = UUID())
    case chart(ChartBlock, id: UUID = UUID())
    case image(path: String, caption: String, id: UUID = UUID())
    case divider(id: UUID = UUID())

    var id: UUID {
        switch self {
        case .heading(_, _, let id), .paragraph(_, let id), .list(_, _, let id), .quote(_, let id),
             .callout(_, _, _, let id), .code(_, let id), .chart(_, let id), .image(_, _, let id), .divider(let id): return id
        }
    }

    @ViewBuilder
    func view(
        baseURL: URL?,
        annotations: [NoteInlineAnnotation],
        onSelection: @escaping (String) -> Void,
        onAskSelection: @escaping (String) -> Void,
        onHighlightSelection: @escaping (String) -> Void,
        onAnnotateSelection: @escaping (String) -> Void,
        onAnnotationTap: @escaping (NoteInlineAnnotation) -> Void
    ) -> some View {
        switch self {
        case .heading(let level, let text, _):
            if level <= 2 {
                VStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: "leaf.fill")
                        .font(.caption)
                        .foregroundStyle(AppTheme.Colors.statusCompleted.opacity(0.72))
                    Text(inlineMarkdown(text))
                        .font(level == 1 ? .system(size: 28, weight: .bold, design: .serif) : .system(size: 23, weight: .semibold, design: .serif))
                        .multilineTextAlignment(.center)
                    RoundedRectangle(cornerRadius: 1)
                        .fill(AppTheme.Colors.border.opacity(0.72))
                        .frame(width: 56, height: 2)
                }
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, AppTheme.Spacing.md)
            } else {
                Text(inlineMarkdown(text))
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
            }
        case .paragraph(let text, _):
            annotatedText(
                text,
                annotations: annotations,
                onSelection: onSelection,
                onAskSelection: onAskSelection,
                onHighlightSelection: onHighlightSelection,
                onAnnotateSelection: onAnnotateSelection,
                onAnnotationTap: onAnnotationTap
            )
        case .list(let items, let ordered, _):
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                        if item.hasPrefix("[ ] ") || item.hasPrefix("[x] ") {
                            Image(systemName: item.hasPrefix("[x]") ? "checkmark.square.fill" : "square")
                                .foregroundStyle(AppTheme.Icons.interactive)
                        } else {
                            Text(ordered ? "\(index + 1)." : "•")
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                                .frame(width: 22, alignment: .trailing)
                        }
                        annotatedText(
                            item.replacingOccurrences(of: #"^\[[ xX]\]\s*"#, with: "", options: .regularExpression),
                            annotations: annotations,
                            onSelection: onSelection,
                            onAskSelection: onAskSelection,
                            onHighlightSelection: onHighlightSelection,
                            onAnnotateSelection: onAnnotateSelection,
                            onAnnotationTap: onAnnotationTap
                        )
                    }
                }
            }
        case .quote(let text, _):
            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                Rectangle()
                    .fill(AppTheme.Colors.border)
                    .frame(width: 3)
                SelectableReadingText(
                    markdown: text,
                    textColor: .secondaryLabel,
                    highlights: annotations.map { .init(id: $0.id, quote: $0.quote) },
                    onAnnotationTap: { id in
                        if let annotation = annotations.first(where: { $0.id == id }) { onAnnotationTap(annotation) }
                    },
                    onAskSelection: onAskSelection,
                    onHighlightSelection: onHighlightSelection,
                    onAnnotateSelection: onAnnotateSelection,
                    onSelection: onSelection
                )
            }
        case .callout(let type, let title, let text, _):
            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                Image(systemName: type == "abstract" ? "rectangle.on.rectangle" : "lightbulb")
                    .foregroundStyle(AppTheme.Icons.intelligence)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text(title)
                        .font(.subheadline.weight(.semibold))
                    SelectableReadingText(
                        markdown: text,
                        highlights: annotations.map { .init(id: $0.id, quote: $0.quote) },
                        onAnnotationTap: { id in
                            if let annotation = annotations.first(where: { $0.id == id }) { onAnnotationTap(annotation) }
                        },
                        onAskSelection: onAskSelection,
                        onHighlightSelection: onHighlightSelection,
                        onAnnotateSelection: onAnnotateSelection,
                        onSelection: onSelection
                    )
                }
                .foregroundStyle(AppTheme.Colors.textPrimary)
            }
            .padding(AppTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(type == "abstract" ? AppTheme.Colors.mistLilac.opacity(0.65) : AppTheme.Colors.mistMint.opacity(0.65))
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
        case .code(let code, _):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code)
                    .font(.system(.body, design: .monospaced))
                    .foregroundStyle(AppTheme.Colors.codeSyntaxForeground)
                    .padding(AppTheme.Spacing.md)
            }
            .background(AppTheme.Colors.codeBlockBackground)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm, style: .continuous))
        case .chart(let chart, _):
            ChartCard(block: chart)
        case .image(let path, let caption, _):
            NoteReadingImage(url: baseURL?.appendingPathComponent(path), caption: caption)
        case .divider:
            Divider()
        }
    }

    private func annotatedText(
        _ text: String,
        annotations: [NoteInlineAnnotation],
        onSelection: @escaping (String) -> Void,
        onAskSelection: @escaping (String) -> Void,
        onHighlightSelection: @escaping (String) -> Void,
        onAnnotateSelection: @escaping (String) -> Void,
        onAnnotationTap: @escaping (NoteInlineAnnotation) -> Void
    ) -> some View {
        let matches = annotations.filter { !$0.quote.isEmpty && text.localizedStandardContains($0.quote) }
        return HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            if !matches.isEmpty {
                RoundedRectangle(cornerRadius: 2)
                    .fill(AppTheme.Colors.quantumBlue)
                    .frame(width: 3)
                    .frame(minHeight: 44, maxHeight: .infinity)
            }
            SelectableReadingText(
                markdown: text,
                highlights: annotations.map { .init(id: $0.id, quote: $0.quote) },
                onAnnotationTap: { id in
                    if let annotation = annotations.first(where: { $0.id == id }) { onAnnotationTap(annotation) }
                },
                onAskSelection: onAskSelection,
                onHighlightSelection: onHighlightSelection,
                onAnnotateSelection: onAnnotateSelection,
                onSelection: onSelection
            )
            .fixedSize(horizontal: false, vertical: true)
            if let annotation = matches.first {
                Button { onAnnotationTap(annotation) } label: {
                    ZStack(alignment: .topTrailing) {
                        Image(systemName: "bubble.left.fill")
                            .font(.title3)
                            .foregroundStyle(AppTheme.Colors.quantumBlue)
                        Text("\(matches.count)")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundStyle(.white)
                            .offset(x: 2, y: 2)
                    }
                    .frame(width: 30, height: 30)
                }
                .buttonStyle(SoftButtonStyle())
                .accessibilityLabel("查看这处批注，共 \(matches.count) 条")
            }
        }
    }

    private func inlineMarkdown(_ text: String) -> AttributedString {
        let wikilinks = text.replacingOccurrences(
            of: #"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]"#,
            with: "$2$1",
            options: .regularExpression
        )
        return (try? AttributedString(markdown: wikilinks)) ?? AttributedString(wikilinks)
    }

    static func parse(_ source: String) -> [NoteReadingBlock] {
        let lines = source.components(separatedBy: .newlines)
        var result: [NoteReadingBlock] = []
        var paragraph: [String] = []
        var list: [String] = []
        var ordered = false
        var code: [String] = []
        var codeLanguage: String?
        var inCode = false
        var index = 0

        func flushParagraph() {
            if !paragraph.isEmpty {
                result.append(.paragraph(paragraph.joined(separator: "\n")))
                paragraph.removeAll()
            }
        }
        func flushList() {
            if !list.isEmpty {
                result.append(.list(list, ordered: ordered))
                list.removeAll()
            }
        }

        while index < lines.count {
            let raw = lines[index]
            let line = raw.trimmingCharacters(in: .whitespaces)

            if inCode {
                if line.hasPrefix("```") {
                    let source = code.joined(separator: "\n")
                    if case .chart(let chart)? = MarkdownBlockParser.chart(language: codeLanguage, code: source) {
                        result.append(.chart(chart))
                    } else {
                        result.append(.code(source))
                    }
                    code.removeAll()
                    codeLanguage = nil
                    inCode = false
                } else {
                    code.append(raw)
                }
                index += 1
                continue
            }

            if line.hasPrefix("```") {
                flushParagraph(); flushList()
                let language = line.drop(while: { $0 == "`" }).trimmingCharacters(in: .whitespaces)
                codeLanguage = language.isEmpty ? nil : language
                inCode = true; index += 1; continue
            }
            if line.hasPrefix("![["), line.hasSuffix("]]"), line.count > 5 {
                flushParagraph(); flushList()
                result.append(.image(path: String(line.dropFirst(3).dropLast(2)), caption: "旅行照片"))
                index += 1; continue
            }
            if let match = line.wholeMatch(of: /!\[([^\]]*)\]\(([^\)]+)\)/) {
                flushParagraph(); flushList()
                result.append(.image(path: String(match.2), caption: String(match.1)))
                index += 1; continue
            }
            if line == "---" || line == "***" {
                flushParagraph(); flushList(); result.append(.divider()); index += 1; continue
            }
            if line.hasPrefix("#") {
                flushParagraph(); flushList()
                let level = min(line.prefix(while: { $0 == "#" }).count, 3)
                result.append(.heading(level: level, text: line.dropFirst(level).trimmingCharacters(in: .whitespaces)))
                index += 1; continue
            }
            if line.hasPrefix("> [!") {
                flushParagraph(); flushList()
                let close = line.firstIndex(of: "]")
                let type = close.map { String(line[line.index(line.startIndex, offsetBy: 4)..<$0]) } ?? "note"
                let title = close.map { String(line[line.index(after: $0)...]).trimmingCharacters(in: .whitespaces) } ?? "提示"
                var content: [String] = []
                var cursor = index + 1
                while cursor < lines.count, lines[cursor].trimmingCharacters(in: .whitespaces).hasPrefix(">") {
                    content.append(String(lines[cursor].trimmingCharacters(in: .whitespaces).dropFirst()).trimmingCharacters(in: .whitespaces))
                    cursor += 1
                }
                result.append(.callout(type: type, title: title.isEmpty ? type.capitalized : title, text: content.joined(separator: "\n")))
                index = cursor; continue
            }
            if line.hasPrefix(">") {
                flushParagraph(); flushList()
                result.append(.quote(String(line.dropFirst()).trimmingCharacters(in: .whitespaces)))
                index += 1; continue
            }
            if line.hasPrefix("- ") || line.hasPrefix("* ") {
                flushParagraph()
                if list.isEmpty { ordered = false }
                list.append(String(line.dropFirst(2)))
                index += 1; continue
            }
            if let match = line.range(of: #"^\d+[.)]\s+"#, options: .regularExpression) {
                flushParagraph()
                if list.isEmpty { ordered = true }
                list.append(String(line[match.upperBound...]))
                index += 1; continue
            }
            if line.isEmpty {
                flushParagraph(); flushList(); index += 1; continue
            }

            flushList()
            paragraph.append(raw)
            index += 1
        }

        if inCode {
            let source = code.joined(separator: "\n")
            if case .chart(let chart)? = MarkdownBlockParser.chart(language: codeLanguage, code: source) {
                result.append(.chart(chart))
            } else {
                result.append(.code(source))
            }
        }
        flushParagraph(); flushList()
        return result
    }
}

struct NoteReadingImage: View {
    let url: URL?
    let caption: String
    @State private var image: UIImage?
    @State private var loadError = false
    @State private var retryCount = 0

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Group {
                if let image {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                } else {
                    ZStack {
                        AppTheme.Colors.secondaryBackground
                        if loadError {
                            Button("图片加载失败，重试") { retryCount += 1 }
                        } else { ProgressView() }
                    }
                }
            }
            .frame(maxWidth: .infinity, minHeight: 220, maxHeight: 420)
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.lg, style: .continuous))
            .clipped()
            if !caption.isEmpty {
                Text(caption)
                    .font(AppTheme.Typography.micro)
                    .foregroundStyle(AppTheme.Colors.textTertiary)
            }
        }
        .task(id: "\(url?.path ?? "")-\(retryCount)") {
            guard let url else { return }
            loadError = false
            let account = KnowledgeNoteStore.shared.accountFingerprint
            if !FileManager.default.fileExists(atPath: url.path), let asset = NoteIllustrationPlacement.asset(from: url.lastPathComponent) {
                do { _ = try await KnowledgeNoteStore.shared.illustrationImage(asset, account: account) }
                catch { loadError = true; return }
            }
            let data = await Task.detached(priority: .utility) {
                guard let raw = try? Data(contentsOf: url) else { return nil as Data? }
                return InboxFileManager.shared.downsampleImage(data: raw, maxDimension: 1_600, compressionQuality: 0.84)
            }.value
            guard !Task.isCancelled, account == KnowledgeNoteStore.shared.accountFingerprint else { return }
            guard let data else { loadError = true; return }
            image = UIImage(data: data)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(caption.isEmpty ? "笔记图片" : caption)
    }
}

#Preview("Knowledge Notes") {
    KnowledgeView()
        .environmentObject(AppState())
        .environmentObject(APIClient.shared)
}

private struct NoteIllustrationSheet: View {
    let noteID: String
    let anchor: String
    @ObservedObject private var store = KnowledgeNoteStore.shared
    @Environment(\.dismiss) private var dismiss
    @State private var brief = ""
    private var job: NoteIllustrationJob? { store.illustrationJobs[noteID] }
    private var running: Bool { store.illustrationIsRunning(noteID) }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Label("为这里配一张图", systemImage: "sparkles")
                        .font(.title2.bold())
                    Text(anchor.hasPrefix("stop:") ? "插在选中的行程地点之后" : anchor == "overview" ? "旅行概览插图" : "插在这段之后：\(anchor.prefix(100))")
                        .font(.subheadline).foregroundStyle(AppTheme.Colors.textSecondary)
                    VStack(alignment: .leading, spacing: 8) {
                        Text("你想画什么？").font(.headline)
                        TextField("例如：宿舍夜读的场景，温暖一点", text: $brief, axis: .vertical)
                            .lineLimit(3...6).padding(16)
                            .background(.white, in: RoundedRectangle(cornerRadius: 18))
                            .accessibilityIdentifier("note-illustration-brief")
                        Text("结合前后文与整篇主旨，延续清新插画风格。")
                            .font(.footnote).foregroundStyle(AppTheme.Colors.textSecondary)
                    }
                    if let job {
                        Label(job.message, systemImage: running ? "hourglass" : "sparkles")
                            .font(.subheadline)
                        ForEach(job.response?.assets ?? []) { asset in
                            NoteReadingImage(url: store.vaultDirectory.appendingPathComponent(asset.relativePath), caption: asset.alt)
                        }
                        if !job.applied, !(job.response?.assets.isEmpty ?? true) {
                            Button("插入笔记") {
                                if store.applyIllustrations(id: noteID) { dismiss() }
                            }
                            .buttonStyle(.borderedProminent)
                            if store.note(id: noteID)?.body != job.originalBody && !anchor.isEmpty {
                                Button("改为插入当前选定位置") {
                                    if store.relocateIllustrations(id: noteID, anchor: anchor) { dismiss() }
                                }.frame(minHeight: 44)
                            }
                        }
                        if running {
                            Button("停止生成", role: .destructive) { store.cancelIllustrations(id: noteID) }.frame(minHeight: 44)
                        } else if job.response?.status == "failed" || !(job.response?.failedIndices.isEmpty ?? true) || job.response == nil {
                            Button("重试配图") { store.startIllustrations(id: noteID, mode: job.request.mode, retry: true) }.frame(minHeight: 44)
                        }
                    }
                    Button(job?.response?.assets.isEmpty == false ? "按新要求重新生成" : "生成插图", systemImage: "sparkles") {
                        store.startIllustrations(id: noteID, mode: "manual", anchor: anchor, brief: brief)
                    }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    .disabled(brief.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || running || anchor.isEmpty)
                    .accessibilityIdentifier("note-illustration-generate")
                }
                .padding(20)
            }
            .background(AppTheme.Colors.background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("关闭") { dismiss() } } }
        }
        .onAppear { if brief.isEmpty { brief = job?.request.brief ?? "" } }
        .tint(AppTheme.Colors.primary)
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }
}
