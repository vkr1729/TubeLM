#if canImport(SwiftUI)
import SwiftUI
import TubeLMCore

private enum SyncDefaults {
    static let endpointKey = "tubelm.syncEndpoint"
    static let keyKey = "tubelm.syncKey"
    static let themeKey = "tubelm.themeMode"
    static let defaultEndpoint = "https://tubelm-sync.kedarvreddy.workers.dev"
}

private enum SyncConnectionState: Equatable {
    case unconfigured
    case testing
    case connected
    case disrupted(String)
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
    @State private var syncState: SyncConnectionState

    private let store = ContentStore()

    public init() {
        let stored = UserDefaults.standard.string(forKey: SyncDefaults.endpointKey)
        let endpoint: String
        if let s = stored, !s.contains("vkr1729.workers.dev"), !s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            endpoint = s
        } else {
            endpoint = SyncDefaults.defaultEndpoint
            UserDefaults.standard.set(SyncDefaults.defaultEndpoint, forKey: SyncDefaults.endpointKey)
        }
        let key = UserDefaults.standard.string(forKey: SyncDefaults.keyKey) ?? ""
        let url = URL(string: endpoint) ?? URL(string: SyncDefaults.defaultEndpoint)!
        _syncClient = State(initialValue: CloudflareSyncClient(baseURL: url, syncKey: key))
        if key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            _syncState = State(initialValue: .unconfigured)
        } else {
            _syncState = State(initialValue: .connected)
        }
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
                                onMarkRead: markItemRead,
                                onPlayAudio: playItemAudio,
                                onEnqueue: enqueueFeedItem,
                                onToggleBookmark: toggleBookmark,
                                isBookmarked: { id in bookmarks.contains(where: { $0.id == id }) }
                            )
                        case 1:
                            ChannelsView(
                                channels: feed?.channels ?? [],
                                readIDs: readIDs,
                                onMarkRead: markVideoRead,
                                onToggleRead: toggleVideoRead,
                                onPlayChannel: playChannelAudio,
                                onEnqueueItem: enqueueQueueItem,
                                onToggleBookmark: toggleBookmark
                            )
                        case 2:
                            BookmarksView(
                                bookmarks: bookmarks,
                                onRemoveBookmark: removeBookmark,
                                onOpenSettings: { isShowingSyncSettings = true }
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
                    if shouldShowSyncButton {
                        ToolbarItem(placement: .topBarTrailing) {
                            syncToolbarButton
                        }
                    }
                }
                #else
                .toolbar {
                    if shouldShowSyncButton {
                        ToolbarItem(placement: .automatic) {
                            syncToolbarButton
                        }
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
                    .onLongPressGesture {
                        Haptics.tap()
                        isShowingSyncSettings = true
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

    // MARK: - Sync Toolbar Button & Visibility

    private var shouldShowSyncButton: Bool {
        switch syncState {
        case .connected:
            return false
        case .unconfigured, .testing, .disrupted:
            return true
        }
    }

    @ViewBuilder
    private var syncToolbarButton: some View {
        Button(action: { isShowingSyncSettings = true }) {
            switch syncState {
            case .unconfigured:
                HStack(spacing: 5) {
                    Image(systemName: "arrow.triangle.2.circlepath")
                        .font(.system(size: 11, weight: .bold))
                    Text("Sync")
                        .font(.system(size: 12, weight: .bold))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(AppTheme.accent.opacity(0.12))
                .foregroundColor(AppTheme.accent)
                .clipShape(Capsule())
            case .testing:
                HStack(spacing: 5) {
                    ProgressView()
                        .controlSize(.mini)
                        .tint(AppTheme.accent)
                    Text("Connecting...")
                        .font(.system(size: 11, weight: .bold))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(AppTheme.accent.opacity(0.12))
                .foregroundColor(AppTheme.accent)
                .clipShape(Capsule())
            case .disrupted:
                HStack(spacing: 5) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 10, weight: .bold))
                    Text("Sync Offline")
                        .font(.system(size: 11, weight: .bold))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(Color.orange.opacity(0.16))
                .foregroundColor(.orange)
                .clipShape(Capsule())
            case .connected:
                EmptyView()
            }
        }
        .accessibilityLabel("Sync settings")
    }

    // MARK: - Sync Configuration

    private func configureSync(endpoint: String, key: String) {
        let trimmedEndpoint = endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedKey = key.trimmingCharacters(in: .whitespacesAndNewlines)
        UserDefaults.standard.set(trimmedEndpoint, forKey: SyncDefaults.endpointKey)
        UserDefaults.standard.set(trimmedKey, forKey: SyncDefaults.keyKey)
        let url = URL(string: trimmedEndpoint) ?? URL(string: SyncDefaults.defaultEndpoint)!
        syncClient = CloudflareSyncClient(baseURL: url, syncKey: trimmedKey)

        guard !trimmedKey.isEmpty else {
            withAnimation(.easeInOut(duration: 0.25)) {
                syncState = .unconfigured
            }
            showToast("Local Storage Only")
            return
        }

        withAnimation(.easeInOut(duration: 0.25)) {
            syncState = .testing
        }
        showToast("Testing Connection...")

        Task {
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
                withAnimation(.easeInOut(duration: 0.25)) {
                    syncState = .connected
                }
                showToast("Sync Connected")
                scheduleSyncPush()
            } catch {
                withAnimation(.easeInOut(duration: 0.25)) {
                    syncState = .disrupted(error.localizedDescription)
                }
                showToast("Connection Failed")
            }
        }
    }

    // MARK: - State & Actions

    private func loadInitialState() async {
        if let cached = await store.loadCachedFeed() {
            self.feed = cached
        }
        self.readIDs = await store.loadReadIDs()
        self.bookmarks = await store.loadBookmarks()
        if await syncClient.isConfigured {
            await pullRemoteState()
        } else {
            withAnimation(.easeInOut(duration: 0.25)) {
                syncState = .unconfigured
            }
        }
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
            let merged = Self.mergeFeedAudio(incoming: newFeed, fallback: self.feed)
            self.feed = merged
            try? await store.saveFeed(merged)
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
        guard await syncClient.isConfigured else {
            withAnimation(.easeInOut(duration: 0.25)) { syncState = .unconfigured }
            return
        }
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
            withAnimation(.easeInOut(duration: 0.25)) { syncState = .connected }
        } catch {
            withAnimation(.easeInOut(duration: 0.25)) { syncState = .disrupted(error.localizedDescription) }
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
                if syncState != .connected {
                    withAnimation(.easeInOut(duration: 0.25)) { syncState = .connected }
                }
            } catch {
                withAnimation(.easeInOut(duration: 0.25)) { syncState = .disrupted(error.localizedDescription) }
            }
        }
    }

    private func markItemRead(_ item: FeedItem) {
        let aliases = item.aliases
        for a in aliases { readIDs.insert(a) }
        Haptics.confirm()
        Task {
            try? await store.markItemRead(aliases: aliases)
            scheduleSyncPush()
        }
    }

    private func markVideoRead(_ vid: VideoItem) {
        let aliases = vid.aliases
        for a in aliases { readIDs.insert(a) }
        Haptics.confirm()
        Task {
            try? await store.markItemRead(aliases: aliases)
            scheduleSyncPush()
        }
    }

    private func toggleVideoRead(_ vid: VideoItem) {
        let aliases = vid.aliases
        let willBeRead = aliases.intersection(readIDs).isEmpty
        if willBeRead {
            for a in aliases { readIDs.insert(a) }
            Haptics.confirm()
        } else {
            for a in aliases { readIDs.remove(a) }
            Haptics.tap()
        }
        Task {
            if willBeRead {
                try? await store.markItemRead(aliases: aliases)
            } else {
                try? await store.unmarkItemRead(aliases: aliases)
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

    private func resolveAudioUrl(for item: FeedItem) -> String? {
        if let direct = item.audioUrl?.trimmingCharacters(in: .whitespacesAndNewlines), !direct.isEmpty {
            return direct
        }
        if let ch = feed?.channels.first(where: {
            $0.name.caseInsensitiveCompare(item.sourceName) == .orderedSame ||
            $0.id.caseInsensitiveCompare(item.sourceName) == .orderedSame
        }) {
            let chAudio = (ch.summaryAudioUrl ?? ch.audioUrl)?.trimmingCharacters(in: .whitespacesAndNewlines)
            if let chAudio = chAudio, !chAudio.isEmpty {
                return chAudio
            }
        }
        return nil
    }

    private func playItemAudio(_ item: FeedItem) {
        markItemRead(item)
        let resolved = resolveAudioUrl(for: item)
        player.playTrack(title: item.title, source: item.sourceName, urlString: resolved)
    }

    private func playChannelAudio(_ channel: Channel) {
        let resolved = CommuteQueueModel.resolveChannelPlayback(for: channel, readIDs: readIDs)
        player.playTrack(title: "\(channel.name): \(resolved.title)", source: channel.name, urlString: resolved.audioUrl)
    }

    private func enqueueFeedItem(_ item: FeedItem) {
        let resolved = resolveAudioUrl(for: item)
        let q = QueueItem(id: item.id, title: item.title, sourceName: item.sourceName, duration: item.duration ?? "", audioUrl: resolved)
        enqueueQueueItem(q)
    }

    private static func mergeFeedAudio(incoming: DigestFeed, fallback: DigestFeed?) -> DigestFeed {
        guard let fallback = fallback else { return incoming }

        var channelAudioMap: [String: String] = [:]
        for ch in fallback.channels {
            if let a = (ch.summaryAudioUrl ?? ch.audioUrl)?.trimmingCharacters(in: .whitespacesAndNewlines), !a.isEmpty {
                channelAudioMap[ch.name.lowercased()] = a
                channelAudioMap[ch.id.lowercased()] = a
            }
        }

        let mergedChannels = incoming.channels.map { ch -> Channel in
            let existingAudio = (ch.summaryAudioUrl ?? ch.audioUrl)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let fallbackAudio = existingAudio.isEmpty ? (channelAudioMap[ch.name.lowercased()] ?? channelAudioMap[ch.id.lowercased()]) : nil
            let summaryAudio = ch.summaryAudioUrl?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false ? ch.summaryAudioUrl : fallbackAudio

            let mergedVideos = ch.videos.map { vid -> VideoItem in
                let vidAudio = vid.audioUrl?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                let resolvedVidAudio = vidAudio.isEmpty ? (summaryAudio ?? fallbackAudio) : vidAudio
                return VideoItem(
                    id: vid.id,
                    videoId: vid.videoId,
                    title: vid.title,
                    duration: vid.duration,
                    durationSeconds: vid.durationSeconds,
                    summaryHtml: vid.summaryHtml,
                    url: vid.url,
                    audioUrl: resolvedVidAudio,
                    sourceType: vid.sourceType,
                    lead: vid.lead
                )
            }

            return Channel(
                id: ch.id,
                name: ch.name,
                category: ch.category,
                readMinutes: ch.readMinutes,
                summaryText: ch.summaryText,
                summaryAudioUrl: summaryAudio,
                audioUrl: ch.audioUrl,
                videos: mergedVideos
            )
        }

        let mergedItems = incoming.top20.items.map { it -> FeedItem in
            let itemAudio = it.audioUrl?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let fallbackAudio = itemAudio.isEmpty ? channelAudioMap[it.sourceName.lowercased()] : nil
            let finalAudio = itemAudio.isEmpty ? fallbackAudio : itemAudio
            return FeedItem(
                id: it.id,
                videoId: it.videoId,
                rank: it.rank,
                title: it.title,
                sourceName: it.sourceName,
                sourceType: it.sourceType,
                duration: it.duration,
                durationSeconds: it.durationSeconds,
                whyItMatters: it.whyItMatters,
                url: it.url,
                audioUrl: finalAudio
            )
        }

        return DigestFeed(
            schemaVersion: incoming.schemaVersion,
            builtAt: incoming.builtAt,
            runDate: incoming.runDate,
            top20: Top20Container(items: mergedItems),
            channels: mergedChannels
        )
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
    @AppStorage("tubelm.themeMode") private var themeMode: String = AppThemeMode.light.rawValue
    @State private var endpoint: String
    @State private var passphrase: String

    let onSave: (String, String) -> Void

    init(onSave: @escaping (String, String) -> Void) {
        self.onSave = onSave
        let storedEndpoint = UserDefaults.standard.string(forKey: SyncDefaults.endpointKey)
        let resolvedEndpoint: String
        if let s = storedEndpoint, !s.contains("vkr1729.workers.dev"), !s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            resolvedEndpoint = s
        } else {
            resolvedEndpoint = SyncDefaults.defaultEndpoint
        }
        _endpoint = State(initialValue: resolvedEndpoint)
        _passphrase = State(initialValue: UserDefaults.standard.string(forKey: SyncDefaults.keyKey) ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Appearance") {
                    Picker("Theme", selection: $themeMode) {
                        ForEach(AppThemeMode.allCases) { mode in
                            Text(mode.title).tag(mode.rawValue)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                Section("Cloud Sync") {
                    #if os(iOS)
                    TextField("https://tubelm-sync.kedarvreddy.workers.dev", text: $endpoint)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                    #else
                    TextField("https://tubelm-sync.kedarvreddy.workers.dev", text: $endpoint)
                        .autocorrectionDisabled(true)
                    #endif
                    SecureField("16+ character passphrase", text: $passphrase)
                }

                Section {
                    HStack {
                        Image(systemName: passphrase.isEmpty ? "bolt.slash" : "bolt.shield.fill")
                            .foregroundColor(passphrase.isEmpty ? .secondary : AppTheme.accent)
                        Text(passphrase.isEmpty ? "Mode: Local Storage Only" : "Mode: Cloudflare KV Sync Active")
                            .font(.footnote)
                            .foregroundColor(.secondary)
                    }
                    Text("Background sync runs automatically on every change once paired. Leave the passphrase empty to stay local-only.")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                }
            }
            .navigationTitle("Settings & Sync")
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
