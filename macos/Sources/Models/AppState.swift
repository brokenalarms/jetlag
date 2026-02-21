import Foundation
import SwiftUI

enum SidebarTab: String, CaseIterable, Identifiable {
    case workflow = "Workflow"
    case profiles = "Profiles"

    var id: String { rawValue }

    var systemImage: String {
        switch self {
        case .workflow: "play.rectangle"
        case .profiles: "camera.on.rectangle"
        }
    }
}

enum PipelineStep: String, CaseIterable, Identifiable {
    case importFromCard = "Import"
    case tag = "Tag"
    case fixTimezone = "Fix Timezone"
    case organize = "Organize"
    case gyroflow = "Gyroflow"

    var id: String { rawValue }

    var systemImage: String {
        switch self {
        case .importFromCard: "sdcard"
        case .tag: "tag"
        case .fixTimezone: "clock.arrow.2.circlepath"
        case .organize: "folder.badge.gearshape"
        case .gyroflow: "gyroscope"
        }
    }

    /// Neon accent colour for each step's icon — sourced from design/tokens.json via Assets.xcassets.
    var iconColor: Color {
        switch self {
        case .importFromCard: Color("NeonCyan")
        case .tag:            Color("NeonPink")
        case .fixTimezone:    Color("NeonYellow")
        case .organize:       Color.accentColor
        case .gyroflow:       Color("NeonPurple")
        }
    }

    var help: String {
        switch self {
        case .importFromCard: "Copy files from source (memory card) to import directory"
        case .tag: "Apply Finder tags and EXIF metadata from profile"
        case .fixTimezone: "Correct timestamps for your video editor using the selected timezone"
        case .organize: "Sort files into date-based folder structure in the ready directory"
        case .gyroflow: "Generate Gyroflow stabilization project files (requires gyro data)"
        }
    }
}

struct LogLine: Identifiable {
    let id = UUID()
    let text: String
    let stream: Stream

    enum Stream {
        case stdout, stderr
    }

    var isMachineReadable: Bool {
        text.hasPrefix("@@")
    }
}

@Observable
final class AppState {
    var selectedTab: SidebarTab = .workflow

    let scriptsDirectory: String
    var profilesFilePath: String {
        didSet { UserDefaults.standard.set(profilesFilePath, forKey: "profilesFilePath") }
    }

    var profilesConfig: ProfilesConfig?
    var profileLoadError: ProfileLoadError?

    var sortedProfileNames: [String] {
        profilesConfig?.profiles.keys.sorted() ?? []
    }

    // Workflow state
    var selectedProfile: String = ""
    var subfolder: String = ""
    var sourceDir: String = ""
    var timezone: String = ""
    var useTimezonePicker: Bool = true
    var skipCompanion: Bool = false
    var preserveSource: Bool = true
    var applyMode: Bool = false

    var enabledSteps: Set<PipelineStep> = Set(PipelineStep.allCases)

    // Execution state
    var isRunning: Bool = false
    var logOutput: [LogLine] = []
    var currentProcess: Process?

    init() {
        self.scriptsDirectory = (Bundle.main.resourcePath! as NSString)
            .appendingPathComponent("scripts")
        self.profilesFilePath = UserDefaults.standard.string(forKey: "profilesFilePath") ?? ""
    }

    var resolvedProfilesPath: String {
        if profilesFilePath.isEmpty {
            return (scriptsDirectory as NSString).appendingPathComponent("media-profiles.yaml")
        }
        return profilesFilePath
    }

    var activeProfile: MediaProfile? {
        profilesConfig?.profiles[selectedProfile]
    }

    func profile(named name: String) -> MediaProfile? {
        profilesConfig?.profiles[name]
    }

    var availableSteps: [PipelineStep] {
        guard let profile = activeProfile else { return [] }
        var steps: [PipelineStep] = [.importFromCard, .tag, .fixTimezone, .organize]
        if profile.gyroflowEnabled == true {
            steps.append(.gyroflow)
        }
        return steps
    }

    func clearLog() {
        logOutput = []
    }

    func appendLog(_ line: LogLine) {
        logOutput.append(line)
    }

    func cancelRunning() {
        currentProcess?.terminate()
        currentProcess = nil
        isRunning = false
    }
}
