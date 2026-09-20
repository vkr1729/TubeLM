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

    @State private var isDraggingScrubber: Bool = false
    @State private var dragScrubProgress: Double = 0.0

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
                    // Hero Artwork Card (Emerald Gradient with dynamic monogram & wave)
                    ZStack {
                        RoundedRectangle(cornerRadius: 24)
                            .fill(
                                LinearGradient(
                                    colors: [
                                        Color(red: 0.08, green: 0.50, blue: 0.24),
                                        Color(red: 0.04, green: 0.32, blue: 0.15)
                                    ],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .frame(width: 180, height: 180)
                            .overlay(
                                RoundedRectangle(cornerRadius: 24)
                                    .stroke(Color.white.opacity(0.18), lineWidth: 1)
                            )
                            .shadow(color: Color.black.opacity(0.16), radius: 16, x: 0, y: 8)

                        VStack(spacing: 10) {
                            Image(systemName: "waveform")
                                .font(.system(size: 46, weight: .medium))
                                .foregroundColor(.white)
                            Text("TubeLM")
                                .font(.system(size: 13, weight: .heavy, design: .monospaced))
                                .tracking(2.5)
                                .foregroundColor(.white.opacity(0.85))
                        }
                    }
                    .padding(.top, 12)

                    // Titles & Status Pill
                    VStack(spacing: 6) {
                        Text(player.currentTitle)
                            .font(.system(size: 18, weight: .bold, design: .serif))
                            .foregroundColor(.primary)
                            .multilineTextAlignment(.center)
                            .lineLimit(2)
                            .padding(.horizontal, 20)

                        Text(player.currentSource)
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(.secondary)

                        HStack(spacing: 6) {
                            Circle()
                                .fill(player.isPlaying ? AppTheme.accent : Color.secondary)
                                .frame(width: 6, height: 6)
                            Text(player.isPlaying ? "Playing NotebookLM Overview" : "Paused")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundColor(.secondary)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(AppTheme.secondarySystemBackground)
                        .clipShape(Capsule())
                        .padding(.top, 4)
                    }

                    // Custom Capsule Scrubber Bar (with DragGesture)
                    let duration = max(1.0, player.duration)
                    let progress = isDraggingScrubber ? dragScrubProgress : (player.duration > 0 ? (player.currentTime / duration) : 0.0)
                    let clamped = max(0.0, min(1.0, progress))
                    let displayCurrentTime = isDraggingScrubber ? (clamped * duration) : player.currentTime

                    VStack(spacing: 8) {
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                // Background track
                                Capsule()
                                    .fill(AppTheme.secondarySystemBackground)
                                    .frame(height: isDraggingScrubber ? 8 : 6)

                                // Filled progress
                                Capsule()
                                    .fill(AppTheme.accent)
                                    .frame(width: max(0, min(geo.size.width, geo.size.width * clamped)), height: isDraggingScrubber ? 8 : 6)

                                // Draggable Thumb
                                Circle()
                                    .fill(Color.white)
                                    .frame(width: isDraggingScrubber ? 18 : 14, height: isDraggingScrubber ? 18 : 14)
                                    .shadow(color: Color.black.opacity(0.2), radius: 3, x: 0, y: 1)
                                    .offset(x: max(0, min(geo.size.width * clamped - (isDraggingScrubber ? 9 : 7), geo.size.width - (isDraggingScrubber ? 18 : 14))))
                            }
                            .contentShape(Rectangle())
                            .gesture(
                                DragGesture(minimumDistance: 0)
                                    .onChanged { value in
                                        isDraggingScrubber = true
                                        let fraction = max(0.0, min(1.0, Double(value.location.x / geo.size.width)))
                                        dragScrubProgress = fraction
                                    }
                                    .onEnded { value in
                                        let fraction = max(0.0, min(1.0, Double(value.location.x / geo.size.width)))
                                        let targetTime = fraction * player.duration
                                        player.seek(to: targetTime)
                                        isDraggingScrubber = false
                                    }
                            )
                        }
                        .frame(height: 18)

                        HStack {
                            Text(formatTime(displayCurrentTime))
                            Spacer()
                            Text(formatTime(player.duration))
                        }
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .foregroundColor(.secondary)
                    }
                    .padding(.horizontal, 24)

                    // Commute Transport Controls (56pt touch targets)
                    HStack(spacing: 20) {
                        Button(action: {
                            Haptics.tap()
                            player.skip(seconds: -15)
                        }) {
                            Image(systemName: "gobackward.15")
                                .font(.system(size: 22))
                                .frame(width: 56, height: 56)
                                .background(AppTheme.secondarySystemBackground)
                                .clipShape(Circle())
                        }
                        .accessibilityLabel("Skip backward 15 seconds")

                        Button(action: {
                            Haptics.tap()
                            player.togglePlay()
                        }) {
                            Image(systemName: player.isPlaying ? "pause.fill" : "play.fill")
                                .font(.system(size: 28))
                                .foregroundColor(.white)
                                .frame(width: 68, height: 68)
                                .background(AppTheme.accent)
                                .clipShape(Circle())
                                .shadow(color: AppTheme.accent.opacity(0.35), radius: 10, x: 0, y: 5)
                        }
                        .accessibilityLabel(player.isPlaying ? "Pause" : "Play")

                        Button(action: {
                            Haptics.tap()
                            player.skip(seconds: 15)
                        }) {
                            Image(systemName: "goforward.15")
                                .font(.system(size: 22))
                                .frame(width: 56, height: 56)
                                .background(AppTheme.secondarySystemBackground)
                                .clipShape(Circle())
                        }
                        .accessibilityLabel("Skip forward 15 seconds")

                        Button(action: {
                            Haptics.tap()
                            player.cycleSpeed()
                        }) {
                            Text(String(format: "%.2g×", player.playbackRate))
                                .font(.system(size: 13, weight: .bold))
                                .frame(width: 56, height: 56)
                                .background(AppTheme.secondarySystemBackground)
                                .clipShape(Circle())
                        }
                        .accessibilityLabel("Playback speed \(String(format: "%.2g", player.playbackRate)) times")
                    }
                    .foregroundColor(.primary)

                    Divider()
                        .padding(.top, 6)

                    // Commute Queue (Up Next)
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Up Next")
                                .font(.system(size: 15, weight: .bold))
                            Spacer()
                            Text("\(queue.count) items")
                                .font(.system(size: 11, weight: .bold))
                                .foregroundColor(AppTheme.accent)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(AppTheme.accent.opacity(0.12))
                                .clipShape(Capsule())
                        }

                        if queue.isEmpty {
                            Text("Queue is empty. Tap '+ Queue' on any article to add.")
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                                .padding(.vertical, 8)
                        } else {
                            ForEach(queue) { item in
                                HStack(spacing: 12) {
                                    Image(systemName: "line.3.horizontal")
                                        .foregroundColor(.secondary)
                                        .font(.system(size: 13))
                                        .frame(width: 24, height: 24)

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
                                        Haptics.tap()
                                        queue.removeAll(where: { $0.id == item.id })
                                    }) {
                                        Image(systemName: "xmark")
                                            .font(.system(size: 11, weight: .bold))
                                            .foregroundColor(.secondary)
                                            .frame(width: 36, height: 36)
                                            .background(AppTheme.tertiarySystemBackground)
                                            .clipShape(Circle())
                                    }
                                    .accessibilityLabel("Remove \(item.title) from queue")
                                }
                                .padding(10)
                                .background(AppTheme.secondarySystemBackground)
                                .cornerRadius(12)
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
