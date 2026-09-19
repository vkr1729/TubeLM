#if canImport(SwiftUI)
import SwiftUI

@main
public struct TubeLMApp: App {
    public init() {}

    public var body: some Scene {
        WindowGroup {
            RootTabView()
                .preferredColorScheme(nil) // Respect system light/dark mode preference
        }
    }
}
#endif
