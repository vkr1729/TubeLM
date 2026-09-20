import XCTest
@testable import TubeLMCore

final class SyncIdentityTests: XCTestCase {

    func testNormalizeVideoUrlVectors() {
        // YouTube watch URL with v param
        XCTAssertEqual(
            SyncIdentity.normalizeVideoUrl("https://www.youtube.com/watch?v=J3ljHm57yU0"),
            "J3ljHm57yU0"
        )
        // YouTube watch URL with additional query params
        XCTAssertEqual(
            SyncIdentity.normalizeVideoUrl("https://www.youtube.com/watch?v=J3ljHm57yU0&t=42s"),
            "J3ljHm57yU0"
        )
        // youtu.be short URL
        XCTAssertEqual(
            SyncIdentity.normalizeVideoUrl("https://youtu.be/J3ljHm57yU0"),
            "J3ljHm57yU0"
        )
        // YouTube shorts URL
        XCTAssertEqual(
            SyncIdentity.normalizeVideoUrl("https://www.youtube.com/shorts/J3ljHm57yU0"),
            "shorts/J3ljHm57yU0"
        )
        // RSS / Article URL (origin + pathname)
        XCTAssertEqual(
            SyncIdentity.normalizeVideoUrl("https://www.technologyreview.com/2026/09/18/1144435/could-ai-really-kill-us-all/?utm_source=feed"),
            "https://www.technologyreview.com/2026/09/18/1144435/could-ai-really-kill-us-all/"
        )
        // Empty or whitespace
        XCTAssertEqual(SyncIdentity.normalizeVideoUrl(""), "")
        XCTAssertEqual(SyncIdentity.normalizeVideoUrl(nil), "")
        XCTAssertEqual(SyncIdentity.normalizeVideoUrl("   "), "")
    }

    func testAliasesGeneration() {
        let aliases = SyncIdentity.aliases(
            id: "item-001",
            videoId: "J3ljHm57yU0",
            url: "https://www.youtube.com/watch?v=J3ljHm57yU0"
        )
        XCTAssertTrue(aliases.contains("item-001"))
        XCTAssertTrue(aliases.contains("J3ljHm57yU0"))
        XCTAssertTrue(aliases.contains("https://www.youtube.com/watch?v=J3ljHm57yU0"))

        // RSS item without videoId
        let rssAliases = SyncIdentity.aliases(
            id: "b491d63c1a336d84",
            videoId: "",
            url: "https://www.technologyreview.com/article"
        )
        XCTAssertTrue(rssAliases.contains("b491d63c1a336d84"))
        XCTAssertTrue(rssAliases.contains("https://www.technologyreview.com/article"))
    }

    func testIsItemReadWithAliases() {
        let aliases: Set<String> = ["item-001", "J3ljHm57yU0", "https://youtube.com/watch?v=J3ljHm57yU0"]
        let readIDs: Set<String> = ["J3ljHm57yU0"]

        XCTAssertTrue(SyncIdentity.isItemRead(aliases: aliases, in: readIDs))

        let otherReadIDs: Set<String> = ["other-id"]
        XCTAssertFalse(SyncIdentity.isItemRead(aliases: aliases, in: otherReadIDs))
    }
}
