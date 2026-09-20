import Foundation

public struct QueueItem: Codable, Identifiable, Sendable, Equatable {
    public let id: String
    public let title: String
    public let sourceName: String
    public let duration: String
    public let audioUrl: String?

    public init(
        id: String,
        title: String,
        sourceName: String,
        duration: String,
        audioUrl: String? = nil
    ) {
        self.id = id
        self.title = title
        self.sourceName = sourceName
        self.duration = duration
        self.audioUrl = audioUrl
    }
}

public struct CommuteQueueModel: Sendable {
    public private(set) var items: [QueueItem]

    public init(items: [QueueItem] = []) {
        self.items = items
    }

    public var count: Int { items.count }
    public var isEmpty: Bool { items.isEmpty }

    public mutating func enqueue(_ item: QueueItem) {
        if !items.contains(where: { $0.id == item.id }) {
            items.append(item)
        }
    }

    public mutating func remove(id: String) {
        items.removeAll(where: { $0.id == id })
    }

    public mutating func move(fromOffsets source: IndexSet, toOffset destination: Int) {
        let valid = source.filter { $0 >= 0 && $0 < items.count }.sorted()
        guard !valid.isEmpty else { return }
        let movingItems = valid.map { items[$0] }
        var newItems = items
        for index in valid.reversed() {
            newItems.remove(at: index)
        }
        var targetIndex = destination
        for offset in valid where offset < destination {
            targetIndex -= 1
        }
        targetIndex = max(0, min(targetIndex, newItems.count))
        newItems.insert(contentsOf: movingItems, at: targetIndex)
        self.items = newItems
    }

    public mutating func clear() {
        items.removeAll()
    }

    /// Dynamically calculates unwatched summaries for a channel, matching on
    /// any alias (id, video_id, url, normalized URL) so web/app keys converge.
    public static func unwatchedVideos(for channel: Channel, readIDs: Set<String>) -> [VideoItem] {
        return channel.videos.filter { $0.aliases.intersection(readIDs).isEmpty }
    }

    /// Computes the playback target for a channel based on read state.
    public static func resolveChannelPlayback(
        for channel: Channel,
        readIDs: Set<String>
    ) -> (title: String, itemsToPlay: [VideoItem], audioUrl: String?) {
        func playable(_ raw: String?) -> String? {
            guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !trimmed.isEmpty else { return nil }
            return trimmed
        }
        let audioFallback = playable(channel.summaryAudioUrl) ?? playable(channel.audioUrl)
        let unwatched = unwatchedVideos(for: channel, readIDs: readIDs)
        if !unwatched.isEmpty {
            return (
                title: "Unwatched Summaries (\(unwatched.count))",
                itemsToPlay: unwatched,
                audioUrl: unwatched.lazy.compactMap { playable($0.audioUrl) }.first ?? audioFallback
            )
        } else {
            return (
                title: "Channel Overview",
                itemsToPlay: channel.videos,
                audioUrl: audioFallback
            )
        }
    }
}
