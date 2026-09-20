#if canImport(SwiftUI)
import SwiftUI
import TubeLMCore

public struct BookmarksView: View {
    public let bookmarks: [FeedItem]
    public let onRemoveBookmark: (String) -> Void
    public let onOpenSettings: (() -> Void)?

    public init(
        bookmarks: [FeedItem],
        onRemoveBookmark: @escaping (String) -> Void,
        onOpenSettings: (() -> Void)? = nil
    ) {
        self.bookmarks = bookmarks
        self.onRemoveBookmark = onRemoveBookmark
        self.onOpenSettings = onOpenSettings
    }

    public var body: some View {
        Group {
            if bookmarks.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "bookmark")
                        .font(.system(size: 40))
                        .foregroundColor(.secondary)
                    Text("No Bookmarks Yet")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundColor(.primary)
                    Text("Saved articles and deep explainers will appear here.")
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)

                    if let onOpenSettings {
                        Button(action: onOpenSettings) {
                            HStack(spacing: 6) {
                                Image(systemName: "gearshape.fill")
                                    .font(.system(size: 12))
                                Text("Settings & Appearance")
                                    .font(.system(size: 13, weight: .semibold))
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                            .background(AppTheme.secondarySystemBackground)
                            .foregroundColor(.primary)
                            .clipShape(Capsule())
                        }
                        .padding(.top, 8)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else {
                ScrollView {
                    LazyVStack(spacing: 12) {
                        ForEach(bookmarks) { item in
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text(item.sourceName.uppercased())
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundColor(AppTheme.accent)
                                    Spacer()
                                    Button(action: { onRemoveBookmark(item.id) }) {
                                        Text("Remove")
                                            .font(.system(size: 11, weight: .semibold))
                                            .foregroundColor(.red)
                                    }
                                }

                                Text(item.title)
                                    .font(AppTheme.title)
                                    .foregroundColor(.primary)
                                    .onTapGesture {
                                        openLink(item)
                                    }

                                if let why = item.whyItMatters, !why.isEmpty {
                                    Text(why)
                                        .font(AppTheme.whyText)
                                        .foregroundColor(.secondary)
                                        .lineLimit(2)
                                }

                                HStack {
                                    Spacer()
                                    Button(action: { openLink(item) }) {
                                        HStack(spacing: 4) {
                                            Image(systemName: item.isArticle ? "doc.text" : "play.rectangle")
                                            Text(item.actionLabel)
                                        }
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundColor(AppTheme.accent)
                                    }
                                }
                            }
                            .padding(14)
                            .background(AppTheme.systemBackground)
                        }

                        if let onOpenSettings {
                            Button(action: onOpenSettings) {
                                HStack(spacing: 6) {
                                    Image(systemName: "gearshape.fill")
                                        .font(.system(size: 12))
                                    Text("Settings & Appearance")
                                        .font(.system(size: 13, weight: .semibold))
                                }
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                                .background(AppTheme.secondarySystemBackground)
                                .foregroundColor(.primary)
                                .clipShape(Capsule())
                            }
                            .padding(.top, 16)
                            .frame(maxWidth: .infinity)
                        }
                    }
                    .padding(.top, 12)
                    .padding(.bottom, 120)
                }
            }
        }
    }

    private func openLink(_ item: FeedItem) {
        if let urlStr = item.url,
           let url = URL(string: urlStr),
           url.scheme == "http" || url.scheme == "https" {
            #if canImport(UIKit)
            UIApplication.shared.open(url)
            #endif
        }
    }
}
#endif
