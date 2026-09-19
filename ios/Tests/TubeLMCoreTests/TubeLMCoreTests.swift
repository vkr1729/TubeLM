import XCTest
@testable import TubeLMCore

final class TubeLMCoreTests: XCTestCase {

    func testDigestFeedDecodingFromMockData() throws {
        var data: Data?
        #if SWIFT_PACKAGE
        if let bundleUrl = Bundle.module.url(forResource: "mock_data", withExtension: "json") ??
                           Bundle.module.url(forResource: "mock_data", withExtension: "json", subdirectory: "Resources") {
            data = try? Data(contentsOf: bundleUrl)
        }
        #endif

        if data == nil {
            if let bundleUrl = Bundle(for: Self.self).url(forResource: "mock_data", withExtension: "json") ??
                               Bundle(for: Self.self).url(forResource: "mock_data", withExtension: "json", subdirectory: "Resources") {
                data = try? Data(contentsOf: bundleUrl)
            }
        }

        if data == nil, let envPath = ProcessInfo.processInfo.environment["MOCK_DATA_PATH"], FileManager.default.fileExists(atPath: envPath) {
            data = try? Data(contentsOf: URL(fileURLWithPath: envPath))
        }

        if data == nil {
            var searchDirs: [URL] = [
                URL(fileURLWithPath: FileManager.default.currentDirectoryPath),
                URL(fileURLWithPath: FileManager.default.currentDirectoryPath).deletingLastPathComponent(),
                URL(fileURLWithPath: FileManager.default.currentDirectoryPath).deletingLastPathComponent().deletingLastPathComponent()
            ]
            for dir in searchDirs {
                let candidate = dir.appendingPathComponent(".workflow/mocks/mock_data.json")
                if FileManager.default.fileExists(atPath: candidate.path) {
                    data = try? Data(contentsOf: candidate)
                    if data != nil { break }
                }
            }
        }

        guard let validData = data else {
            XCTFail("mock_data.json could not be loaded via bundle, environment, or file path")
            return
        }

        let feed = try JSONDecoder().decode(DigestFeed.self, from: validData)

        XCTAssertEqual(feed.schemaVersion, 1)
        XCTAssertEqual(feed.top20.items.count, 20)
        XCTAssertEqual(feed.channels.count, 23)

        // Check first item
        let first = feed.top20.items[0]
        XCTAssertFalse(first.id.isEmpty)
        XCTAssertEqual(first.rank, 1)
        XCTAssertFalse(first.title.isEmpty)

        // Check MIT Technology Review in channels
        let mit = feed.channels.first(where: { $0.name.contains("MIT") })
        XCTAssertNotNil(mit)
        XCTAssertEqual(mit?.videos.count, 6)
        for v in mit?.videos ?? [] {
            XCTAssertFalse(v.id.isEmpty)
        }
    }

