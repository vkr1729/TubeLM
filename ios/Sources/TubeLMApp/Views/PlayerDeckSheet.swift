#if canImport(SwiftUI)
import SwiftUI
import TubeLMCore
#if canImport(UniformTypeIdentifiers)
import UniformTypeIdentifiers
#endif

public struct PlayerDeckSheet: View {
    @ObservedObject var player: AudioPlayerManager
    @Binding var queue: [QueueItem]
    public let onDismiss: () -> Void

    public init(player: AudioPlayerManager, queue: Binding<[QueueItem]>, onDismiss: @escaping () -> Void) {
        self.player = player
        self._queue = queue
        self.onDismiss = onDismiss
    }

    public var body: some View {
        VStack(spacing: 0) {
            // Drag Handle
            Capsule()
                .fill(Color.secondary.opacity(0.3))
                .frame(width: 38, height: 5)
                .padding(.top, 10)
                .padding(.bottom, 6)

            // Sheet Header
            HStack {
                Text("Now Playing")
                    .font(.system(size: 16, weight: .bold))
                Spacer()
                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.secondary)
                        .padding(8)
                        .background(AppTheme.secondarySystemBackground)
                        .clipShape(Circle())
                }
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 12)

            Divider()

            ScrollView {
                VStack(spacing: 20) {
                    // Hero Artwork
                    ZStack {
                        RoundedRectangle(cornerRadius: 24)
                            .fill(AppTheme.accentBadge)
                            .frame(width: 100, height: 100)
                            .shadow(color: Color.black.opacity(0.12), radius: 10, x: 0, y: 4)
                        Text("TL")
                            .font(.system(size: 36, weight: .black))
                            .foregroundColor(AppTheme.accentBadgeText)
                    }
                    .padding(.top, 10)

                    // Titles
                    VStack(spacing: 4) {
                        Text(player.currentTitle)
                            .font(.system(size: 17, weight: .bold))
                            .foregroundColor(.primary)
                            .multilineTextAlignment(.center)
                            .lineLimit(2)
                        Text(player.currentSource)
                            .font(.system(size: 13))
                            .foregroundColor(.secondary)
                    }
                    .padding(.horizontal, 24)

                    // Scrubber Bar
                    VStack(spacing: 6) {
                        Slider(value: Binding(
                            get: { player.currentTime },
                            set: { player.seek(to: $0) }
                        ), in: 0...max(1.0, player.duration))
                        .accentColor(AppTheme.accent)

                        HStack {
                            Text(formatTime(player.currentTime))
                            Spacer()
                            Text(formatTime(player.duration))
                        }
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .foregroundColor(.secondary)
                    }
                    .padding(.horizontal, 24)

                    // Controls
                    HStack(spacing: 24) {
                        Button(action: { player.skip(seconds: -15) }) {
                            Image(systemName: "gobackward.15")
                                .font(.system(size: 20))
                                .frame(width: 44, height: 44)
                                .background(AppTheme.secondarySystemBackground)
                                .clipShape(Circle())
                        }

                        Button(action: { player.togglePlay() }) {
                            Image(systemName: player.isPlaying ? "pause.fill" : "play.fill")
                                .font(.system(size: 26))
                                .foregroundColor(.white)
                                .frame(width: 62, height: 62)
                                .background(AppTheme.accent)
                                .clipShape(Circle())
                                .shadow(color: AppTheme.accent.opacity(0.3), radius: 8, x: 0, y: 4)
                        }

                        Button(action: { player.skip(seconds: 15) }) {
                            Image(systemName: "goforward.15")
                                .font(.system(size: 20))
                                .frame(width: 44, height: 44)
                                .background(AppTheme.secondarySystemBackground)
                                .clipShape(Circle())
                        }

                        Button(action: { player.cycleSpeed() }) {
                            Text(String(format: "%.2g×", player.playbackRate))
                                .font(.system(size: 12, weight: .bold))
                                .frame(width: 44, height: 44)
                                .background(AppTheme.secondarySystemBackground)
                                .clipShape(Circle())
                        }
                    }
                    .foregroundColor(.primary)

                    Divider()
                        .padding(.top, 10)

                    // Commute Queue (Up Next)
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Up Next")
                                .font(.system(size: 14, weight: .bold))
                            Spacer()
                            Text("\(queue.count) items")
                                .font(.system(size: 11, weight: .bold))
                                .foregroundColor(AppTheme.accent)
                        }

                        if queue.isEmpty {
                            Text("Queue is empty. Tap '+ Queue' on any article to add.")
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                                .padding(.vertical, 8)
                        } else {
                            ForEach(queue) { item in
                                HStack {
                                    Image(systemName: "line.3.horizontal")
                                        .foregroundColor(.secondary)
                                        .font(.system(size: 12))

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(item.title)
                                            .font(.system(size: 13, weight: .semibold))
                                            .lineLimit(1)
                                        Text(item.duration.isEmpty ? item.sourceName : "\(item.sourceName) · \(item.duration)")
                                            .font(.system(size: 11))
                                            .foregroundColor(.secondary)
                                    }

                                    Spacer()

                                    Button(action: {
                                        queue.removeAll(where: { $0.id == item.id })
                                    }) {
                                        Image(systemName: "xmark")
                                            .font(.system(size: 11))
                                            .foregroundColor(.secondary)
                                            .padding(6)
                                    }
                                }
                                .padding(10)
                                .background(AppTheme.secondarySystemBackground)
                                .cornerRadius(10)
                                .onDrag { NSItemProvider(object: item.id as NSString) }
                                .onDrop(of: [.text], delegate: QueueDropDelegate(item: item, queue: $queue))
                            }
                        }
                    }
                    .padding(.horizontal, 20)
                }
                .padding(.bottom, 30)
            }
        }
        .background(AppTheme.systemBackground)
    }

    private func formatTime(_ seconds: Double) -> String {
        guard seconds.isFinite else { return "00:00" }
        let s = max(0, Int(seconds))
        let m = s / 60
        let remS = s % 60
        return String(format: "%02d:%02d", m, remS)
    }
}

private struct QueueDropDelegate: DropDelegate {
    let item: QueueItem
    @Binding var queue: [QueueItem]

    func performDrop(info: DropInfo) -> Bool {
        guard let provider = info.itemProviders(for: [.text]).first else { return false }
        _ = provider.loadObject(ofClass: NSString.self) { [self] dragged, _ in
            guard let draggedID = dragged as? String else { return }
            Task { @MainActor in
                guard let from = queue.firstIndex(where: { $0.id == draggedID }),
                      let to = queue.firstIndex(where: { $0.id == item.id }),
                      from != to else { return }
                var model = CommuteQueueModel(items: queue)
                model.move(fromOffsets: IndexSet(integer: from), toOffset: to > from ? to + 1 : to)
                queue = model.items
            }
        }
        return true
    }
}
#endif
