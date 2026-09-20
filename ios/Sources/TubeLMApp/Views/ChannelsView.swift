#if canImport(SwiftUI)
import SwiftUI
import TubeLMCore

public struct ChannelsView: View {
    public let channels: [Channel]
    public let readIDs: Set<String>
    public let onMarkRead: (VideoItem) -> Void
    public let onToggleRead: (VideoItem) -> Void
    public let onPlayChannel: (Channel) -> Void
    public let onEnqueueItem: (QueueItem) -> Void
    public let onToggleBookmark: (FeedItem) -> Void

    @State private var searchText: String = ""
    @State private var expandedChannels: Set<String> = []

    public init(
        channels: [Channel],
        readIDs: Set<String>,
        onMarkRead: @escaping (VideoItem) -> Void,
        onToggleRead: @escaping (VideoItem) -> Void,
        onPlayChannel: @escaping (Channel) -> Void,
        onEnqueueItem: @escaping (QueueItem) -> Void,
        onToggleBookmark: @escaping (FeedItem) -> Void
    ) {
        self.channels = channels
        self.readIDs = readIDs
        self.onMarkRead = onMarkRead
        self.onToggleRead = onToggleRead
        self.onPlayChannel = onPlayChannel
        self.onEnqueueItem = onEnqueueItem
        self.onToggleBookmark = onToggleBookmark
    }

    var filteredChannels: [Channel] {
        if searchText.trimmingCharacters(in: .whitespaces).isEmpty {
            return channels
        }
        return channels.filter {
            $0.name.localizedCaseInsensitiveContains(searchText) ||
            $0.category.localizedCaseInsensitiveContains(searchText)
        }
    }

