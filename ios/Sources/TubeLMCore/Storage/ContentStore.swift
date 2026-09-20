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

    public func loadCachedFeed() -> DigestFeed? {
        if FileManager.default.fileExists(atPath: feedCacheFile.path) {
            if let data = try? Data(contentsOf: feedCacheFile) {
                if let feed = try? JSONDecoder().decode(DigestFeed.self, from: data),
                   !feed.top20.items.isEmpty {
                    return feed
                } else {
                    // Corrupt or empty cache file detected: quarantine to preserve diagnostics and heal
                    let corruptPath = feedCacheFile.path + ".corrupt.\(Int(Date().timeIntervalSince1970))"
                    try? FileManager.default.moveItem(atPath: feedCacheFile.path, toPath: corruptPath)
                }
            }
        }

        // Fallback to bundled seed feed on initial launch or after cache corruption
        let mainCandidates = [
            Bundle.main.url(forResource: "data", withExtension: "json"),
            Bundle.main.url(forResource: "mock_data", withExtension: "json")
        ]
        for url in mainCandidates.compactMap({ $0 }) {
            if let data = try? Data(contentsOf: url),
               let feed = try? JSONDecoder().decode(DigestFeed.self, from: data),
               !feed.top20.items.isEmpty {
                try? saveFeed(feed)
                return feed
            }
        }

        // Fallback file paths for development / test environments without Bundle.main resources
        let envCandidates = [
            ProcessInfo.processInfo.environment["MOCK_DATA_PATH"],
            ProcessInfo.processInfo.environment["DATA_PATH"]
        ].compactMap { $0 }
        for envPath in envCandidates {
            let url = URL(fileURLWithPath: envPath)
            if let data = try? Data(contentsOf: url),
               let feed = try? JSONDecoder().decode(DigestFeed.self, from: data),
               !feed.top20.items.isEmpty {
                try? saveFeed(feed)
                return feed
            }
        }

        let fallbackRelativePaths = [
            "Resources/data.json",
            "Resources/mock_data.json",
            "../.workflow/mocks/mock_data.json",
            ".workflow/mocks/mock_data.json"
        ]
        for rel in fallbackRelativePaths {
            let url = URL(fileURLWithPath: rel)
            if FileManager.default.fileExists(atPath: url.path),
               let data = try? Data(contentsOf: url),
               let feed = try? JSONDecoder().decode(DigestFeed.self, from: data),
               !feed.top20.items.isEmpty {
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
        var ordered: [String] = []
        ordered.reserveCapacity(min(ids.count, Self.maxReadIDs))
        for raw in ids {
            let id = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty, id.count <= 256, seen.insert(id).inserted else { continue }
            ordered.append(id)
            if ordered.count >= Self.maxReadIDs { break }
        }
        return ordered
    }

    public func loadReadIDs() -> Set<String> {
        Set(loadReadIDsOrdered())
    }

    private func persistReadIDs(_ ids: [String]) throws {
        let data = try JSONEncoder().encode(Array(ids.prefix(Self.maxReadIDs)))
        try atomicWrite(data: data, to: readStateFile)
    }

    public func markItemRead(_ id: String) throws {
        let clean = id.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, clean.count <= 256 else { return }
        var current = loadReadIDsOrdered()
        current.removeAll(where: { $0 == clean })
        current.insert(clean, at: 0)
        try persistReadIDs(current)
        var states = loadItemStates()
        states[clean] = Date().timeIntervalSince1970 * 1000
        try saveItemStates(states)
    }

    public func unmarkItemRead(_ id: String) throws {
        let clean = id.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, clean.count <= 256 else { return }
        var current = loadReadIDsOrdered()
        current.removeAll(where: { $0 == clean })
        try persistReadIDs(current)
        var states = loadItemStates()
        states[clean] = -Date().timeIntervalSince1970 * 1000
        try saveItemStates(states)
    }

    // MARK: - Item States (LWW Tombstone Map for Sync)

    public func loadItemStates() -> [String: Double] {
        guard FileManager.default.fileExists(atPath: itemStatesFile.path),
              let data = try? Data(contentsOf: itemStatesFile),
              let decoded = try? JSONDecoder().decode([String: Double].self, from: data) else {
            return [:]
        }
        var clean: [String: Double] = [:]
        clean.reserveCapacity(min(decoded.count, Self.maxItemStates))
        for (key, ts) in decoded {
            let id = key.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty, id.count <= 256, ts.isFinite else { continue }
            clean[id] = ts
        }
        return clean
    }

    public func saveItemStates(_ states: [String: Double]) throws {
        var finite: [String: Double] = [:]
        finite.reserveCapacity(min(states.count, Self.maxItemStates))
        for (key, ts) in states {
            let id = key.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty, id.count <= 256, ts.isFinite else { continue }
            finite[id] = ts
        }
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
            let id = key.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty, id.count <= 256, ts.isFinite else { continue }
            let cur = local[id] ?? 0
            if abs(ts) >= abs(cur) {
                local[id] = ts
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
            var clean: [String: Double] = [:]
            clean.reserveCapacity(min(decoded.count, Self.maxBookmarkStates))
            for (key, ts) in decoded {
                let id = key.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !id.isEmpty, id.count <= 256, ts.isFinite else { continue }
                clean[id] = ts
            }
            return clean
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
        var finite: [String: Double] = [:]
        finite.reserveCapacity(min(states.count, Self.maxBookmarkStates))
        for (key, ts) in states {
            let id = key.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty, id.count <= 256, ts.isFinite else { continue }
            finite[id] = ts
        }
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
        let clean = item.id.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, clean.count <= 256 else { return }
        var current = loadBookmarks()
        current.removeAll(where: { $0.id == item.id || $0.id == clean })
        current.insert(item, at: 0)
        let encoder = JSONEncoder()
        encoder.outputFormatting = .prettyPrinted
        let data = try encoder.encode(current)
        try atomicWrite(data: data, to: bookmarksFile)

        var states = loadBookmarkStates()
        states[clean] = Date().timeIntervalSince1970 * 1000
        try saveBookmarkStates(states)
    }

    public func removeBookmark(id: String) throws {
        let clean = id.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, clean.count <= 256 else { return }
        var current = loadBookmarks()
        current.removeAll(where: { $0.id == id || $0.id == clean })
        let encoder = JSONEncoder()
        encoder.outputFormatting = .prettyPrinted
        let data = try encoder.encode(current)
        try atomicWrite(data: data, to: bookmarksFile)

        var states = loadBookmarkStates()
        states[clean] = -Date().timeIntervalSince1970 * 1000
        try saveBookmarkStates(states)
    }

    /// Merges remote bookmarks and bookmark states into local storage using LWW tombstones.
    public func applyRemoteBookmarks(remoteBookmarks: [FeedItem], remoteStates: [String: Double]) throws -> [FeedItem] {
        var localStates = loadBookmarkStates()
        for (key, ts) in remoteStates {
            let id = key.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty, id.count <= 256, ts.isFinite else { continue }
            let cur = localStates[id] ?? 0
            if abs(ts) >= abs(cur) {
                localStates[id] = ts
            }
        }

        var itemsMap = [String: FeedItem]()
        for item in loadBookmarks() {
            let id = item.id.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty, id.count <= 256 else { continue }
            itemsMap[id] = item
            if localStates[id] == nil {
                localStates[id] = Date().timeIntervalSince1970 * 1000
            }
        }
        for item in remoteBookmarks {
            let id = item.id.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !id.isEmpty, id.count <= 256 else { continue }
            itemsMap[id] = item
            if localStates[id] == nil {
                localStates[id] = Date().timeIntervalSince1970 * 1000
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
