import Foundation

/// Where a row's file currently lives on disk: `dest` only once organize has
/// actually placed a file there (`copied`, `moved`, `overwrote`), otherwise
/// wherever the pipeline read it from, under `sourceDir`. `dest` is present on
/// skipped and dry-run rows too, so its presence alone is never evidence that
/// anything moved.
///
/// The pre-move path is a guess, not a certainty: the pipeline's
/// `pipeline_file` event only ever carries a basename (`file_path.name`), and
/// the source scan is recursive, so two same-named files in different
/// subdirectories of `sourceDir` would resolve to the same path here.
enum RowFileLocation {
    static func path(for row: DiffTableRow, sourceDir: String) -> String? {
        switch row.outcome.movement {
        case .copied, .moved, .overwrote:
            if let dest = row.dest {
                return dest
            }
        default:
            break
        }
        guard !sourceDir.isEmpty else { return nil }
        return (sourceDir as NSString).appendingPathComponent(row.file)
    }

    static func exists(
        for row: DiffTableRow, sourceDir: String, fileManager: FileManager = .default
    ) -> Bool {
        guard let path = path(for: row, sourceDir: sourceDir) else { return false }
        return fileManager.fileExists(atPath: path)
    }
}