    public var body: some View {
        VStack(spacing: 0) {
            // Search Input
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)
                TextField("Search channels...", text: $searchText)
                    .font(.system(size: 14))
            }
            .padding(10)
            .background(AppTheme.secondarySystemBackground)
            .cornerRadius(12)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)

            // Channels List
            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(filteredChannels) { channel in
                        let isExpanded = expandedChannels.contains(channel.id)
                        let watchedCount = channel.videos.filter { ! $0.aliases.intersection(readIDs).isEmpty }.count
                        let totalCount = channel.videos.count
                        let isCompleted = totalCount > 0 && watchedCount == totalCount

                        VStack(alignment: .leading, spacing: 10) {
                            // Channel Header (Tap to expand/collapse)
                            HStack(alignment: .center, spacing: 12) {
                                Text(channel.initials)
                                    .font(.system(size: 14, weight: .bold))
                                    .foregroundColor(AppTheme.accent)
                                    .frame(width: 42, height: 42)
                                    .background(AppTheme.secondarySystemBackground)
                                    .cornerRadius(12)

                                VStack(alignment: .leading, spacing: 3) {
                                    HStack {
                                        Text(channel.name)
                                            .font(.system(size: 15, weight: .bold))
                                            .foregroundColor(.primary)
                                            .lineLimit(1)
                                        Spacer()
                                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                                            .font(.system(size: 12, weight: .semibold))
                                            .foregroundColor(.secondary)
                                    }

                                    HStack(spacing: 6) {
                                        Text(channel.categoryLabel)
                                            .font(.system(size: 10, weight: .bold))
                                            .foregroundColor(AppTheme.accent)
                                            .padding(.horizontal, 7)
                                            .padding(.vertical, 2)
                                            .background(AppTheme.accent.opacity(0.12))
                                            .clipShape(Capsule())
                                        Text(isCompleted ? "✓ Channel Completed" : "\(watchedCount)/\(totalCount) Completed")
                                            .font(.system(size: 11, weight: .semibold))
                                            .foregroundColor(isCompleted ? AppTheme.accent : .primary)
                                        if let minutes = channel.readMinutes, minutes > 0 {
                                            Text("·")
                                            Text("\(minutes)m")
                                                .font(.system(size: 11))
                                                .foregroundColor(.secondary)
                                        }
                                    }
                                }
                            }
                            .contentShape(Rectangle())
                            .onTapGesture {
                                toggleExpand(channel.id)
                            }

                            // Summary Preview Box
                            if let summary = channel.summaryText, !summary.isEmpty {
                                Text(summary.prefix(200) + (summary.count > 200 ? "..." : ""))
                                    .font(.system(size: 12))
                                    .foregroundColor(.secondary)
                                    .lineSpacing(2)
                                    .padding(10)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(AppTheme.secondarySystemBackground)
                                    .cornerRadius(10)
                            }

                            // Compact Action Bar (User feedback: Proportional 'Listen' pill, not an oversized bar!)
                            HStack(spacing: 8) {
                                Button(action: { onPlayChannel(channel) }) {
                                    HStack(spacing: 5) {
                                        Image(systemName: "play.fill")
                                            .font(.system(size: 10))
                                        Text("Listen")
                                            .font(.system(size: 12, weight: .bold))
                                    }
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 7)
                                    .background(AppTheme.accentBadge)
                                    .foregroundColor(AppTheme.accentBadgeText)
                                    .clipShape(Capsule())
                                }

                                Button(action: {
                                    let totalSeconds = channel.videos.compactMap { $0.durationSeconds }.filter { $0 > 0 }.reduce(0, +)
                                    let durationLabel: String
                                    if totalSeconds > 0 {
                                        durationLabel = "\(totalSeconds / 60)m"
                                    } else if let minutes = channel.readMinutes, minutes > 0 {
                                        durationLabel = "\(minutes)m"
                                    } else {
                                        durationLabel = ""
                                    }
                                    let item = QueueItem(
                                        id: "ch_\(channel.id)",
                                        title: "\(channel.name) (\(totalCount) Items)",
                                        sourceName: channel.name,
                                        duration: durationLabel,
                                        audioUrl: channel.summaryAudioUrl ?? channel.audioUrl
                                    )
                                    onEnqueueItem(item)
                                }) {
                                    Text("+ Queue")
                                        .font(.system(size: 11, weight: .bold))
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 7)
                                        .background(AppTheme.secondarySystemBackground)
                                        .foregroundColor(.primary)
                                        .cornerRadius(8)
                                }

                                Spacer()
                            }
                            .padding(.top, 4)

                            // Expanded Video Items Panel
                            if isExpanded {
                                var originalVideoIndices: [String: Int] = [:]
                                for (offset, element) in channel.videos.enumerated() {
                                    originalVideoIndices[element.id] = originalVideoIndices[element.id] ?? (offset + 1)
                                }
                                let partitionedVideos = FeedPartition.unreadFirst(items: channel.videos) { vid in
                                    !vid.aliases.intersection(readIDs).isEmpty
                                }

                                VStack(spacing: 10) {
                                    ForEach(partitionedVideos, id: \.id) { vid in
                                        let vIdx = originalVideoIndices[vid.id] ?? 1
                                        let isVidRead = !vid.aliases.intersection(readIDs).isEmpty

                                        VStack(alignment: .leading, spacing: 6) {
                                            HStack(alignment: .top, spacing: 8) {
                                                Button(action: {
                                                    withAnimation(.easeInOut(duration: 0.25)) {
                                                        onToggleRead(vid)
                                                    }
                                                }) {
                                                    Image(systemName: isVidRead ? "checkmark.square.fill" : "square")
                                                        .foregroundColor(isVidRead ? AppTheme.accent : .secondary)
                                                        .font(.system(size: 16))
                                                }

                                                Text("\(vIdx). \(vid.title)")
                                                    .font(AppTheme.subcardTitle)
                                                    .foregroundColor(.primary)
                                                    .onTapGesture {
                                                        openVideoLink(vid)
                                                    }

                                                Spacer()

                                                if let duration = vid.duration, !duration.isEmpty {
                                                    Text(duration)
                                                        .font(AppTheme.durationBadge)
                                                        .foregroundColor(.secondary)
                                                }
                                            }

                                            // Formatted Markdown Overview
                                            if let summaryHtml = vid.summaryHtml ?? vid.lead {
                                                MarkdownView(summaryHtml)
                                                    .padding(.leading, 24)
                                                    .padding(.vertical, 4)
                                            }

                                            // Subcard Actions
                                            HStack {
                                                Spacer()
                                                Button(action: { openVideoLink(vid) }) {
                                                    HStack(spacing: 3) {
                                                        Image(systemName: vid.isArticle ? "doc.text" : "play.rectangle")
                                                        Text(vid.actionLabel)
                                                    }
                                                    .font(.system(size: 11, weight: .bold))
                                                    .foregroundColor(AppTheme.accent)
                                                }

                                                Button(action: {
                                                    let qItem = QueueItem(
                                                        id: vid.id,
                                                        title: vid.title,
                                                        sourceName: channel.name,
                                                        duration: vid.duration ?? "",
                                                        audioUrl: vid.audioUrl
                                                    )
                                                    onEnqueueItem(qItem)
                                                }) {
                                                    Text("+ Queue")
                                                        .font(.system(size: 10, weight: .bold))
                                                        .padding(.horizontal, 8)
                                                        .padding(.vertical, 4)
                                                        .background(AppTheme.tertiarySystemBackground)
                                                        .cornerRadius(6)
                                                }

                                                Button(action: {
                                                    let fItem = FeedItem(
                                                        id: vid.id,
                                                        videoId: vid.videoId,
                                                        title: vid.title,
                                                        sourceName: channel.name,
                                                        sourceType: vid.sourceType ?? "youtube",
                                                        duration: vid.duration,
                                                        whyItMatters: vid.lead,
                                                        url: vid.url,
                                                        audioUrl: vid.audioUrl
                                                    )
                                                    onToggleBookmark(fItem)
                                                }) {
                                                    Image(systemName: "bookmark")
                                                        .font(.system(size: 11))
                                                        .padding(5)
                                                        .background(AppTheme.tertiarySystemBackground)
                                                        .cornerRadius(6)
                                                }
                                            }
                                            .padding(.leading, 24)
                                        }
                                        .padding(10)
                                        .background(AppTheme.secondarySystemBackground)
                                        .cornerRadius(12)
                                        .opacity(isVidRead ? 0.45 : 1.0)
                                    }
                                }
                                .padding(.top, 6)
                            }
                        }
                        .padding(14)
                        .background(AppTheme.systemBackground)
                        .cornerRadius(16)
                        .shadow(color: Color.black.opacity(0.04), radius: 6, x: 0, y: 2)
                        .padding(.horizontal, 16)
                    }
                }
                .padding(.top, 4)
                .padding(.bottom, 120)
            }
        }
    }

    private func toggleExpand(_ chId: String) {
        if expandedChannels.contains(chId) {
            expandedChannels.remove(chId)
        } else {
            expandedChannels.insert(chId)
        }
    }

    private func openVideoLink(_ vid: VideoItem) {
        withAnimation(.easeInOut(duration: 0.25)) {
            onMarkRead(vid)
        }
        if let urlStr = vid.url,
           let url = URL(string: urlStr),
           url.scheme == "http" || url.scheme == "https" {
            #if canImport(UIKit)
            UIApplication.shared.open(url)
            #endif
        }
    }
}
#endif
