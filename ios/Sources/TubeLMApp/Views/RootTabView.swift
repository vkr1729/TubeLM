#if canImport(SwiftUI)
import SwiftUI
import TubeLMCore

private enum SyncDefaults {
    static let endpointKey = "tubelm.syncEndpoint"
    static let keyKey = "tubelm.syncKey"
    static let defaultEndpoint = "https://tubelm-sync.vkr1729.workers.dev"
}

public struct RootTabView: View {
    @StateObject private var player = AudioPlayerManager.shared
    @Environment(\.scenePhase) private var scenePhase
    @State private var selectedTab: Int = 0
    @State private var feed: DigestFeed?
    @State private var readIDs: Set<String> = []
    @State private var bookmarks: [FeedItem] = []
    @State private var queue: [QueueItem] = []
    @State private var isShowingPlayerSheet: Bool = false
    @State private var isShowingSyncSettings: Bool = false
    @State private var syncToastText: String? = nil
    @State private var toastTask: Task<Void, Never>? = nil
    @State private var isRefreshing: Bool = false
    @State private var syncTask: Task<Void, Never>? = nil
    @State private var syncClient: CloudflareSyncClient

    private let store = ContentStore()

    public init() {
        let endpoint = UserDefaults.standard.string(forKey: SyncDefaults.endpointKey)
            ?? SyncDefaults.defaultEndpoint
        let key = UserDefaults.standard.string(forKey: SyncDefaults.keyKey) ?? ""
        let url = URL(string: endpoint) ?? URL(string: SyncDefaults.defaultEndpoint)!
        _syncClient = State(initialValue: CloudflareSyncClient(baseURL: url, syncKey: key))
    }

    public var body: some View {
        ZStack(alignment: .bottom) {
            // Main Navigation & Content
            NavigationStack {
                VStack(spacing: 0) {
                    Group {
                        switch selectedTab {
                        case 0:
                            BriefingView(
                                items: feed?.top20.items ?? [],
                                readIDs: readIDs,
                                onMarkRead: markRead,
                                onPlayAudio: playItemAudio,
                                onEnqueue: enqueueFeedItem,
                                onToggleBookmark: toggleBookmark,
                                isBookmarked: { id in bookmarks.contains(where: { $0.id == id }) }
                            )
                        case 1:
                            ChannelsView(
                                channels: feed?.channels ?? [],
                                readIDs: readIDs,
                                onToggleRead: toggleRead,
                                onPlayChannel: playChannelAudio,
                                onEnqueueItem: enqueueQueueItem,
                                onToggleBookmark: toggleBookmark
                            )
                        case 2:
                            BookmarksView(
                                bookmarks: bookmarks,
                                onRemoveBookmark: removeBookmark
                            )
                        default:
                            EmptyView()
                        }
                    }
                }
                .navigationTitle(currentTitle)
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button(action: { isShowingSyncSettings = true }) {
                            Image(systemName: "arrow.triangle.2.circlepath")
                        }
                        .accessibilityLabel("Sync settings")
                    }
                }
                #else
                .toolbar {
                    ToolbarItem(placement: .automatic) {
                        Button(action: { isShowingSyncSettings = true }) {
                            Image(systemName: "arrow.triangle.2.circlepath")
                        }
                        .accessibilityLabel("Sync settings")
                    }
                }
                #endif
            }

            // Floating Sticky Mini-Player
            VStack(spacing: 0) {
                // Subtle Sync Toast
                if let toast = syncToastText {
                    Text(toast)
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 5)
                        .background(AppTheme.accent)
                        .clipShape(Capsule())
                        .shadow(radius: 4)
                        .transition(.opacity.combined(with: .move(edge: .top)))
                        .padding(.bottom, 8)
                }

