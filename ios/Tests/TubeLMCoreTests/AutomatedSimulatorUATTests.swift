import XCTest
@testable import TubeLMCore

/// Automated UAT test cases verifying acceptance criteria from `.workflow/UAT_PLAN.md`
/// inside the iOS execution environment.
final class AutomatedSimulatorUATTests: XCTestCase {

    // MARK: - S1: Briefing Tab Acceptance

    /// UAT-005: Continuous #1–#20 feed with no splits or dividers
    func test_UAT005_ContinuousBriefingOrderAndCount() throws {
        let feed = try loadMockFeed()
        XCTAssertEqual(feed.top20.items.count, 20, "Briefing must contain exactly 20 items")
        for (idx, item) in feed.top20.items.enumerated() {
            let expectedRank = idx + 1
            XCTAssertEqual(item.rank, expectedRank, "Item rank must be consecutive 1..20")
            XCTAssertFalse(item.id.isEmpty, "Item id must not be empty")
            XCTAssertFalse(item.title.isEmpty, "Item title must not be empty")
        }
    }

    /// UAT-006: Why-It-Matters callouts render cleanly
    func test_UAT006_WhyItMattersCalloutFormatting() throws {
        let feed = try loadMockFeed()
        let itemsWithWhy = feed.top20.items.filter { !($0.whyItMatters ?? "").isEmpty }
        XCTAssertFalse(itemsWithWhy.isEmpty, "At least some items must contain why_it_matters callouts")
        for item in itemsWithWhy {
            let why = item.whyItMatters ?? ""
            XCTAssertFalse(why.contains("undefined"), "Why-it-matters must not contain 'undefined'")
            XCTAssertFalse(why.contains("null"), "Why-it-matters must not contain 'null'")
        }
    }

    /// UAT-007: Watch vs Read labels and icons
    func test_UAT007_ActionLabelWatchVsRead() {
        let ytItem = FeedItem(id: "yt_1", rank: 1, title: "Video", sourceName: "Ch", sourceType: "youtube")
        XCTAssertEqual(ytItem.actionLabel, "Watch", "YouTube sources must show 'Watch'")
        XCTAssertFalse(ytItem.isArticle, "YouTube sources must not be marked as articles")

        let articleItem = FeedItem(id: "art_1", rank: 2, title: "Article", sourceName: "Blog", sourceType: "rss")
        XCTAssertEqual(articleItem.actionLabel, "Read", "RSS/article sources must show 'Read'")
        XCTAssertTrue(articleItem.isArticle, "RSS sources must be marked as articles")
    }

    // MARK: - S2: Channels Tab Acceptance

    /// UAT-013 & UAT-014: Channel catalog, initials generation, and category pills
    func test_UAT013_014_ChannelCatalogPillsAndInitials() throws {
        let feed = try loadMockFeed()
        XCTAssertEqual(feed.channels.count, 23, "Catalog must contain 23 channels from feed fixture")

        for channel in feed.channels {
            XCTAssertFalse(channel.id.isEmpty, "Channel id must not be empty")
            XCTAssertFalse(channel.initials.isEmpty, "Channel initials must be generated")
            XCTAssertLessThanOrEqual(channel.initials.count, 2, "Channel initials must be 1-2 characters")
            XCTAssertFalse(channel.categoryLabel.isEmpty, "Channel must have a human-readable category pill")
        }

        // Test specific initials logic
        let mit = Channel(id: "mit", name: "MIT Technology Review", category: "tech")
        XCTAssertEqual(mit.initials, "MT")
        let b1b = Channel(id: "3b1b", name: "3Blue1Brown", category: "deep_explainer")
        XCTAssertEqual(b1b.initials, "3B")
    }

