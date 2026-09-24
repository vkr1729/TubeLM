#if canImport(AVFoundation) && canImport(MediaPlayer)
@preconcurrency import Foundation
@preconcurrency import AVFoundation
@preconcurrency import MediaPlayer
import TubeLMCore

@MainActor
public final class AudioPlayerManager: NSObject, ObservableObject {
    public static let shared = AudioPlayerManager()

    @Published public var isPlaying: Bool = false
    @Published public var currentTitle: String = "Nothing Playing"
    @Published public var currentSource: String = "Pick an episode to begin"
    @Published public var currentTime: Double = 0.0
    @Published public var duration: Double = 0.0
    @Published public var playbackRate: Float = 1.25

    public var queue = CommuteQueueModel()
    private var player: AVPlayer?
    private var timeObserverToken: Any?
    private var endOfPlaybackObserver: NSObjectProtocol?
    private var playbackFailedObserver: NSObjectProtocol?
    private var statusObserverToken: NSKeyValueObservation?

    public override init() {
        super.init()
        setupRemoteCommands()
        endOfPlaybackObserver = NotificationCenter.default.addObserver(
            forName: AVPlayerItem.didPlayToEndTimeNotification,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            MainActor.assumeIsolated {
                guard let self = self else { return }
                guard let finished = notification.object as? AVPlayerItem,
                      finished == self.player?.currentItem else { return }
                self.isPlaying = false
                self.updateNowPlayingInfo()
            }
        }
        playbackFailedObserver = NotificationCenter.default.addObserver(
            forName: AVPlayerItem.failedToPlayToEndTimeNotification,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            MainActor.assumeIsolated {
                guard let self = self else { return }
                guard let failed = notification.object as? AVPlayerItem,
                      failed == self.player?.currentItem else { return }
                print("[AudioPlayerManager] Playback failed: \(String(describing: failed.error))")
                self.isPlaying = false
                self.updateNowPlayingInfo()
            }
        }
    }

    deinit {
        statusObserverToken?.invalidate()
        if let token = timeObserverToken {
            player?.removeTimeObserver(token)
        }
        if let observer = endOfPlaybackObserver {
            NotificationCenter.default.removeObserver(observer)
        }
        if let observer = playbackFailedObserver {
            NotificationCenter.default.removeObserver(observer)
        }
    }

