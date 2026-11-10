import SwiftUI

/// The pipeline's steps, declared in the order the pipeline runs them — the
/// order of `cli.steps` in scripts/lib/media_pipeline/pipeline-schema.yaml, which
/// PipelineSchemaContractTests holds these cases and tokens to.
enum PipelineStep: String, CaseIterable, Identifiable {
    case ingest = "Ingest"
    case tag = "Tag"
    case fixTimestamps = "Fix Timestamps"
    case organize = "Organize"
    case gyroflow = "Gyroflow"
    case archiveSource = "Archive Source"

    var id: String { rawValue }

    var isAlwaysOn: Bool {
        self == .ingest || self == .organize
    }

    /// The token `--tasks` accepts for this step; nil for the fixed frame, which
    /// always runs and cannot be named.
    var taskToken: String? {
        switch self {
        case .ingest, .organize: nil
        case .tag: "tag"
        case .fixTimestamps: "fix-timestamp"
        case .gyroflow: "gyroflow"
        case .archiveSource: "archive-source"
        }
    }

    /// The token the pipeline's `stage_complete` event carries for this step.
    var stageToken: String {
        switch self {
        case .ingest: "ingest"
        case .tag: "tag"
        case .fixTimestamps: "fix-timestamp"
        case .organize: "output"
        case .gyroflow: "gyroflow"
        case .archiveSource: "archive-source"
        }
    }

    var systemImage: String {
        switch self {
        case .ingest: "sdcard"
        case .tag: "tag"
        case .fixTimestamps: "clock.arrow.2.circlepath"
        case .organize: "folder.badge.gearshape"
        case .gyroflow: "gyroscope"
        case .archiveSource: "archivebox"
        }
    }

    var iconColor: Color {
        switch self {
        case .ingest:        Theme.Accent.ingest
        case .tag:           Theme.Accent.tag
        case .fixTimestamps:   Theme.Accent.fixTimestamps
        case .organize:      Theme.Accent.organize
        case .gyroflow:      Theme.Accent.gyroflow
        case .archiveSource: Theme.Accent.archiveSource
        }
    }

    var label: String {
        switch self {
        case .ingest: Strings.Pipeline.ingestLabel
        case .tag: Strings.Pipeline.tagLabel
        case .fixTimestamps: Strings.Pipeline.fixTimestampsLabel
        case .organize: Strings.Pipeline.organizeLabel
        case .gyroflow: Strings.Pipeline.gyroflowLabel
        case .archiveSource: Strings.Pipeline.archiveSourceLabel
        }
    }

    /// The short name a results row shows while this is the last step it finished.
    var stageLabel: String {
        switch self {
        case .ingest: Strings.Pipeline.ingestLabel
        case .tag: Strings.Pipeline.tagLabel
        case .fixTimestamps: Strings.Pipeline.fixTimestampsStageLabel
        case .organize: Strings.Pipeline.organizeLabel
        case .gyroflow: Strings.Pipeline.gyroflowLabel
        case .archiveSource: Strings.Pipeline.archiveSourceLabel
        }
    }

    var help: String {
        switch self {
        case .ingest: Strings.Pipeline.ingestHelp
        case .tag: Strings.Pipeline.tagHelp
        case .fixTimestamps: Strings.Pipeline.fixTimestampsHelp
        case .organize: Strings.Pipeline.organizeHelp
        case .gyroflow: Strings.Pipeline.gyroflowHelp
        case .archiveSource: Strings.Pipeline.archiveSourceHelp
        }
    }
}
