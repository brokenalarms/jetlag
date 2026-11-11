import SwiftUI

/// The text a table cell would draw, each part with the font it draws in, and what
/// else its measurement depends on.
struct CellText: Equatable {
    struct Part: Equatable {
        let text: String
        let font: NSFont
    }

    static let padding: CGFloat = 20

    let parts: [Part]
    let extraWidth: CGFloat
    let fixedWidth: CGFloat?
    let maxWidth: CGFloat

    init(_ parts: [(String, NSFont)] = [], extraWidth: CGFloat = 0,
         fixedWidth: CGFloat? = nil, maxWidth: CGFloat = .infinity) {
        self.parts = parts.map { Part(text: $0.0, font: $0.1) }
        self.extraWidth = extraWidth
        self.fixedWidth = fixedWidth
        self.maxWidth = maxWidth
    }

    /// What the auto-fitter applies: the cell's content width held to the column's cap.
    var idealWidth: CGFloat {
        min(contentFitWidth, maxWidth)
    }

    /// The width that shows the cell's widest content untruncated, ignoring the cap —
    /// what double-clicking a header divider snaps the column to. Kept alongside the
    /// capped width rather than replacing it: the cap keeps a long writes subtitle from
    /// stretching the table, and this is the width that shows the user the whole thing.
    var contentFitWidth: CGFloat {
        if let fixedWidth { return fixedWidth }
        let widest = parts
            .filter { !$0.text.isEmpty }
            .map { ($0.text as NSString).size(withAttributes: [.font: $0.font]).width }
            .max() ?? 0
        guard widest > 0 else { return 0 }
        return widest + extraWidth + Self.padding
    }
}

/// The two widths every column has: `fitted` is what the auto-fitter applies — each
/// column's content width held to its cap — and `contentFit` is the same content
/// measured without that cap, which a header divider double-click snaps to.
struct ColumnWidths: Equatable {
    var fitted: [CGFloat] = []
    var contentFit: [CGFloat] = []
}

/// Per-run cache of the column widths, which depend on every row. A row's cell text
/// is a function of the row and the columns alone, so a row is measured when it first
/// appears and again only when it changes — a run's live row fills in as its events
/// arrive and is then replaced by the finalised row at the same index — and the column
/// widths are the running maxima. Deciding a row is unchanged compares the row, not its
/// text: building the text (a status is a localized string) for every row on every
/// update made a long run cost more with each file, and the app fell minutes behind a
/// pipeline that had already finished.
class ColumnMeasurements<Row: Identifiable & Equatable> {
    private struct Measured {
        let row: Row
        let widths: ColumnWidths
    }

    private var titles: [String] = []
    private var measured: [Row.ID: Measured] = [:]
    private var widths = ColumnWidths()
    /// How many rows have had their text measured, for tests that pin the cache.
    private(set) var measurementCount = 0

    /// `titles` names the columns the text is built for: a different set of columns
    /// (a Verify check against other locations) measures every row afresh.
    func columnWidths(for rows: [Row], titles: [String], texts: (Row) -> [CellText]) -> ColumnWidths {
        if titles != self.titles {
            self.titles = titles
            measured = [:]
            widths = ColumnWidths()
        }
        var seen = Set<Row.ID>()
        for row in rows {
            seen.insert(row.id)
            if measured[row.id]?.row == row {
                continue
            }
            let cells = texts(row)
            let cellWidths = ColumnWidths(fitted: cells.map(\.idealWidth),
                                          contentFit: cells.map(\.contentFitWidth))
            measurementCount += 1
            measured[row.id] = Measured(row: row, widths: cellWidths)
            widths = Self.folding(cellWidths, into: widths)
        }
        if seen.count < measured.count {
            // Rows were removed (a cleared table): drop what is no longer shown and
            // rebuild the maxima from what remains.
            measured = measured.filter { seen.contains($0.key) }
            widths = measured.values.reduce(ColumnWidths()) { Self.folding($1.widths, into: $0) }
        }
        return widths
    }

    /// A column is as wide as its widest row needs, so folding a row's widths into the
    /// running maxima is a per-column max — growing the maxima to the row's column
    /// count first, since a row can carry cells for columns nothing has filled yet.
    private static func folding(_ row: ColumnWidths, into running: ColumnWidths) -> ColumnWidths {
        ColumnWidths(fitted: folding(row.fitted, into: running.fitted),
                     contentFit: folding(row.contentFit, into: running.contentFit))
    }

    private static func folding(_ row: [CGFloat], into running: [CGFloat]) -> [CGFloat] {
        var maxima = running
        if maxima.count < row.count {
            maxima.append(contentsOf: repeatElement(0, count: row.count - maxima.count))
        }
        for (index, width) in row.enumerated() where width > maxima[index] {
            maxima[index] = width
        }
        return maxima
    }
}
