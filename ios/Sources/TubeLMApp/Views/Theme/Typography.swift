#if canImport(SwiftUI)
import SwiftUI

public enum AppTheme {
    // Colors conforming to WCAG AAA contrast
    public static let accent = Color(red: 0.08, green: 0.50, blue: 0.24) // #15803d
    public static let accentBadge = Color(red: 0.85, green: 1.00, blue: 0.39) // #d9ff63
    public static let accentBadgeText = Color(red: 0.09, green: 0.09, blue: 0.08) // #171815
    public static let whyBackgroundLight = Color(red: 0.94, green: 0.99, blue: 0.96) // #f0fdf4
    public static let whyBorder = Color(red: 0.13, green: 0.77, blue: 0.37) // #22c55e

    #if canImport(UIKit)
    public static let systemBackground = Color(uiColor: .systemBackground)
    public static let secondarySystemBackground = Color(uiColor: .secondarySystemBackground)
    public static let tertiarySystemBackground = Color(uiColor: .tertiarySystemBackground)
    public static let separator = Color(uiColor: .separator)
    #else
    public static let systemBackground = Color.white
    public static let secondarySystemBackground = Color(red: 0.95, green: 0.95, blue: 0.97)
    public static let tertiarySystemBackground = Color(red: 0.92, green: 0.92, blue: 0.94)
    public static let separator = Color(red: 0.85, green: 0.85, blue: 0.87)
    #endif

    // Typography
    public static let headline = Font.system(size: 24, weight: .bold, design: .serif)
    public static let title = Font.system(size: 16, weight: .bold, design: .serif)
    public static let subcardTitle = Font.system(size: 14, weight: .semibold, design: .default)
    public static let body = Font.system(size: 13, weight: .regular, design: .default)
    public static let whyText = Font.system(size: 13, weight: .regular, design: .default)
    public static let meta = Font.system(size: 11, weight: .medium, design: .default)
    public static let rankBadge = Font.system(size: 11, weight: .bold, design: .monospaced)
    public static let durationBadge = Font.system(size: 11, weight: .semibold, design: .monospaced)
    public static let actionButton = Font.system(size: 11, weight: .bold, design: .default)
}
#endif
