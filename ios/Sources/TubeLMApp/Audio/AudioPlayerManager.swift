#if canImport(AVFoundation) && canImport(MediaPlayer)
import Foundation
import AVFoundation
import MediaPlayer
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

    public override init() {
        super.init()
        setupAudioSession()
        setupRemoteCommands()
        endOfPlaybackObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEnd,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self else { return }
            guard let finished = notification.object as? AVPlayerItem,
                  finished == self.player?.currentItem else { return }
            self.isPlaying = false
            self.updateNowPlayingInfo()
        }
    }

    deinit {
        if let endOfPlaybackObserver = endOfPlaybackObserver {
            NotificationCenter.default.removeObserver(endOfPlaybackObserver)
        }
        if let token = timeObserverToken {
            player?.removeTimeObserver(token)
        }
    }

    private func setupAudioSession() {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio, options: [])
            try session.setActive(true)
        } catch {
            print("Failed to configure AVAudioSession: \(error)")
        }
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
        if !trimmed.isEmpty,
           let url = URL(string: trimmed, relativeTo: Self.feedBaseURL)?.absoluteURL,
           url.scheme == "http" || url.scheme == "https" {
            let item = AVPlayerItem(url: url)
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
            isPlaying = false
            currentTime = 0
        }
        updateNowPlayingInfo()
    }

    public func play() {
        player?.play()
        player?.rate = playbackRate
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
