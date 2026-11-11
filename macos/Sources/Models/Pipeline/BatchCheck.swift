import Foundation

/// One finding of a batch-level check, as the pipeline's `batch_check` event
/// reported it. The script decides everything here, including whether the run
/// stopped on it; the app only renders it and, when asked, passes its flag.
struct BatchCheck: Equatable {
    /// The `batch_check.check` tokens.
    enum Kind: String, CaseIterable {
        case protectedSources = "protected_sources"
        case cameraMismatch = "camera_mismatch"
        case mixedTimezones = "mixed_timezones"
        case zoneRelabel = "zone_relabel"
        case filenameUnparseable = "filename_unparseable"
        case sourceReadOnly = "source_read_only"
        case destinationOccupied = "destination_occupied"
    }

    /// The group `mixed_timezones` puts files with no zone evidence under.
    static let noZoneGroup = "none"

    let kind: Kind
    let files: [String]
    let groups: [String: [String]]
    /// What the groups were held against, as offsets like the group labels.
    let chosen: [String]
    let assentFlag: String?
    let refused: Bool
}
