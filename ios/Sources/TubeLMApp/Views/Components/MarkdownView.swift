#if canImport(SwiftUI)
import Foundation
import SwiftUI

public struct MarkdownView: View {
    public let text: String

    public init(_ text: String) {
        self.text = text
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(parseBlocks(text), id: \.id) { block in
                switch block.kind {
                case .header(let level, let content):
                    Text(decodeEntities(content))
                        .font(.system(size: level == 2 ? 15 : 14, weight: .bold))
                        .foregroundColor(.primary)
                        .padding(.top, 4)
                case .bullet(let content):
                    HStack(alignment: .top, spacing: 6) {
                        Text("•")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(.secondary)
                        renderInline(content)
                            .font(.system(size: 13))
                            .foregroundColor(.primary)
                    }
                case .numbered(let number, let content):
                    HStack(alignment: .top, spacing: 6) {
                        Text("\(number).")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(.secondary)
                        renderInline(content)
                            .font(.system(size: 13))
                            .foregroundColor(.primary)
                    }
                case .paragraph(let content):
                    renderInline(content)
                        .font(.system(size: 13))
                        .foregroundColor(.primary)
                        .lineSpacing(2)
                }
            }
        }
    }

    private func renderInline(_ raw: String) -> Text {
        var result = Text("")
        let decoded = decodeEntities(stripRemainingTags(raw))
        let pattern = #"\*\*(.+?)\*\*"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else {
            return Text(decoded)
        }
        let ns = decoded as NSString
        var cursor = 0
        for match in regex.matches(in: decoded, range: NSRange(location: 0, length: ns.length)) {
            let full = match.range(at: 0)
            let inner = match.range(at: 1)
            if full.location > cursor {
                result = result + Text(ns.substring(with: NSRange(location: cursor, length: full.location - cursor)))
            }
            result = result + Text(ns.substring(with: inner)).bold()
            cursor = full.location + full.length
        }
        if cursor < ns.length {
            result = result + Text(ns.substring(from: cursor))
        }
        return result
    }

    private struct MarkdownBlock: Identifiable {
        let id = UUID()
        enum Kind {
            case header(level: Int, content: String)
            case bullet(content: String)
            case numbered(number: Int, content: String)
            case paragraph(content: String)
        }
        let kind: Kind
    }

    private func decodeEntities(_ raw: String) -> String {
        var out = raw
        let entities: [(String, String)] = [
            ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
            ("&quot;", "\""), ("&#39;", "'"), ("&apos;", "'"),
            ("&nbsp;", " "),
        ]
        for (entity, char) in entities {
            out = out.replacingOccurrences(of: entity, with: char)
        }
        return out
    }

    private func stripRemainingTags(_ raw: String) -> String {
        guard let regex = try? NSRegularExpression(pattern: #"<[^>]+>"#) else { return raw }
        return regex.stringByReplacingMatches(
            in: raw,
            range: NSRange(raw.startIndex..., in: raw),
            withTemplate: ""
        ).trimmingCharacters(in: .whitespaces)
    }

    private func parseBlocks(_ raw: String) -> [MarkdownBlock] {
        var blocks: [MarkdownBlock] = []
        let clean = raw
            .replacingOccurrences(of: "<br>", with: "\n")
            .replacingOccurrences(of: "<br/>", with: "\n")
            .replacingOccurrences(of: "<br />", with: "\n")
            .replacingOccurrences(of: "</br>", with: "\n")
            .replacingOccurrences(of: "<li>", with: "- ")
            .replacingOccurrences(of: "</li>", with: "\n")
            .replacingOccurrences(of: "<ul>", with: "\n")
            .replacingOccurrences(of: "</ul>", with: "\n")
            .replacingOccurrences(of: "<ol>", with: "\n")
            .replacingOccurrences(of: "</ol>", with: "\n")
            .replacingOccurrences(of: "<p>", with: "")
            .replacingOccurrences(of: "</p>", with: "\n")
            .replacingOccurrences(of: "<strong>", with: "**")
            .replacingOccurrences(of: "</strong>", with: "**")
            .replacingOccurrences(of: "<b>", with: "**")
            .replacingOccurrences(of: "</b>", with: "**")
            .replacingOccurrences(of: "<em>", with: "*")
            .replacingOccurrences(of: "</em>", with: "*")

        let numberedPattern = #"^(\d+)[.)]\s+(.*)$"#
        let numberedRegex = try? NSRegularExpression(pattern: numberedPattern)

        let lines = clean.components(separatedBy: "\n")
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty { continue }

            if trimmed.hasPrefix("### ") {
                blocks.append(MarkdownBlock(kind: .header(level: 3, content: stripRemainingTags(String(trimmed.dropFirst(4))))))
            } else if trimmed.hasPrefix("## ") {
                blocks.append(MarkdownBlock(kind: .header(level: 2, content: stripRemainingTags(String(trimmed.dropFirst(3))))))
            } else if trimmed.hasPrefix("- ") || trimmed.hasPrefix("* ") {
                blocks.append(MarkdownBlock(kind: .bullet(content: String(trimmed.dropFirst(2)))))
            } else if let regex = numberedRegex,
                      let match = regex.firstMatch(in: trimmed, range: NSRange(trimmed.startIndex..., in: trimmed)),
                      match.numberOfRanges == 3,
                      let numRange = Range(match.range(at: 1), in: trimmed),
                      let textRange = Range(match.range(at: 2), in: trimmed),
                      let number = Int(trimmed[numRange]) {
                blocks.append(MarkdownBlock(kind: .numbered(number: number, content: String(trimmed[textRange]))))
            } else {
                blocks.append(MarkdownBlock(kind: .paragraph(content: trimmed)))
            }
        }
        return blocks
    }
}
#endif