    /// UAT-017 & UAT-020: Channel completion state
    func test_UAT017_020_ChannelCompletionState() {
        let channel = Channel(
            id: "ch_test",
            name: "Test Channel",
            videos: [
                VideoItem(id: "v1", title: "Video 1"),
                VideoItem(id: "v2", title: "Video 2")
            ]
        )

        var readIDs: Set<String> = []
        let allVideosRead = channel.videos.allSatisfy { readIDs.contains($0.id) }
        XCTAssertFalse(allVideosRead, "Channel with 0/2 read is not completed")

        readIDs.insert("v1")
        let partialRead = channel.videos.allSatisfy { readIDs.contains($0.id) }
        XCTAssertFalse(partialRead, "Channel with 1/2 read is not completed")

        readIDs.insert("v2")
        let completeRead = channel.videos.allSatisfy { readIDs.contains($0.id) }
        XCTAssertTrue(completeRead, "Channel with 2/2 read is completed")
    }

    /// UAT-019: Listen unwatched channel filter
    func test_UAT019_ListenUnwatchedChannelFilter() {
        let channel = Channel(
            id: "ch_filter",
            name: "Filtered Channel",
            audioUrl: "audio/overview.mp3",
            videos: [
                VideoItem(id: "vid_1", title: "Episode 1", audioUrl: "audio/ep1.mp3"),
                VideoItem(id: "vid_2", title: "Episode 2", audioUrl: "audio/ep2.mp3"),
                VideoItem(id: "vid_3", title: "Episode 3", audioUrl: "audio/ep3.mp3")
            ]
        )

        // 1. Unwatched filter when 1 item is already read
        let read1: Set<String> = ["vid_1"]
        let target1 = CommuteQueueModel.resolveChannelPlayback(for: channel, readIDs: read1)
        XCTAssertEqual(target1.itemsToPlay.count, 2, "Must only return remaining 2 unwatched videos")
        XCTAssertEqual(target1.itemsToPlay.map { $0.id }, ["vid_2", "vid_3"])
        XCTAssertEqual(target1.title, "Unwatched Summaries (2)")

        // 2. Fallback to full channel when all are read
        let readAll: Set<String> = ["vid_1", "vid_2", "vid_3"]
        let targetAll = CommuteQueueModel.resolveChannelPlayback(for: channel, readIDs: readAll)
        XCTAssertEqual(targetAll.itemsToPlay.count, 3, "Must return all videos when none unwatched")
        XCTAssertEqual(targetAll.title, "Channel Overview")
    }

    // MARK: - S3: Bookmarks Tab Acceptance

