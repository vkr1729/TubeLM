#if canImport(SwiftUI)
import SwiftUI

public enum AppThemeMode: String, CaseIterable, Identifiable {
    case light = "light"
    case dark = "dark"
    case system = "system"

    public var id: String { rawValue }

    public var colorScheme: ColorScheme? {
        switch self {
        case .light: return .light
        case .dark: return .dark
        case .system: return nil
        }
    }

    public var title: String {
        switch self {
        case .light: return "Light"
        case .dark: return "Dark"
        case .system: return "System"
        }
    }
}

@main
public struct TubeLMApp: App {
    @AppStorage("tubelm.themeMode") private var themeMode: String = AppThemeMode.light.rawValue

    public init() {}

    public var body: some Scene {
        WindowGroup {
            RootTabView()
                .preferredColorScheme(AppThemeMode(rawValue: themeMode)?.colorScheme ?? .light)
        }
    }
}
#endif
