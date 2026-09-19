#if canImport(SwiftUI)
import SwiftUI
import TubeLMCore

public struct BookmarksView: View {
    public let bookmarks: [FeedItem]
    public let onRemoveBookmark: (String) -> Void

    public init(bookmarks: [FeedItem], onRemoveBookmark: @escaping (String) -> Void) {
        self.bookmarks = bookmarks
        self.onRemoveBookmark = onRemoveBookmark
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
                            .background(Color(UIColor.systemBackground))
                            .cornerRadius(16)
                            .shadow(color: Color.black.opacity(0.04), radius: 6, x: 0, y: 2)
                            .padding(.horizontal, 16)
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