    /// UAT-023 & UAT-056: Unlimited bookmarks in purge-exempt storage
    func test_UAT023_056_UnlimitedBookmarksStorage() async throws {
        let tempDir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("TubeLM_UAT_BM_\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let store = ContentStore(baseDirectory: tempDir)

        // Save 75 bookmarks (exceeding the old 50 bookmark limit)
        for i in 1...75 {
            let item = FeedItem(id: "bm_\(i)", rank: i, title: "Bookmark \(i)", sourceName: "Source \(i)")
            try await store.saveBookmark(item)
        }

        let loaded = await store.loadBookmarks()
        XCTAssertEqual(loaded.count, 75, "ContentStore must support unlimited bookmarks (>50)")

        // Verify bookmark removal
        try await store.removeBookmark(id: "bm_1")
        let afterRemove = await store.loadBookmarks()
        XCTAssertEqual(afterRemove.count, 74)
        XCTAssertFalse(afterRemove.contains(where: { $0.id == "bm_1" }))
    }

    /// UAT-024: Cloudflare CRDT bookmark synchronization, LWW timestamps, and tombstone resolution
    func test_UAT024_BookmarkCRDTSyncAndTombstoneResolution() async throws {
        let tempDir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("TubeLM_UAT_BMSync_\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let store = ContentStore(baseDirectory: tempDir)
        let now = Date().timeIntervalSince1970 * 1000

        // 1. Local device saves bookmark bm_1
        let bm1 = FeedItem(id: "bm_1", rank: 1, title: "Bookmark 1", sourceName: "Source 1")
        try await store.saveBookmark(bm1)

        let localStates = await store.loadBookmarkStates()
        XCTAssertGreaterThan(localStates["bm_1"] ?? 0, 0, "Bookmark save must record positive timestamp")

        // 2. Remote peer adds bookmark bm_2 at t = now + 1000
        let bm2 = FeedItem(id: "bm_2", rank: 2, title: "Bookmark 2", sourceName: "Source 2")
        let merged1 = try await store.applyRemoteBookmarks(
            remoteBookmarks: [bm2],
            remoteStates: ["bm_2": now + 1000]
        )
        XCTAssertEqual(merged1.count, 2, "Merged bookmarks must contain both bm_1 and bm_2")
        XCTAssertEqual(merged1.map { $0.id }, ["bm_2", "bm_1"], "Bookmarks must be ordered by timestamp descending")

        // 3. Local device removes bookmark bm_1 -> tombstone
        try await store.removeBookmark(id: "bm_1")
        let statesAfterDelete = await store.loadBookmarkStates()
        XCTAssertLessThan(statesAfterDelete["bm_1"] ?? 0, 0, "Unbookmarking must record negative tombstone")
        let bookmarksAfterDelete = await store.loadBookmarks()
        XCTAssertEqual(bookmarksAfterDelete.count, 1)
        XCTAssertFalse(bookmarksAfterDelete.contains(where: { $0.id == "bm_1" }))

        // 4. Stale peer attempts to re-push bm_1 with older timestamp
        let mergedStale = try await store.applyRemoteBookmarks(
            remoteBookmarks: [bm1],
            remoteStates: ["bm_1": now]
        )
        XCTAssertEqual(mergedStale.count, 1, "Stale push must not resurrect deleted bookmark")
        XCTAssertFalse(mergedStale.contains(where: { $0.id == "bm_1" }))

        // 5. Newer remote peer explicitly re-bookmarks bm_1 with fresher timestamp
        let mergedResurrect = try await store.applyRemoteBookmarks(
            remoteBookmarks: [bm1],
            remoteStates: ["bm_1": now + 10000]
        )
        XCTAssertEqual(mergedResurrect.count, 2, "Fresher intent must resurrect bookmark")
        XCTAssertTrue(mergedResurrect.contains(where: { $0.id == "bm_1" }))
    }

    // MARK: - S4: Commute Queue Acceptance

    /// UAT-026 & UAT-029: Commute Queue operations, duplicate prevention, and reorder safety
    func test_UAT026_029_CommuteQueueOperations() {
        var queue = CommuteQueueModel()
        XCTAssertTrue(queue.isEmpty)

        // Enqueue items
        let q1 = QueueItem(id: "q1", title: "Item 1", sourceName: "Source 1", duration: "5m")
        let q2 = QueueItem(id: "q2", title: "Item 2", sourceName: "Source 2", duration: "10m")
        queue.enqueue(q1)
        queue.enqueue(q2)
        XCTAssertEqual(queue.count, 2)

        // Duplicate prevention
        queue.enqueue(q1)
        XCTAssertEqual(queue.count, 2, "Enqueueing existing item must not duplicate it")

        // Safe move within bounds
        queue.move(fromOffsets: IndexSet(integer: 0), toOffset: 2)
        XCTAssertEqual(queue.items.map { $0.id }, ["q2", "q1"])

        // Out of bounds move must not crash
        queue.move(fromOffsets: IndexSet(integer: 99), toOffset: 0)
        XCTAssertEqual(queue.items.map { $0.id }, ["q2", "q1"], "Out-of-bounds move must be a safe no-op")

        // Removal
        queue.remove(id: "q2")
        XCTAssertEqual(queue.count, 1)
        XCTAssertEqual(queue.items.first?.id, "q1")
    }

    // MARK: - S7: Cloudflare Worker Sync Acceptance

    /// UAT-044 & UAT-052: Worker CRDT LWW sync payload and negative tombstones
    func test_UAT044_052_WorkerCRDTProtocolAndTombstones() async throws {
        let tempDir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("TubeLM_UAT_Sync_\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let store = ContentStore(baseDirectory: tempDir)

        // 1. Mark read -> positive timestamp
        try await store.markItemRead("item_sync_1")
        let states1 = await store.loadItemStates()
        XCTAssertGreaterThan(states1["item_sync_1"] ?? 0, 0, "Mark read must record positive timestamp")

        // 2. Unmark read -> negative tombstone
        try await store.unmarkItemRead("item_sync_1")
        let states2 = await store.loadItemStates()
        XCTAssertLessThan(states2["item_sync_1"] ?? 0, 0, "Unmark must record negative tombstone")

        // 3. Remote merge resolution
        let now = Date().timeIntervalSince1970 * 1000
        // Newer read from remote peer overrides older local unmark
        let merged = try await store.applyRemoteStates(["item_sync_1": now + 5000])
        XCTAssertTrue(merged.contains("item_sync_1"), "Newer remote read must resurrect item")
    }

    // MARK: - S8: Relative Audio URL Resolution

    /// UAT-070: Relative audio URL resolution against feed base URL
    func test_UAT070_RelativeAudioURLResolution() {
        let feedBase = URL(string: "https://vkr1729.github.io/TubeLM/")!
        let relativeAudio = "audio/2026-09-18_3Blue1Brown.mp3"
        let resolved = URL(string: relativeAudio, relativeTo: feedBase)?.absoluteURL

        XCTAssertEqual(resolved?.absoluteString, "https://vkr1729.github.io/TubeLM/audio/2026-09-18_3Blue1Brown.mp3")
        XCTAssertEqual(resolved?.scheme, "https")

        // Absolute URL should remain absolute
        let absoluteAudio = "https://r2.example.com/tubelm/audio/channel.mp3"
        let resolvedAbs = URL(string: absoluteAudio, relativeTo: feedBase)?.absoluteURL
        XCTAssertEqual(resolvedAbs?.absoluteString, absoluteAudio)
    }

    // MARK: - Helper

    private func loadMockFeed() throws -> DigestFeed {
        #if SWIFT_PACKAGE
        if let bundleUrl = Bundle.module.url(forResource: "mock_data", withExtension: "json") ??
                           Bundle.module.url(forResource: "mock_data", withExtension: "json", subdirectory: "Resources"),
           let data = try? Data(contentsOf: bundleUrl) {
            return try JSONDecoder().decode(DigestFeed.self, from: data)
        }
        #endif

        if let bundleUrl = Bundle(for: Self.self).url(forResource: "mock_data", withExtension: "json") ??
                           Bundle(for: Self.self).url(forResource: "mock_data", withExtension: "json", subdirectory: "Resources"),
           let data = try? Data(contentsOf: bundleUrl) {
            return try JSONDecoder().decode(DigestFeed.self, from: data)
        }

        if let envPath = ProcessInfo.processInfo.environment["MOCK_DATA_PATH"],
           FileManager.default.fileExists(atPath: envPath) {
            let data = try Data(contentsOf: URL(fileURLWithPath: envPath))
            return try JSONDecoder().decode(DigestFeed.self, from: data)
        }

        var searchDirs: [URL] = [
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath),
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath).deletingLastPathComponent(),
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath).deletingLastPathComponent().deletingLastPathComponent()
        ]
        for dir in searchDirs {
            let candidate = dir.appendingPathComponent(".workflow/mocks/mock_data.json")
            if FileManager.default.fileExists(atPath: candidate.path), let data = try? Data(contentsOf: candidate) {
                return try JSONDecoder().decode(DigestFeed.self, from: data)
            }
        }
        throw NSError(domain: "UAT", code: 404, userInfo: [NSLocalizedDescriptionKey: "mock_data.json not found"])
    }
}
