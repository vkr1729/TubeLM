import Foundation

public enum FeedPartition: Sendable {
    /// Stable partition preserving relative order of unread items first, followed by read items.
    public static func unreadFirst<T: Identifiable>(
        items: [T],
        isRead: (T) -> Bool
    ) -> [T] {
        let unread = items.filter { !isRead($0) }
        let read = items.filter { isRead($0) }
        return unread + read
    }
}