    func testContentStoreTwoTierAndLRUCap() async throws {
        let tempDir = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("TubeLMTest-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let store = ContentStore(baseDirectory: tempDir)

        // 1. Test Feed Cache
        let dummyFeed = DigestFeed(
            schemaVersion: 1,
            runDate: "2026-09-18",
            top20: Top20Container(items: [
                FeedItem(id: "item_1", rank: 1, title: "Test Video", sourceName: "Test", sourceType: "youtube")
            ]),
            channels: []
        )
        try await store.saveFeed(dummyFeed)
        let loadedFeed = try await store.loadCachedFeed()
        XCTAssertEqual(loadedFeed?.schemaVersion, 1)
        XCTAssertEqual(loadedFeed?.top20.items.count, 1)

        // 2. Test Bookmarks (Pinned)
        let bItem = FeedItem(id: "bm_1", rank: nil, title: "Saved Deep Explainer", sourceName: "3Blue1Brown")
        try await store.saveBookmark(bItem)
        let bookmarks = await store.loadBookmarks()
        XCTAssertEqual(bookmarks.count, 1)
        XCTAssertEqual(bookmarks.first?.id, "bm_1")

        try await store.removeBookmark(id: "bm_1")
        let afterRemove = await store.loadBookmarks()
        XCTAssertTrue(afterRemove.isEmpty)

        // 3. Test LRU Read IDs Cap
        for i in 1...100 {
            try await store.markItemRead("read_\(i)")
        }
        let readIDs = await store.loadReadIDs()
        XCTAssertEqual(readIDs.count, 100)
        XCTAssertTrue(readIDs.contains("read_100"))

        // 4. Test unmark tombstone path (was: unmark impossible, read set append-only)
        try await store.unmarkItemRead("read_100")
        let afterUnmark = await store.loadReadIDs()
        XCTAssertFalse(afterUnmark.contains("read_100"))
        let states = await store.loadItemStates()
        XCTAssertLessThan(states["read_100"] ?? 0, 0)

        // 5. Test remote merge: newer tombstone removes, newer read adds
        let merged = try await store.applyRemoteStates(["read_99": -Date().timeIntervalSince1970 * 1000 - 1000,
                                                        "fresh_remote": Date().timeIntervalSince1970 * 1000 + 1000])
        XCTAssertFalse(merged.contains("read_99"))
        XCTAssertTrue(merged.contains("fresh_remote"))

        // 6. Test non-finite timestamps are rejected, not persisted
        try await store.saveItemStates(["bad": Double.nan, "inf": Double.infinity, "good": 123])
        let cleaned = await store.loadItemStates()
        XCTAssertNil(cleaned["bad"])
        XCTAssertNil(cleaned["inf"])
        XCTAssertEqual(cleaned["good"], 123)
    }

    func testCommuteQueueMathAndUnwatchedFiltering() {
        var queue = CommuteQueueModel()
        XCTAssertTrue(queue.isEmpty)

        queue.enqueue(QueueItem(id: "1", title: "Audio 1", sourceName: "Ch 1", duration: "10m"))
        queue.enqueue(QueueItem(id: "2", title: "Audio 2", sourceName: "Ch 2", duration: "12m"))
        XCTAssertEqual(queue.count, 2)

        // Prevent duplicate enqueue
        queue.enqueue(QueueItem(id: "1", title: "Audio 1", sourceName: "Ch 1", duration: "10m"))
        XCTAssertEqual(queue.count, 2)

        queue.remove(id: "1")
        XCTAssertEqual(queue.count, 1)
        XCTAssertEqual(queue.items.first?.id, "2")

        // Unwatched Channel Filter test
        let channel = Channel(
            id: "mit",
            name: "MIT Tech Review",
            videos: [
                VideoItem(id: "v1", title: "Video 1"),
                VideoItem(id: "v2", title: "Video 2"),
                VideoItem(id: "v3", title: "Video 3")
            ]
        )

        // Case A: 1 item watched
        let readIDs: Set<String> = ["v1"]
        let targetA = CommuteQueueModel.resolveChannelPlayback(for: channel, readIDs: readIDs)
        XCTAssertEqual(targetA.itemsToPlay.count, 2)
        XCTAssertEqual(targetA.title, "Unwatched Summaries (2)")

        // Case B: all items watched
        let allRead: Set<String> = ["v1", "v2", "v3"]
        let targetB = CommuteQueueModel.resolveChannelPlayback(for: channel, readIDs: allRead)
        XCTAssertEqual(targetB.itemsToPlay.count, 3)
        XCTAssertEqual(targetB.title, "Channel Overview")
    }

    func testSyncPayloadMatchesWorkerContract() throws {
        let bm = FeedItem(id: "bm_1", rank: 1, title: "Bookmark 1", sourceName: "Source 1")
        let payload = SyncPayload(
            readIds: ["a"],
            top20Read: ["b"],
            itemStates: ["a": 123.0, "c": -456.0],
            bookmarks: [bm],
            bookmarkStates: ["bm_1": 1000.0]
        )
        let data = try JSONEncoder().encode(payload)
        let keys = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        XCTAssertNotNil(keys?["read_ids"])
        XCTAssertNotNil(keys?["top20_read"])
        XCTAssertNotNil(keys?["item_states"])
        XCTAssertNotNil(keys?["bookmarks"])
        XCTAssertNotNil(keys?["bookmark_states"])
        XCTAssertNil(keys?["client_id"])
        XCTAssertNil(keys?["merged_item_states"])

        let workerGET = """
        {"read_ids": ["a"], "top20_read": ["b"], "item_states": {"a": 123}, "bookmarks": [{"id": "bm_1", "title": "B1", "source_name": "S1", "source_type": "youtube"}], "bookmark_states": {"bm_1": 1000}, "updated_at": "2026-09-19T00:00:00.000Z"}
        """.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(SyncResponse.self, from: workerGET)
        XCTAssertEqual(decoded.readIds, ["a"])
        XCTAssertEqual(decoded.top20Read, ["b"])
        XCTAssertEqual(decoded.itemStates["a"], 123)
        XCTAssertEqual(decoded.bookmarks.count, 1)
        XCTAssertEqual(decoded.bookmarks[0].id, "bm_1")
        XCTAssertEqual(decoded.bookmarkStates["bm_1"], 1000)

        let emptyGET = """
        {"read_ids": [], "top20_read": [], "item_states": {}, "bookmarks": [], "bookmark_states": {}, "updated_at": null, "message": "No remote state yet for this key"}
        """.data(using: .utf8)!
        let empty = try JSONDecoder().decode(SyncResponse.self, from: emptyGET)
        XCTAssertTrue(empty.readIds.isEmpty)
        XCTAssertTrue(empty.itemStates.isEmpty)
        XCTAssertTrue(empty.bookmarks.isEmpty)
        XCTAssertTrue(empty.bookmarkStates.isEmpty)
    }

    func testQueueMoveIgnoresOutOfBoundsIndices() {
        var queue = CommuteQueueModel(items: [
            QueueItem(id: "1", title: "A", sourceName: "S", duration: "1m"),
            QueueItem(id: "2", title: "B", sourceName: "S", duration: "1m"),
        ])
        queue.move(fromOffsets: IndexSet(integer: 9), toOffset: 0)
        XCTAssertEqual(queue.items.map { $0.id }, ["1", "2"])
        queue.move(fromOffsets: IndexSet(integer: 0), toOffset: 2)
        XCTAssertEqual(queue.items.map { $0.id }, ["2", "1"])
    }

    func testCategoryLabelMapsPipelineValuesToSpecPills() {
        func label(_ raw: String) -> String {
            Channel(id: "c", name: "C", category: raw).categoryLabel
        }
        XCTAssertEqual(label("tech"), "Tech & AI")
        XCTAssertEqual(label("health"), "Health & Bio")
        XCTAssertEqual(label("deep_explainer"), "Science & Deep")
        XCTAssertEqual(label("news_feed"), "News")
        XCTAssertEqual(label("science"), "Science & Deep")
    }

    func testChannelPlaybackSkipsEmptyAudioStrings() {
        let channel = Channel(
            id: "c",
            name: "C",
            summaryAudioUrl: "",
            audioUrl: "audio/real.mp3",
            videos: [VideoItem(id: "v1", title: "V1", audioUrl: "  ")]
        )
        let resolved = CommuteQueueModel.resolveChannelPlayback(for: channel, readIDs: [])
        XCTAssertEqual(resolved.audioUrl, "audio/real.mp3")
    }
}
