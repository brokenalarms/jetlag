import SwiftUI

struct ResultsColumn<Row> {
    let title: String
    let minWidth: CGFloat
    let idealWidth: CGFloat?
    let measure: (Row) -> CellText
    let cell: (Row) -> AnyView

    init(_ title: String, minWidth: CGFloat, idealWidth: CGFloat? = nil,
         measure: @escaping (Row) -> CellText,
         @ViewBuilder cell: @escaping (Row) -> some View) {
        self.title = title
        self.minWidth = minWidth
        self.idealWidth = idealWidth
        self.measure = measure
        self.cell = { AnyView(cell($0)) }
    }
}

struct ResultsMenuItem {
    let title: String
    let urls: [URL]
}

/// The files table, generic over its row and columns. Every row resolves to the file
/// the Show in Finder / Quick Look commands act on through `fileURL`; the caller adds
/// its own context-menu items with `extraMenuItems`, given the selected rows.
struct ResultsTable<Row: Identifiable>: View {
    let rows: [Row]
    let columns: [ResultsColumn<Row>]
    let measurements: ColumnMeasurements
    let fileURL: (Row) -> URL?
    var extraMenuItems: ([Row]) -> [ResultsMenuItem] = { _ in [] }

    @State private var selection: Set<Row.ID> = []
    @State private var previewCoordinator = QuickLookCoordinator()

    /// The rows selected by the given ids, resolved to the file URLs Show in Finder /
    /// Quick Look act on. Every row the pipeline reported resolves to a path, so the
    /// menu items stay enabled: whether that path still holds a file is Finder's
    /// answer to give, not a reason to withhold the command.
    static func fileURLs(for ids: Set<Row.ID>, in rows: [Row], locating fileURL: (Row) -> URL?) -> [URL] {
        rows.filter { ids.contains($0.id) }.compactMap(fileURL)
    }

    private var columnWidths: ColumnWidths {
        measurements.columnWidths(for: rows) { row in columns.map { $0.measure(row) } }
    }

    private func selectedFileURLs(_ ids: Set<Row.ID>) -> [URL] {
        Self.fileURLs(for: ids, in: rows, locating: fileURL)
    }

    var body: some View {
        table
            .contextMenu(forSelectionType: Row.ID.self) { ids in
                let urls = selectedFileURLs(ids)
                Button(Strings.DiffTable.showInFinder) {
                    NSWorkspace.shared.activateFileViewerSelecting(urls)
                }

                Button(Strings.DiffTable.quickLook) {
                    previewCoordinator.show(urls)
                }

                ForEach(extraMenuItems(rows.filter { ids.contains($0.id) }), id: \.title) { item in
                    Button(item.title) {
                        NSWorkspace.shared.activateFileViewerSelecting(item.urls)
                    }
                }
            }
            .onKeyPress(.space) {
                let urls = selectedFileURLs(selection)
                guard !urls.isEmpty else { return .ignored }
                previewCoordinator.show(urls)
                return .handled
            }
            .background {
                ColumnAutoSizer(widths: columnWidths, rowCount: rows.count)
                    .frame(width: 0, height: 0)
            }
    }

    private func column(_ index: Int) -> some TableColumnContent<Row, Never> {
        let column = columns[index]
        return TableColumn(column.title) { row in column.cell(row) }
            .width(min: column.minWidth, ideal: column.idealWidth)
    }

    /// `Table` takes its columns from a result builder, which has no runtime-count form
    /// below macOS 14.4, so the column count selects one of these fixed arities (1...10).
    @ViewBuilder
    private var table: some View {
        switch columns.count {
        case 1: Table(rows, selection: $selection) { column(0) }
        case 2: Table(rows, selection: $selection) { column(0); column(1) }
        case 3: Table(rows, selection: $selection) { column(0); column(1); column(2) }
        case 4: Table(rows, selection: $selection) { column(0); column(1); column(2); column(3) }
        case 5: Table(rows, selection: $selection) { column(0); column(1); column(2); column(3); column(4) }
        case 6:
            Table(rows, selection: $selection) {
                column(0); column(1); column(2); column(3); column(4); column(5)
            }
        case 7:
            Table(rows, selection: $selection) {
                column(0); column(1); column(2); column(3); column(4); column(5); column(6)
            }
        case 8:
            Table(rows, selection: $selection) {
                column(0); column(1); column(2); column(3); column(4); column(5); column(6); column(7)
            }
        case 9:
            Table(rows, selection: $selection) {
                column(0); column(1); column(2); column(3); column(4)
                column(5); column(6); column(7); column(8)
            }
        case 10:
            Table(rows, selection: $selection) {
                column(0); column(1); column(2); column(3); column(4)
                column(5); column(6); column(7); column(8); column(9)
            }
        default: EmptyView()
        }
    }
}
