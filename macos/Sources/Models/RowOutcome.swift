import Foundation

/// What a file's row reports happened to it, composed only from the tokens the
/// pipeline emitted: `timestamp_result.action` and `organize_result.action`.
///
/// The script decides an outcome and names it; the app renders that name. Which
/// other fields an event happens to carry is not an outcome — a skipped file still
/// reports the destination it would have gone to — so nothing here consults `dest`.
/// The token sets are enumerated in scripts/pipeline-schema.yaml and pinned to
/// these cases by PipelineSchemaContractTests.
struct RowOutcome {
    let correction: Correction?
    let movement: Movement?

    /// The `timestamp_result.action` tokens.
    enum Correction: String, CaseIterable {
        case fixed
        case wouldFix = "would_fix"
        case noChange = "no_change"
        case error
    }

    /// The `organize_result.action` tokens.
    enum Movement: String, CaseIterable {
        case copied
        case moved
        case overwrote
        case wouldCopy = "would_copy"
        case wouldMove = "would_move"
        case wouldOverwrite = "would_overwrite"
        case skipped
        case error
    }

    /// The `organize_result.reason` tokens: why a skipped file was not moved.
    enum SkipReason: String, CaseIterable {
        case identical
        case existsDiffers = "exists_differs"
        case userChoice = "user_choice"
    }

    init(timestampAction: String?, organizeAction: String?) {
        correction = timestampAction.flatMap(Correction.init(rawValue:))
        movement = organizeAction.flatMap(Movement.init(rawValue:))
    }

    /// The row's status, or nil when neither token describes a change and the
    /// caller should fall back to the pipeline's own verdict for the file.
    var statusLabel: String? {
        switch (correction?.statusLabel, movement) {
        case (nil, nil):
            return nil
        case (let correction?, nil):
            return correction
        case (nil, let movement?):
            return movement.statusLabel
        case (let correction?, let movement?):
            return Strings.DiffTable.combinedStatus(correction, movement.statusLabelAfterCorrection)
        }
    }
}

extension RowOutcome.Correction {
    /// nil where the timestamp contributes nothing to the status — such a row is
    /// described by what happened to its location instead.
    var statusLabel: String? {
        switch self {
        case .fixed: return Strings.DiffTable.fixedStatus
        case .wouldFix: return Strings.DiffTable.wouldFixStatus
        case .noChange, .error: return nil
        }
    }
}

extension RowOutcome.Movement {
    /// Every token the schema enumerates names an outcome here. The switch has no
    /// default, so a token added to the enum without a label stops compiling, and
    /// one added to the schema alone fails the contract test.
    var statusLabel: String {
        switch self {
        case .copied, .moved, .overwrote: return Strings.DiffTable.movedStatus
        case .wouldCopy, .wouldMove, .wouldOverwrite: return Strings.DiffTable.wouldMoveStatus
        case .skipped: return Strings.DiffTable.moveSkippedStatus
        case .error: return Strings.DiffTable.moveFailedStatus
        }
    }

    /// The same outcome phrased to follow a correction, as in "Would fix + move".
    var statusLabelAfterCorrection: String {
        switch self {
        case .copied, .moved, .overwrote: return Strings.DiffTable.movedStatusAfterFix
        case .wouldCopy, .wouldMove, .wouldOverwrite: return Strings.DiffTable.wouldMoveStatusAfterFix
        case .skipped: return Strings.DiffTable.moveSkippedStatusAfterFix
        case .error: return Strings.DiffTable.moveFailedStatusAfterFix
        }
    }
}

extension RowOutcome.SkipReason {
    /// Why the file stayed where it was, for the row's help text and the
    /// destination cell. A dry run never prompts, so it never claims a choice.
    var explanation: String {
        switch self {
        case .identical: return Strings.DiffTable.skipIdenticalHelp
        case .existsDiffers: return Strings.DiffTable.skipExistsDiffersHelp
        case .userChoice: return Strings.DiffTable.skipUserChoiceHelp
        }
    }
}
