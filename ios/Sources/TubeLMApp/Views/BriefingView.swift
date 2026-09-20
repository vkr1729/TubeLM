#if canImport(SwiftUI)
import SwiftUI
import TubeLMCore

public struct BriefingView: View {
    public let items: [FeedItem]
    public let readIDs: Set<String>
    public let onMarkRead: (FeedItem) -> Void
    public let onPlayAudio: (FeedItem) -> Void
    public let onEnqueue: (FeedItem) -> Void
    public let onToggleBookmark: (FeedItem) -> Void
    public let isBookmarked: (String) -> Bool

    public init(
        items: [FeedItem],
        readIDs: Set<String>,
        onMarkRead: @escaping (FeedItem) -> Void,
        onPlayAudio: @escaping (FeedItem) -> Void,
        onEnqueue: @escaping (FeedItem) -> Void,
        onToggleBookmark: @escaping (FeedItem) -> Void,
        isBookmarked: @escaping (String) -> Bool
    ) {
        self.items = items
        self.readIDs = readIDs
        self.onMarkRead = onMarkRead
        self.onPlayAudio = onPlayAudio
        self.onEnqueue = onEnqueue
        self.onToggleBookmark = onToggleBookmark
        self.isBookmarked = isBookmarked
    }

    public var body: some View {
        Group {
            if items.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "newspaper")
                        .font(.system(size: 40))
                        .foregroundColor(.secondary)
                    Text("No Briefing Yet")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundColor(.primary)
                    Text("Connect to refresh the weekly digest. Your saved state stays on this device.")
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else {
                let top20 = Array(items.prefix(20))
                let partitioned = FeedPartition.unreadFirst(items: top20) { item in
                    !item.aliases.intersection(readIDs).isEmpty
                }

                ScrollView {
                    LazyVStack(spacing: 12) {
                        ForEach(partitioned, id: \.id) { item in
                            let rank = itemRank(item, in: top20)
                            let isRead = !item.aliases.intersection(readIDs).isEmpty
                            let bookmarked = isBookmarked(item.id)

                            VStack(alignment: .leading, spacing: 10) {
                                // Card Top Line
                                HStack {
                                    Text("#\(rank)")
                                        .font(AppTheme.rankBadge)
                                        .padding(.horizontal, 7)
                                        .padding(.vertical, 3)
                                        .background(isRead ? AppTheme.secondarySystemBackground : AppTheme.accentBadge)
                                        .foregroundColor(isRead ? .secondary : AppTheme.accentBadgeText)
                                        .cornerRadius(6)

                                    if isRead {
                                        Text("✓ Watched")
                                            .font(.system(size: 10, weight: .bold))
                                            .foregroundColor(AppTheme.accent)
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(AppTheme.accent.opacity(0.12))
                                            .clipShape(Capsule())
                                    }

                                    Spacer()

                                    HStack(spacing: 6) {
                                        Text(item.sourceName)
                                        if let duration = item.duration, !duration.isEmpty {
                                            Text("·")
                                            Text(duration)
                                        }
                                    }
                                    .font(AppTheme.meta)
                                    .foregroundColor(.secondary)
                                }

                                // Title (Tap opens link and auto-marks watched)
                                Text(item.title)
                                    .font(AppTheme.title)
                                    .foregroundColor(.primary)
                                    .lineLimit(3)
                                    .onTapGesture {
                                        openLink(item)
                                    }

                                // Why It Matters Box
                                if let why = item.whyItMatters, !why.isEmpty {
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text("WHY IT MATTERS")
                                            .font(.system(size: 10, weight: .bold))
                                            .foregroundColor(AppTheme.accent)
                                        Text(why)
                                            .font(AppTheme.whyText)
                                            .foregroundColor(.primary)
                                    }
                                    .padding(10)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(AppTheme.whyBackgroundLight)
                                    .overlay(
                                        Rectangle()
                                            .frame(width: 3)
                                            .foregroundColor(AppTheme.whyBorder),
                                        alignment: .leading
                                    )
                                    .cornerRadius(8)
                                }

                                // Actions
                                HStack {
                                    Button(action: {
                                        withAnimation(.easeInOut(duration: 0.25)) {
                                            onMarkRead(item)
                                        }
                                        onPlayAudio(item)
                                    }) {
                                        HStack(spacing: 5) {
                                            Image(systemName: "play.fill")
                                                .font(.system(size: 10))
                                            Text("Play")
                                                .font(.system(size: 12, weight: .bold))
                                        }
                                        .padding(.horizontal, 14)
                                        .padding(.vertical, 6)
                                        .background(AppTheme.accent.opacity(0.12))
                                        .foregroundColor(AppTheme.accent)
                                        .clipShape(Capsule())
                                    }

                                    Spacer()

                                    HStack(spacing: 8) {
                                        Button(action: { openLink(item) }) {
                                            HStack(spacing: 4) {
                                                Image(systemName: item.isArticle ? "doc.text" : "play.rectangle")
                                                Text(item.actionLabel)
                                            }
                                            .font(AppTheme.actionButton)
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 6)
                                            .background(AppTheme.secondarySystemBackground)
                                            .foregroundColor(.primary)
                                            .cornerRadius(8)
                                        }

                                        Button(action: { onEnqueue(item) }) {
                                            Text("+ Queue")
                                                .font(AppTheme.actionButton)
                                                .padding(.horizontal, 10)
                                                .padding(.vertical, 6)
                                                .background(AppTheme.secondarySystemBackground)
                                                .foregroundColor(.primary)
                                                .cornerRadius(8)
                                        }

                                        Button(action: { onToggleBookmark(item) }) {
                                            Image(systemName: bookmarked ? "bookmark.fill" : "bookmark")
                                                .font(.system(size: 12))
                                                .padding(8)
                                                .background(AppTheme.secondarySystemBackground)
                                                .foregroundColor(bookmarked ? AppTheme.accent : .primary)
                                                .cornerRadius(8)
                                        }
                                    }
                                }
                                .padding(.top, 4)
                            }
                            .padding(16)
                            .background(AppTheme.systemBackground)
                            .cornerRadius(18)
                            .shadow(color: Color.black.opacity(0.04), radius: 6, x: 0, y: 2)
                            .opacity(isRead ? 0.45 : 1.0)
                            .padding(.horizontal, 16)
                        }
                    }
                    .padding(.top, 12)
                    .padding(.bottom, 120) // Space for sticky mini-player
                }
            }
        }
    }

    private func openLink(_ item: FeedItem) {
        withAnimation(.easeInOut(duration: 0.25)) {
            onMarkRead(item)
        }
        if let urlStr = item.url,
           let url = URL(string: urlStr),
           url.scheme == "http" || url.scheme == "https" {
            #if canImport(UIKit)
            UIApplication.shared.open(url)
            #endif
        }
    }

    private func itemRank(_ item: FeedItem, in top20: [FeedItem]) -> Int {
        if let r = item.rank { return r }
        if let idx = top20.firstIndex(where: { $0.id == item.id }) {
            return idx + 1
        }
        return 1
    }
}
#endif
