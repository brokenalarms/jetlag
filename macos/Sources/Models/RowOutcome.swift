import Foundation

/// What a file's row reports happened to it, composed only from the tokens the
/// pipeline emitted: `timestamp_result.action`, `organize_result.action`,
/// `organize_result.reason`, and `pipeline_result`.
///
/// The script decides an outcome and names it; the app renders that name. Which
/// other fields an event happens to carry is not an outcome — a skipped file still
/// reports the destination it would have gone to — so nothing here consults `dest`.
/// The token sets are enumerated in scripts/pipeline-schema.yaml and pinned to
/// these cases by PipelineSchemaContractTests.
struct RowOutcome {
    let correction: Correction?
    let movement: Movement?
    let reason: SkipReason?
    let dryRun: Bool

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

    init(timestampAction: String?, organizeAction: String?,
         organizeReason: String? = nil, pipelineResult: String? = nil) {
        correction = timestampAction.flatMap(Correction.init(rawValue:))
        movement = organizeAction.flatMap(Movement.init(rawValue:))
        reason = organizeReason.flatMap(SkipReason.init(rawValue:))
        dryRun = pipelineResult == "would_change"
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
            return movement.statusLabel(reason: reason, dryRun: dryRun)
        case (let correction?, let movement?):
            return combinedStatusLabel(correction: correction, movement: movement)
        }
    }

    /// `movement`'s label following a correction — except a dry run's destination
    /// conflict, which names what Apply will actually do (prompt, then replace)
    /// rather than "skipped", and an identical file, which needs no move at all.
    private func combinedStatusLabel(correction: String, movement: Movement) -> String {
        if dryRun, movement == .skipped, reason == .identical {
            return Strings.DiffTable.wouldFixIdenticalStatus(correction)
        }
        return Strings.DiffTable.combinedStatus(correction, movement.statusLabelAfterCorrection(reason: reason, dryRun: dryRun))
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
    /// Every token the schema enumerates names one outcome here, and no two tokens
    /// share a label: a copy leaves the source where it is, a move does not, and a
    /// replacement means something at the destination is gone. The switch has no
    /// default, so a token added to the enum without a label stops compiling, and
    /// one added to the schema alone fails the contract test. `reason` and `dryRun`
    /// only change `.skipped`'s label: a dry run's destination conflict names what
    /// Apply will actually do (prompt, then replace) rather than "skipped".
    func statusLabel(reason: RowOutcome.SkipReason?, dryRun: Bool) -> String {
        switch self {
        case .copied: return Strings.DiffTable.copiedStatus
        case .moved: return Strings.DiffTable.movedStatus
        case .overwrote: return Strings.DiffTable.overwroteStatus
        case .wouldCopy: return Strings.DiffTable.wouldCopyStatus
        case .wouldMove: return Strings.DiffTable.wouldMoveStatus
        case .wouldOverwrite: return Strings.DiffTable.wouldOverwriteStatus
        case .skipped:
            if dryRun, reason == .existsDiffers { return Strings.DiffTable.wouldReplaceStatus }
            return Strings.DiffTable.moveSkippedStatus
        case .error: return Strings.DiffTable.moveFailedStatus
        }
    }

    /// The same outcome phrased to follow a correction, as in "Would fix + copy".
    func statusLabelAfterCorrection(reason: RowOutcome.SkipReason?, dryRun: Bool) -> String {
        switch self {
        case .copied: return Strings.DiffTable.copiedStatusAfterFix
        case .moved: return Strings.DiffTable.movedStatusAfterFix
        case .overwrote: return Strings.DiffTable.overwroteStatusAfterFix
        case .wouldCopy: return Strings.DiffTable.wouldCopyStatusAfterFix
        case .wouldMove: return Strings.DiffTable.wouldMoveStatusAfterFix
        case .wouldOverwrite: return Strings.DiffTable.wouldOverwriteStatusAfterFix
        case .skipped:
            if dryRun, reason == .existsDiffers { return Strings.DiffTable.wouldReplaceStatusAfterFix }
            return Strings.DiffTable.moveSkippedStatusAfterFix
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
