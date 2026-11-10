import Foundation

/// Where a row's file currently lives on disk: `dest` only once organize has
/// actually placed a file there (`copied`, `moved`, `overwrote`), otherwise the
/// path the pipeline read it from, as emitted on `pipeline_file`. `dest` is
/// present on skipped and dry-run rows too, so its presence alone is never
/// evidence that anything moved.
enum RowFileLocation {
    static func path(for row: DiffTableRow) -> String? {
        switch row.outcome.movement {
        case .copied, .moved, .overwrote:
            if let dest = row.dest {
                return dest
            }
        default:
            break
        }
        return row.sourcePath
    }
}
