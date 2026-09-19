import Foundation

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
        self.id = try c.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        self.rank = try c.decodeIfPresent(Int.self, forKey: .rank)
        self.title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        self.sourceName = try c.decodeIfPresent(String.self, forKey: .sourceName) ?? ""
        self.sourceType = try c.decodeIfPresent(String.self, forKey: .sourceType) ?? "youtube"
        self.duration = try c.decodeIfPresent(String.self, forKey: .duration)
        self.durationSeconds = try c.decodeIfPresent(Int.self, forKey: .durationSeconds)
        self.whyItMatters = try c.decodeIfPresent(String.self, forKey: .whyItMatters)
        self.url = try c.decodeIfPresent(String.self, forKey: .url)
        self.audioUrl = try c.decodeIfPresent(String.self, forKey: .audioUrl)
    }

    public var isArticle: Bool {
        let st = sourceType.lowercased()
        return st == "rss" || st == "article" || st == "newsletter"
    }

    public var actionLabel: String {
        isArticle ? "Read" : "Watch"
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
        self.id = try c.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        self.name = try c.decodeIfPresent(String.self, forKey: .name) ?? "Channel"
        self.category = try c.decodeIfPresent(String.self, forKey: .category) ?? "tech"
        self.readMinutes = try c.decodeIfPresent(Int.self, forKey: .readMinutes)
        self.summaryText = try c.decodeIfPresent(String.self, forKey: .summaryText)
        self.summaryAudioUrl = try c.decodeIfPresent(String.self, forKey: .summaryAudioUrl)
        self.audioUrl = try c.decodeIfPresent(String.self, forKey: .audioUrl)
        self.videos = try c.decodeIfPresent([VideoItem].self, forKey: .videos) ?? []
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
        self.id = try c.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        self.title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        self.duration = try c.decodeIfPresent(String.self, forKey: .duration)
        self.durationSeconds = try c.decodeIfPresent(Int.self, forKey: .durationSeconds)
        self.summaryHtml = try c.decodeIfPresent(String.self, forKey: .summaryHtml)
        self.url = try c.decodeIfPresent(String.self, forKey: .url)
        self.audioUrl = try c.decodeIfPresent(String.self, forKey: .audioUrl)
        self.sourceType = try c.decodeIfPresent(String.self, forKey: .sourceType)
        self.lead = try c.decodeIfPresent(String.self, forKey: .lead)
    }

    public var isArticle: Bool {
        let st = (sourceType ?? "youtube").lowercased()
        return st == "rss" || st == "article" || st == "newsletter"
    }

    public var actionLabel: String {
        isArticle ? "Read" : "Watch"
    }
}
