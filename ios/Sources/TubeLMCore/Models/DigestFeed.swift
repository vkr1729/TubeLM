import Foundation

/// Lenient primitives for a pipeline-owned feed: dirty producer values
/// (numeric strings, floats, bools) coerce; anything else falls back.
private func lenientInt<K: CodingKey>(_ c: KeyedDecodingContainer<K>, _ key: K) -> Int? {
    if let v = (try? c.decodeIfPresent(Int.self, forKey: key)) ?? nil { return v }
    if let v = (try? c.decodeIfPresent(Double.self, forKey: key)) ?? nil, v.isFinite { return Int(v) }
    if let s = (try? c.decodeIfPresent(String.self, forKey: key)) ?? nil {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { return nil }
        if let d = Double(t), d.isFinite { return Int(d) }
    }
    return nil
}

private func lenientString<K: CodingKey>(_ c: KeyedDecodingContainer<K>, _ key: K, default value: String = "") -> String {
    if let s = (try? c.decodeIfPresent(String.self, forKey: key)) ?? nil { return s }
    if let v = (try? c.decodeIfPresent(Int.self, forKey: key)) ?? nil { return String(v) }
    if let v = (try? c.decodeIfPresent(Double.self, forKey: key)) ?? nil { return String(v) }
    if let v = (try? c.decodeIfPresent(Bool.self, forKey: key)) ?? nil { return v ? "true" : "false" }
    return value
}

public struct DigestFeed: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let builtAt: String?
    public let runDate: String
    public let top20: Top20Container
    public let channels: [Channel]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case builtAt = "built_at"
        case runDate = "run_date"
        case top20
        case channels
    }

    public init(
        schemaVersion: Int = 1,
        builtAt: String? = nil,
        runDate: String,
        top20: Top20Container,
        channels: [Channel]
    ) {
        self.schemaVersion = schemaVersion
        self.builtAt = builtAt
        self.runDate = runDate
        self.top20 = top20
        self.channels = channels
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.schemaVersion = try container.decodeIfPresent(Int.self, forKey: .schemaVersion) ?? 1
        self.builtAt = try container.decodeIfPresent(String.self, forKey: .builtAt)
        self.runDate = try container.decodeIfPresent(String.self, forKey: .runDate) ?? ""
        self.top20 = try container.decodeIfPresent(Top20Container.self, forKey: .top20) ?? Top20Container(items: [])
        self.channels = try container.decodeIfPresent([Channel].self, forKey: .channels) ?? []
    }
}

public struct Top20Container: Codable, Sendable, Equatable {
    public let items: [FeedItem]

    public init(items: [FeedItem] = []) {
        self.items = items
    }
}

public struct FeedItem: Codable, Identifiable, Sendable, Equatable {
    public let id: String
    public let videoId: String?
    public let rank: Int?
    public let title: String
    public let sourceName: String
    public let sourceType: String
    public let duration: String?
    public let durationSeconds: Int?
    public let whyItMatters: String?
    public let url: String?
    public let audioUrl: String?

    enum CodingKeys: String, CodingKey {
        case id
        case videoId = "video_id"
        case rank
        case title
        case sourceName = "source_name"
        case sourceType = "source_type"
        case duration
        case durationSeconds = "duration_seconds"
        case whyItMatters = "why_it_matters"
        case url
        case audioUrl = "audio_url"
    }

    public init(
        id: String,
        videoId: String? = nil,
        rank: Int? = nil,
        title: String,
        sourceName: String = "",
        sourceType: String = "youtube",
        duration: String? = nil,
        durationSeconds: Int? = nil,
        whyItMatters: String? = nil,
        url: String? = nil,
        audioUrl: String? = nil
    ) {
        self.id = id
        self.videoId = videoId
        self.rank = rank
        self.title = title
        self.sourceName = sourceName
        self.sourceType = sourceType
        self.duration = duration
        self.durationSeconds = durationSeconds
        self.whyItMatters = whyItMatters
        self.url = url
        self.audioUrl = audioUrl
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? nil, !id.isEmpty {
            self.id = id
        } else if let numericId = try? c.decodeIfPresent(Int.self, forKey: .id) {
            self.id = String(numericId)
        } else {
            self.id = UUID().uuidString
        }
        self.videoId = try? c.decodeIfPresent(String.self, forKey: .videoId)
        self.rank = lenientInt(c, .rank)
        self.title = lenientString(c, .title)
        self.sourceName = lenientString(c, .sourceName)
        self.sourceType = lenientString(c, .sourceType, default: "youtube")
        self.duration = try? c.decodeIfPresent(String.self, forKey: .duration)
        self.durationSeconds = lenientInt(c, .durationSeconds)
        self.whyItMatters = try? c.decodeIfPresent(String.self, forKey: .whyItMatters)
        self.url = try? c.decodeIfPresent(String.self, forKey: .url)
        self.audioUrl = try? c.decodeIfPresent(String.self, forKey: .audioUrl)
    }

    public var isArticle: Bool {
        let st = sourceType.lowercased()
        return st == "rss" || st == "article" || st == "newsletter"
    }

    public var actionLabel: String {
        isArticle ? "Read" : "Watch"
    }

    public var aliases: Set<String> {
        SyncIdentity.aliases(id: id, videoId: videoId, url: url)
    }
}

