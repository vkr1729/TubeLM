import XCTest
@testable import TubeLMCore

final class FeedPartitionTests: XCTestCase {

    struct MockItem: Identifiable, Equatable {
        let id: String
        let rank: Int
    }

    func testUnreadFirstPartition() {
        let items = [
            MockItem(id: "1", rank: 1),
            MockItem(id: "2", rank: 2),
            MockItem(id: "3", rank: 3),
            MockItem(id: "4", rank: 4),
            MockItem(id: "5", rank: 5)
        ]

        // Mark item 1 and 3 as read
        let readIDs: Set<String> = ["1", "3"]
        let partitioned = FeedPartition.unreadFirst(items: items) { readIDs.contains($0.id) }

        // Expected: unread items (2, 4, 5) preserved in original relative order,
        // followed by read items (1, 3) in original relative order.
        XCTAssertEqual(partitioned.map(\.id), ["2", "4", "5", "1", "3"])

        // Original rank values remain intact
        XCTAssertEqual(partitioned.map(\.rank), [2, 4, 5, 1, 3])
    }

    func testAllUnreadPartition() {
        let items = [
            MockItem(id: "1", rank: 1),
            MockItem(id: "2", rank: 2)
        ]
        let partitioned = FeedPartition.unreadFirst(items: items) { _ in false }
        XCTAssertEqual(partitioned.map(\.id), ["1", "2"])
    }

    func testAllReadPartition() {
        let items = [
            MockItem(id: "1", rank: 1),
            MockItem(id: "2", rank: 2)
        ]
        let partitioned = FeedPartition.unreadFirst(items: items) { _ in true }
        XCTAssertEqual(partitioned.map(\.id), ["1", "2"])
    }

    func testEmptyPartition() {
        let items: [MockItem] = []
        let partitioned = FeedPartition.unreadFirst(items: items) { _ in false }
        XCTAssertTrue(partitioned.isEmpty)
    }
}