    private func ensureAudioSession() {
        #if os(iOS)
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio, options: [])
            try session.setActive(true)
        } catch {
            print("Failed to configure AVAudioSession: \(error)")
        }
        #endif
    }

    private func setupRemoteCommands() {
        let commandCenter = MPRemoteCommandCenter.shared()

        commandCenter.playCommand.addTarget { [weak self] _ in
            self?.play()
            return .success
        }
        commandCenter.pauseCommand.addTarget { [weak self] _ in
            self?.pause()
            return .success
        }
        commandCenter.togglePlayPauseCommand.addTarget { [weak self] _ in
            self?.togglePlay()
            return .success
        }
        commandCenter.skipForwardCommand.preferredIntervals = [15]
        commandCenter.skipForwardCommand.addTarget { [weak self] _ in
            self?.skip(seconds: 15)
            return .success
        }
        commandCenter.skipBackwardCommand.preferredIntervals = [15]
        commandCenter.skipBackwardCommand.addTarget { [weak self] _ in
            self?.skip(seconds: -15)
            return .success
        }
    }

    public static let feedBaseURL = URL(string: "https://vkr1729.github.io/TubeLM/")!

    public func playTrack(title: String, source: String, urlString: String?) {
        currentTitle = title
        currentSource = source

        let trimmed = urlString?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        var resolvedURL: URL? = URL(string: trimmed, relativeTo: Self.feedBaseURL)?.absoluteURL
        if resolvedURL == nil, let encoded = trimmed.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) {
            resolvedURL = URL(string: encoded, relativeTo: Self.feedBaseURL)?.absoluteURL
        }

        if let url = resolvedURL, url.scheme == "http" || url.scheme == "https" {
            ensureAudioSession()
            statusObserverToken?.invalidate()
            statusObserverToken = nil
            let item = AVPlayerItem(url: url)
            statusObserverToken = item.observe(\.status, options: [.initial, .new]) { [weak self] observedItem, _ in
                Task { @MainActor in
                    guard let self = self, observedItem == self.player?.currentItem else { return }
                    switch observedItem.status {
                    case .failed:
                        print("[AudioPlayerManager] Playback failed: \(String(describing: observedItem.error))")
                        self.isPlaying = false
                        self.updateNowPlayingInfo()
                    case .readyToPlay:
                        let total = observedItem.duration.seconds
                        if total.isFinite && total > 0 {
                            self.duration = total
                        }
                        self.updateNowPlayingInfo()
                    case .unknown:
                        break
                    @unknown default:
                        break
                    }
                }
            }
            if player == nil {
                player = AVPlayer(playerItem: item)
                setupTimeObserver()
            } else {
                player?.replaceCurrentItem(with: item)
            }
            player?.play()
            player?.rate = playbackRate
            isPlaying = true
        } else {
            // No playable audio for this item: surface the state instead of
            // faking playback (a stuck "playing" indicator with no sound).
            statusObserverToken?.invalidate()
            statusObserverToken = nil
            isPlaying = false
            currentTime = 0
        }
        updateNowPlayingInfo()
    }

    public func play() {
        guard let player = player, player.currentItem != nil else {
            // No loaded item: do not activate audio session or fake playing state
            isPlaying = false
            return
        }
        ensureAudioSession()
        player.play()
        player.rate = playbackRate
        isPlaying = true
        updateNowPlayingInfo()
    }

    public func pause() {
        player?.pause()
        isPlaying = false
        updateNowPlayingInfo()
    }

    public func togglePlay() {
        if isPlaying { pause() } else { play() }
    }

    public func skip(seconds: Double) {
        let safeSeconds = seconds.isFinite ? seconds : 0
        let newTime = max(0, min(currentTime + safeSeconds, max(duration, 0)))
        seek(to: newTime)
    }

    public func seek(to seconds: Double) {
        let clamped = seconds.isFinite ? max(0, min(seconds, max(duration, 0))) : 0
        currentTime = clamped
        if let player = player {
            let cmTime = CMTime(seconds: clamped, preferredTimescale: 600)
            player.seek(to: cmTime)
        }
        updateNowPlayingInfo()
    }

    public func cycleSpeed() {
        let speeds: [Float] = [1.0, 1.25, 1.5, 2.0]
        let currentIdx = speeds.firstIndex(of: playbackRate) ?? 1
        playbackRate = speeds[(currentIdx + 1) % speeds.count]
        if isPlaying {
            player?.rate = playbackRate
        }
        updateNowPlayingInfo()
    }

    private func setupTimeObserver() {
        guard timeObserverToken == nil else { return }
        let interval = CMTime(seconds: 0.5, preferredTimescale: 600)
        timeObserverToken = player?.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] time in
            MainActor.assumeIsolated {
                guard let self = self else { return }
                let seconds = time.seconds
                self.currentTime = seconds.isFinite ? max(0, seconds) : 0
                if let currentItem = self.player?.currentItem {
                    let total = currentItem.duration.seconds
                    if total.isFinite && total > 0 {
                        self.duration = total
                    }
                }
                self.updateNowPlayingInfo()
            }
        }
    }

    private func updateNowPlayingInfo() {
        var info = [String: Any]()
        info[MPMediaItemPropertyTitle] = currentTitle
        info[MPMediaItemPropertyArtist] = currentSource
        info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = currentTime
        info[MPMediaItemPropertyPlaybackDuration] = duration
        info[MPNowPlayingInfoPropertyPlaybackRate] = isPlaying ? Double(playbackRate) : 0.0
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }
}
#endif