                // Mini-Player Bar
                HStack(spacing: 12) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 10)
                            .fill(AppTheme.accentBadge)
                            .frame(width: 36, height: 36)
                        Text("TL")
                            .font(.system(size: 13, weight: .black))
                            .foregroundColor(AppTheme.accentBadgeText)
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text(player.currentTitle)
                            .font(.system(size: 13, weight: .bold))
                            .lineLimit(1)
                        HStack(spacing: 6) {
                            Text(player.currentSource)
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                            if !queue.isEmpty {
                                Text("\(queue.count) in Queue")
                                    .font(.system(size: 9, weight: .bold))
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 1)
                                    .background(AppTheme.accent.opacity(0.12))
                                    .foregroundColor(AppTheme.accent)
                                    .clipShape(Capsule())
                            }
                        }
                    }

                    Spacer()

                    Button(action: { player.togglePlay() }) {
                        Image(systemName: player.isPlaying ? "pause.fill" : "play.fill")
                            .font(.system(size: 14))
                            .frame(width: 36, height: 36)
                            .background(AppTheme.secondarySystemBackground)
                            .clipShape(Circle())
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(.ultraThinMaterial)
                .cornerRadius(16)
                .shadow(color: Color.black.opacity(0.12), radius: 10, x: 0, y: 4)
                .padding(.horizontal, 12)
                .padding(.bottom, 8)
                .onTapGesture {
                    isShowingPlayerSheet = true
                }

                // Native Tab Bar
                HStack {
                    tabButton(index: 0, title: "Briefing", icon: "newspaper.fill")
                    Spacer()
                    tabButton(index: 1, title: "Channels", icon: "square.grid.2x2.fill")
                    Spacer()
                    tabButton(index: 2, title: "Bookmarks", icon: "bookmark.fill")
                }
                .padding(.horizontal, 32)
                .padding(.vertical, 10)
                .background(AppTheme.systemBackground)
                .overlay(Rectangle().frame(height: 0.5).foregroundColor(AppTheme.separator), alignment: .top)
            }
        }
        .ignoresSafeArea(.keyboard)
        .sheet(isPresented: $isShowingPlayerSheet) {
            PlayerDeckSheet(player: player, queue: $queue) {
                isShowingPlayerSheet = false
            }
        }
        .sheet(isPresented: $isShowingSyncSettings) {
            SyncSettingsSheet(onSave: configureSync)
        }
        .task {
            await loadInitialState()
        }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .active {
                Task { await refreshFeedIfNeeded() }
            }
        }
    }

    private var currentTitle: String {
        switch selectedTab {
        case 0: return "Weekly Briefing"
        case 1: return "Channels"
        case 2: return "Bookmarks"
        default: return "TubeLM"
        }
    }

    private func tabButton(index: Int, title: String, icon: String) -> some View {
        Button(action: { selectedTab = index }) {
            VStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 20))
                Text(title)
                    .font(.system(size: 10, weight: .bold))
            }
            .foregroundColor(selectedTab == index ? AppTheme.accent : .secondary)
        }
    }

    // MARK: - Sync Configuration

    private func configureSync(endpoint: String, key: String) {
        let trimmedEndpoint = endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedKey = key.trimmingCharacters(in: .whitespacesAndNewlines)
        UserDefaults.standard.set(trimmedEndpoint, forKey: SyncDefaults.endpointKey)
        UserDefaults.standard.set(trimmedKey, forKey: SyncDefaults.keyKey)
        let url = URL(string: trimmedEndpoint) ?? URL(string: SyncDefaults.defaultEndpoint)!
        syncClient = CloudflareSyncClient(baseURL: url, syncKey: trimmedKey)
        Task {
            await pullRemoteState()
            scheduleSyncPush()
        }
    }

    // MARK: - State & Actions

    private func loadInitialState() async {
        if let cached = try? await store.loadCachedFeed() {
            self.feed = cached
        }
        self.readIDs = await store.loadReadIDs()
        self.bookmarks = await store.loadBookmarks()
        await pullRemoteState()
        await refreshFeedIfNeeded()
    }

    /// Stale-while-revalidate: single-flight conditional GET. A 304 keeps the
    /// local cache untouched; a 200 atomically replaces it.
    private func refreshFeedIfNeeded() async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        guard let url = URL(string: "https://vkr1729.github.io/TubeLM/data.json") else { return }
        do {
            var request = URLRequest(url: url)
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.timeoutInterval = 20
            let meta = await store.loadMeta()
            if let etag = meta.etag, !etag.isEmpty {
                request.addValue(etag, forHTTPHeaderField: "If-None-Match")
            }
            if let lastModified = meta.lastModified, !lastModified.isEmpty {
                request.addValue(lastModified, forHTTPHeaderField: "If-Modified-Since")
            }
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else { return }
            if http.statusCode == 304 {
                var updated = meta
                updated.lastChecked = Date()
                try? await store.saveMeta(updated)
                return
            }
            guard (200..<300).contains(http.statusCode) else { return }
            let newFeed = try JSONDecoder().decode(DigestFeed.self, from: data)
            self.feed = newFeed
            try? await store.saveFeed(newFeed)
            var updated = meta
            updated.lastChecked = Date()
            if let etag = http.value(forHTTPHeaderField: "ETag"), !etag.isEmpty {
                updated.etag = etag
            }
            if let lastModified = http.value(forHTTPHeaderField: "Last-Modified"), !lastModified.isEmpty {
                updated.lastModified = lastModified
            }
            try? await store.saveMeta(updated)
        } catch {
            // Offline or degraded feed: keep serving the local cache silently.
        }
    }

    private func pullRemoteState() async {
        do {
            if let remote = try await syncClient.fetchRemoteState() {
                let mergedReads = try await store.applyRemoteStates(remote.itemStates)
                self.readIDs = mergedReads
                let mergedBookmarks = try await store.applyRemoteBookmarks(
                    remoteBookmarks: remote.bookmarks,
                    remoteStates: remote.bookmarkStates
                )
                self.bookmarks = mergedBookmarks
            }
        } catch {
            // Unpaired or unreachable: local state remains authoritative.
        }
    }

    /// Debounced background push: every mutation schedules one push ~1.5s out,
    /// coalescing rapid taps into a single request. Silent on failure.
    private func scheduleSyncPush() {
        syncTask?.cancel()
        syncTask = Task {
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            guard !Task.isCancelled else { return }
            do {
                let states = await store.loadItemStates()
                let ordered = await store.loadReadIDsOrdered()
                let localBookmarks = await store.loadBookmarks()
                let localBookmarkStates = await store.loadBookmarkStates()
                if let remote = try await syncClient.pushLocalMutations(
                    readIds: ordered,
                    top20Read: ordered,
                    itemStates: states,
                    bookmarks: localBookmarks,
                    bookmarkStates: localBookmarkStates
                ) {
                    let mergedReads = try await store.applyRemoteStates(remote.itemStates)
                    self.readIDs = mergedReads
                    let mergedBookmarks = try await store.applyRemoteBookmarks(
                        remoteBookmarks: remote.bookmarks,
                        remoteStates: remote.bookmarkStates
                    )
                    self.bookmarks = mergedBookmarks
                }
            } catch {
                // Next mutation retries; never interrupt the user.
            }
        }
    }

    private func markRead(_ id: String) {
        readIDs.insert(id)
        Haptics.confirm()
        Task {
            try? await store.markItemRead(id)
            scheduleSyncPush()
        }
    }

    private func toggleRead(_ id: String) {
        let willBeRead = !readIDs.contains(id)
        if willBeRead {
            readIDs.insert(id)
            Haptics.confirm()
        } else {
            readIDs.remove(id)
            Haptics.tap()
        }
        Task {
            if willBeRead {
                try? await store.markItemRead(id)
            } else {
                try? await store.unmarkItemRead(id)
            }
            scheduleSyncPush()
        }
    }

    private func toggleBookmark(_ item: FeedItem) {
        if bookmarks.contains(where: { $0.id == item.id }) {
            removeBookmark(item.id)
        } else {
            bookmarks.insert(item, at: 0)
            Haptics.confirm()
            Task {
                try? await store.saveBookmark(item)
                scheduleSyncPush()
            }
        }
    }

    private func removeBookmark(_ id: String) {
        bookmarks.removeAll(where: { $0.id == id })
        Task {
            try? await store.removeBookmark(id: id)
            scheduleSyncPush()
        }
    }

    private func playItemAudio(_ item: FeedItem) {
        player.playTrack(title: item.title, source: item.sourceName, urlString: item.audioUrl)
    }

    private func playChannelAudio(_ channel: Channel) {
        let resolved = CommuteQueueModel.resolveChannelPlayback(for: channel, readIDs: readIDs)
        player.playTrack(title: "\(channel.name): \(resolved.title)", source: channel.name, urlString: resolved.audioUrl)
    }

    private func enqueueFeedItem(_ item: FeedItem) {
        let q = QueueItem(id: item.id, title: item.title, sourceName: item.sourceName, duration: item.duration ?? "", audioUrl: item.audioUrl)
        enqueueQueueItem(q)
    }

    private func enqueueQueueItem(_ item: QueueItem) {
        if !queue.contains(where: { $0.id == item.id }) {
            queue.append(item)
            Haptics.tap()
            showToast("Added to Queue")
            scheduleSyncPush()
        }
    }

    private func showToast(_ msg: String) {
        toastTask?.cancel()
        withAnimation { syncToastText = msg }
        toastTask = Task {
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            if !Task.isCancelled {
                withAnimation { syncToastText = nil }
            }
        }
    }
}

private struct SyncSettingsSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var endpoint: String = UserDefaults.standard.string(forKey: SyncDefaults.endpointKey) ?? SyncDefaults.defaultEndpoint
    @State private var passphrase: String = UserDefaults.standard.string(forKey: SyncDefaults.keyKey) ?? ""
    let onSave: (String, String) -> Void

    var body: some View {
        NavigationStack {
            Form {
                Section("Worker URL") {
                    #if os(iOS)
                    TextField("https://tubelm-sync.<subdomain>.workers.dev", text: $endpoint)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                    #else
                    TextField("https://tubelm-sync.<subdomain>.workers.dev", text: $endpoint)
                        .autocorrectionDisabled(true)
                    #endif
                }
                Section("Sync Passphrase") {
                    SecureField("16+ character passphrase", text: $passphrase)
                }
                Section {
                    Text("Background sync runs automatically on every change once paired. Leave the passphrase empty to stay local-only.")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                }
            }
            .navigationTitle("Cloud Sync")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        onSave(endpoint, passphrase)
                        dismiss()
                    }
                }
            }
        }
    }
}
#endif