public struct Channel: Codable, Identifiable, Sendable, Equatable {
    public let id: String
    public let name: String
    public let category: String
    public let readMinutes: Int?
    public let summaryText: String?
    public let summaryAudioUrl: String?
    public let audioUrl: String?
    public let videos: [VideoItem]

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case category
        case readMinutes = "read_minutes"
        case summaryText = "summary_text"
        case summaryAudioUrl = "summary_audio_url"
        case audioUrl = "audio_url"
        case videos
    }

    public init(
        id: String,
        name: String,
        category: String = "tech",
        readMinutes: Int? = 4,
        summaryText: String? = nil,
        summaryAudioUrl: String? = nil,
        audioUrl: String? = nil,
        videos: [VideoItem] = []
    ) {
        self.id = id
        self.name = name
        self.category = category
        self.readMinutes = readMinutes
        self.summaryText = summaryText
        self.summaryAudioUrl = summaryAudioUrl
        self.audioUrl = audioUrl
        self.videos = videos
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? nil, !id.isEmpty {
            self.id = id
        } else if let numericId = try? c.decodeIfPresent(Int.self, forKey: .id) {
            self.id = String(numericId)
        } else {
            self.id = UUID().uuidString
        }
        self.name = lenientString(c, .name, default: "Channel")
        self.category = lenientString(c, .category, default: "tech")
        self.readMinutes = lenientInt(c, .readMinutes)
        self.summaryText = try? c.decodeIfPresent(String.self, forKey: .summaryText)
        self.summaryAudioUrl = try? c.decodeIfPresent(String.self, forKey: .summaryAudioUrl)
        self.audioUrl = try? c.decodeIfPresent(String.self, forKey: .audioUrl)
        self.videos = (try? c.decodeIfPresent([VideoItem].self, forKey: .videos)) ?? []
    }

    public var initials: String {
        let words = name.split(separator: " ")
        if words.count >= 2 {
            return String(words[0].prefix(1) + words[1].prefix(1)).uppercased()
        }
        return String(name.prefix(2)).uppercased()
    }

    /// Display label for the spec's category pills (Tech & AI, Health & Bio,
    /// Science & Deep). Raw pipeline values (tech, health, deep_explainer,
    /// news_feed, science) map to pills; unknown values title-case through.
    public var categoryLabel: String {
        switch category.lowercased() {
        case "tech", "ai", "tech_ai": return "Tech & AI"
        case "health", "bio", "health_bio": return "Health & Bio"
        case "science", "deep", "deep_explainer", "science_deep": return "Science & Deep"
        case "news", "news_feed": return "News"
        default:
            let cleaned = category.replacingOccurrences(of: "_", with: " ")
            return cleaned.prefix(1).uppercased() + cleaned.dropFirst()
        }
    }
}

public struct VideoItem: Codable, Identifiable, Sendable, Equatable {
    public let id: String
    public let videoId: String?
    public let title: String
    public let duration: String?
    public let durationSeconds: Int?
    public let summaryHtml: String?
    public let url: String?
    public let audioUrl: String?
    public let sourceType: String?
    public let lead: String?

    enum CodingKeys: String, CodingKey {
        case id
        case videoId = "video_id"
        case title
        case duration
        case durationSeconds = "duration_seconds"
        case summaryHtml = "summary_html"
        case url
        case audioUrl = "audio_url"
        case sourceType = "source_type"
        case lead
    }

    public init(
        id: String,
        videoId: String? = nil,
        title: String,
        duration: String? = nil,
        durationSeconds: Int? = nil,
        summaryHtml: String? = nil,
        url: String? = nil,
        audioUrl: String? = nil,
        sourceType: String? = "youtube",
        lead: String? = nil
    ) {
        self.id = id
        self.videoId = videoId
        self.title = title
        self.duration = duration
        self.durationSeconds = durationSeconds
        self.summaryHtml = summaryHtml
        self.url = url
        self.audioUrl = audioUrl
        self.sourceType = sourceType
        self.lead = lead
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let id = (try? c.decodeIfPresent(String.self, forKey: .id)) ?? nil, !id.isEmpty {
            self.id = id
        } else if let numericId = try? c.decodeIfPresent(Int.self, forKey: .id) {
            self.id = String(numericId)
        } else {
            self.id = UUID().uuidString
        }
        self.videoId = try? c.decodeIfPresent(String.self, forKey: .videoId)
        self.title = lenientString(c, .title)
        self.duration = try? c.decodeIfPresent(String.self, forKey: .duration)
        self.durationSeconds = lenientInt(c, .durationSeconds)
        self.summaryHtml = try? c.decodeIfPresent(String.self, forKey: .summaryHtml)
        self.url = try? c.decodeIfPresent(String.self, forKey: .url)
        self.audioUrl = try? c.decodeIfPresent(String.self, forKey: .audioUrl)
        self.sourceType = try? c.decodeIfPresent(String.self, forKey: .sourceType)
        self.lead = try? c.decodeIfPresent(String.self, forKey: .lead)
    }

    public var isArticle: Bool {
        let st = (sourceType ?? "youtube").lowercased()
        return st == "rss" || st == "article" || st == "newsletter"
    }

    public var actionLabel: String {
        isArticle ? "Read" : "Watch"
    }

    public var aliases: Set<String> {
        SyncIdentity.aliases(id: id, videoId: videoId, url: url)
    }
}
