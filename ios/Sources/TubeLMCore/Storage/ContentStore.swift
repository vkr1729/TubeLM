import Foundation

public actor ContentStore {
    public static let maxReadIDs = 5000
    public static let maxItemStates = 5000
    public static let maxBookmarkStates = 5000

    private let baseDirectory: URL
    private let cacheDirectory: URL
    private let pinnedDirectory: URL
    private let feedCacheFile: URL
    private let readStateFile: URL
    private let itemStatesFile: URL
    private let bookmarksFile: URL
    private let bookmarkStatesFile: URL
    private let metaFile: URL

    public struct StoreMeta: Codable, Sendable {
        public var etag: String?
        public var lastChecked: Date?
        public var lastModified: String?

        public init(etag: String? = nil, lastChecked: Date? = nil, lastModified: String? = nil) {
            self.etag = etag
            self.lastChecked = lastChecked
            self.lastModified = lastModified
        }
    }

    public init(baseDirectory: URL? = nil) {
        let base: URL
        if let baseDirectory = baseDirectory {
            base = baseDirectory
        } else {
            let paths = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)
            base = paths.first ?? URL(fileURLWithPath: NSTemporaryDirectory())
        }
        self.baseDirectory = base
        self.cacheDirectory = base.appendingPathComponent("cache", isDirectory: true)
        self.pinnedDirectory = base.appendingPathComponent("pinned", isDirectory: true)
        self.feedCacheFile = cacheDirectory.appendingPathComponent("feed.json")
        self.readStateFile = cacheDirectory.appendingPathComponent("read_state.json")
        self.itemStatesFile = cacheDirectory.appendingPathComponent("item_states.json")
        self.bookmarksFile = pinnedDirectory.appendingPathComponent("bookmarks.json")
        self.bookmarkStatesFile = pinnedDirectory.appendingPathComponent("bookmark_states.json")
        self.metaFile = cacheDirectory.appendingPathComponent("meta.json")

        try? FileManager.default.createDirectory(at: cacheDirectory, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: pinnedDirectory, withIntermediateDirectories: true)
    }

    // MARK: - Atomic File Writing

    private func atomicWrite(data: Data, to destination: URL) throws {
        try FileManager.default.createDirectory(
            at: destination.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: destination, options: .atomic)
    }

    // MARK: - Feed Cache

    public func loadCachedFeed() throws -> DigestFeed? {
        if FileManager.default.fileExists(atPath: feedCacheFile.path) {
            let data = try Data(contentsOf: feedCacheFile)
            return try JSONDecoder().decode(DigestFeed.self, from: data)
        }

        // Fallback to bundled seed feed on initial launch
        #if SWIFT_PACKAGE
        if let bundleUrl = Bundle.module.url(forResource: "data", withExtension: "json") ??
                           Bundle.module.url(forResource: "data", withExtension: "json", subdirectory: "Resources") {
            if let data = try? Data(contentsOf: bundleUrl),
               let feed = try? JSONDecoder().decode(DigestFeed.self, from: data) {
                try? saveFeed(feed)
                return feed
            }
        }
        #endif

        let mainCandidates = [
            Bundle.main.url(forResource: "data", withExtension: "json"),
            Bundle.main.url(forResource: "mock_data", withExtension: "json")
        ]
        for url in mainCandidates.compactMap({ $0 }) {
            if let data = try? Data(contentsOf: url),
               let feed = try? JSONDecoder().decode(DigestFeed.self, from: data) {
                try? saveFeed(feed)
                return feed
            }
        }

        return nil
    }

    public func saveFeed(_ feed: DigestFeed) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted]
        let data = try encoder.encode(feed)
        try atomicWrite(data: data, to: feedCacheFile)
    }

    // MARK: - Read State (Ordered LRU, Capped at 5000)

    public func loadReadIDsOrdered() -> [String] {
        guard FileManager.default.fileExists(atPath: readStateFile.path),
              let data = try? Data(contentsOf: readStateFile),
              let ids = try? JSONDecoder().decode([String].self, from: data) else {
            return []
        }
        var seen = Set<String>()
        return ids.filter { seen.insert($0).inserted }.prefix(Self.maxReadIDs).map { $0 }
    }

    public func loadReadIDs() -> Set<String> {
        Set(loadReadIDsOrdered())
    }

    private func persistReadIDs(_ ids: [String]) throws {
        let data = try JSONEncoder().encode(Array(ids.prefix(Self.maxReadIDs)))
        try atomicWrite(data: data, to: readStateFile)
    }

    public func markItemRead(_ id: String) throws {
        var current = loadReadIDsOrdered()
        current.removeAll(where: { $0 == id })
        current.insert(id, at: 0)
        try persistReadIDs(current)
        var states = loadItemStates()
        states[id] = Date().timeIntervalSince1970 * 1000
        try saveItemStates(states)
    }

    public func unmarkItemRead(_ id: String) throws {
        var current = loadReadIDsOrdered()
        current.removeAll(where: { $0 == id })
        try persistReadIDs(current)
        var states = loadItemStates()
        states[id] = -Date().timeIntervalSince1970 * 1000
        try saveItemStates(states)
    }

    // MARK: - Item States (LWW Tombstone Map for Sync)

    public func loadItemStates() -> [String: Double] {
        guard FileManager.default.fileExists(atPath: itemStatesFile.path),
              let data = try? Data(contentsOf: itemStatesFile),
              let decoded = try? JSONDecoder().decode([String: Double].self, from: data) else {
            return [:]
        }
        return decoded.filter { _, ts in ts.isFinite }
    }

    public func saveItemStates(_ states: [String: Double]) throws {
        let finite = states.filter { _, ts in ts.isFinite }
        let capped: [String: Double]
        if finite.count > Self.maxItemStates {
            var kept = [String: Double](minimumCapacity: Self.maxItemStates)
            for (key, value) in finite.sorted(by: { abs($0.value) > abs($1.value) }).prefix(Self.maxItemStates) {
                kept[key] = value
            }
            capped = kept
        } else {
            capped = finite
        }
        let data = try JSONEncoder().encode(capped)
        try atomicWrite(data: data, to: itemStatesFile)
    }

    /// Merges a remote sync payload into local state. Positive timestamps win
    /// as read, negative as unread; most-recent intent wins per key.
    public func applyRemoteStates(_ remote: [String: Double]) throws -> Set<String> {
        var local = loadItemStates()
        for (key, ts) in remote {
            guard ts.isFinite else { continue }
            let cur = local[key] ?? 0
            if abs(ts) >= abs(cur) {
                local[key] = ts
            }
        }
        try saveItemStates(local)
        var ordered = loadReadIDsOrdered()
        for (key, ts) in local {
            if ts > 0, !ordered.contains(key) {
                ordered.insert(key, at: 0)
            } else if ts < 0 {
                ordered.removeAll(where: { $0 == key })
            }
        }
        try persistReadIDs(ordered)
        return Set(ordered)
    }

    // MARK: - Pinned Bookmarks (Pin-Exempt from Purge, Unlimited Text)

    public func loadBookmarks() -> [FeedItem] {
        guard FileManager.default.fileExists(atPath: bookmarksFile.path),
              let data = try? Data(contentsOf: bookmarksFile),
              let items = try? JSONDecoder().decode([FeedItem].self, from: data) else {
            return []
        }
        return items
    }

    public func loadBookmarkStates() -> [String: Double] {
        if FileManager.default.fileExists(atPath: bookmarkStatesFile.path),
           let data = try? Data(contentsOf: bookmarkStatesFile),
           let decoded = try? JSONDecoder().decode([String: Double].self, from: data) {
            return decoded.filter { _, ts in ts.isFinite }
        }
        // Seed from existing bookmarks if states file does not exist yet
        let existing = loadBookmarks()
        guard !existing.isEmpty else { return [:] }
        let now = Date().timeIntervalSince1970 * 1000
        var seeded: [String: Double] = [:]
        for item in existing {
            seeded[item.id] = now
        }
        return seeded
    }

    public func saveBookmarkStates(_ states: [String: Double]) throws {
        let finite = states.filter { _, ts in ts.isFinite }
        let capped: [String: Double]
        if finite.count > Self.maxBookmarkStates {
            var kept = [String: Double](minimumCapacity: Self.maxBookmarkStates)
            for (key, value) in finite.sorted(by: { abs($0.value) > abs($1.value) }).prefix(Self.maxBookmarkStates) {
                kept[key] = value
            }
            capped = kept
        } else {
            capped = finite
        }
        let data = try JSONEncoder().encode(capped)
        try atomicWrite(data: data, to: bookmarkStatesFile)
    }

    public func saveBookmark(_ item: FeedItem) throws {
        var current = loadBookmarks()
        current.removeAll(where: { $0.id == item.id })
        current.insert(item, at: 0)
        let encoder = JSONEncoder()
        encoder.outputFormatting = .prettyPrinted
        let data = try encoder.encode(current)
        try atomicWrite(data: data, to: bookmarksFile)

        var states = loadBookmarkStates()
        states[item.id] = Date().timeIntervalSince1970 * 1000
        try saveBookmarkStates(states)
    }

    public func removeBookmark(id: String) throws {
        var current = loadBookmarks()
        current.removeAll(where: { $0.id == id })
        let encoder = JSONEncoder()
        encoder.outputFormatting = .prettyPrinted
        let data = try encoder.encode(current)
        try atomicWrite(data: data, to: bookmarksFile)

        var states = loadBookmarkStates()
        states[id] = -Date().timeIntervalSince1970 * 1000
        try saveBookmarkStates(states)
    }

    /// Merges remote bookmarks and bookmark states into local storage using LWW tombstones.
    public func applyRemoteBookmarks(remoteBookmarks: [FeedItem], remoteStates: [String: Double]) throws -> [FeedItem] {
        var localStates = loadBookmarkStates()
        for (id, ts) in remoteStates {
            guard ts.isFinite else { continue }
            let cur = localStates[id] ?? 0
            if abs(ts) >= abs(cur) {
                localStates[id] = ts
            }
        }

        var itemsMap = [String: FeedItem]()
        for item in loadBookmarks() {
            itemsMap[item.id] = item
            if localStates[item.id] == nil {
                localStates[item.id] = Date().timeIntervalSince1970 * 1000
            }
        }
        for item in remoteBookmarks {
            itemsMap[item.id] = item
            if localStates[item.id] == nil {
                localStates[item.id] = Date().timeIntervalSince1970 * 1000
            }
        }
        try saveBookmarkStates(localStates)

        var activeBookmarks: [FeedItem] = []
        for (id, item) in itemsMap {
            if let ts = localStates[id], ts > 0 {
                activeBookmarks.append(item)
            }
        }
        activeBookmarks.sort { (localStates[$0.id] ?? 0) > (localStates[$1.id] ?? 0) }

        let encoder = JSONEncoder()
        encoder.outputFormatting = .prettyPrinted
        let data = try encoder.encode(activeBookmarks)
        try atomicWrite(data: data, to: bookmarksFile)

        return activeBookmarks
    }

    // MARK: - Meta & ETag

    public func loadMeta() -> StoreMeta {
        guard FileManager.default.fileExists(atPath: metaFile.path),
              let data = try? Data(contentsOf: metaFile),
              let meta = try? JSONDecoder().decode(StoreMeta.self, from: data) else {
            return StoreMeta()
        }
        return meta
    }

    public func saveMeta(_ meta: StoreMeta) throws {
        let data = try JSONEncoder().encode(meta)
        try atomicWrite(data: data, to: metaFile)
    }
}
