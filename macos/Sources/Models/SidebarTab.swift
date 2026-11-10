import Foundation

enum SidebarTab: String, CaseIterable, Identifiable {
    case workflow = "Workflow"
    case profiles = "Profiles"
    case verify = "Verify"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .workflow: Strings.Nav.workflow
        case .profiles: Strings.Nav.profiles
        case .verify: Strings.Nav.verify
        }
    }

    var systemImage: String {
        switch self {
        case .workflow: "play.rectangle"
        case .profiles: "camera.on.rectangle"
        case .verify: "checkmark.shield"
        }
    }
}
