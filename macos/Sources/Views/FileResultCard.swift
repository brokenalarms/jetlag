import SwiftUI

struct FileResultCard: View {
    let file: ProcessedFile

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    var body: some View {
        HStack(spacing: 12) {
            statusBadge
            fileInfo
            Spacer()
            timestampComparison
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .strokeBorder(borderColor, lineWidth: 1)
        )
    }

    // MARK: - Status badge

    private var statusBadge: some View {
        Image(systemName: file.statusIcon)
            .font(.system(size: 16))
            .foregroundStyle(statusColor)
    }

    // MARK: - File info (left side)

    private var fileInfo: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(file.filename)
                .font(.system(size: 12, weight: .medium, design: .monospaced))
                .lineLimit(1)
                .truncationMode(.middle)

            if let dest = file.destination {
                let folder = (dest as NSString).deletingLastPathComponent
                let short = shortenPath(folder)
                Text("→ \(short)")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.head)
            }
        }
        .frame(minWidth: 140, alignment: .leading)
    }

    // MARK: - Timestamp comparison (right side)

    @ViewBuilder
    private var timestampComparison: some View {
        if file.status == .unchanged {
            unchangedBadge
        } else if file.originalTime != nil || file.correctedTime != nil {
            HStack(spacing: 8) {
                if let orig = file.originalDate {
                    VStack(alignment: .trailing, spacing: 1) {
                        Text(Self.timeFormatter.string(from: orig))
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(.secondary)
                        Text(Self.dateFormatter.string(from: orig))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(.tertiary)
                    }
                }

                if file.shift != nil || (file.originalTime != nil && file.correctedTime != nil && file.originalTime != file.correctedTime) {
                    shiftBadge
                }

                if let corr = file.correctedDate {
                    VStack(alignment: .trailing, spacing: 1) {
                        Text(Self.timeFormatter.string(from: corr))
                            .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        Text(Self.dateFormatter.string(from: corr))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
    }

    private var shiftBadge: some View {
        Text(file.shift ?? "→")
            .font(.system(size: 9, weight: .bold, design: .monospaced))
            .foregroundStyle(Color("NeonYellow"))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color("NeonYellow").opacity(0.15))
            .clipShape(Capsule())
    }

    private var unchangedBadge: some View {
        Text("No change")
            .font(.system(size: 10))
            .foregroundStyle(.secondary)
    }

    // MARK: - Styling

    private var statusColor: Color {
        switch file.status {
        case .processing: return .secondary
        case .changed: return Color("NeonYellow")
        case .unchanged: return .green.opacity(0.7)
        case .failed: return .red
        }
    }

    private var borderColor: Color {
        switch file.status {
        case .changed: return Color("NeonYellow").opacity(0.2)
        case .failed: return Color.red.opacity(0.3)
        default: return Color.secondary.opacity(0.15)
        }
    }

    private var cardBackground: Color {
        switch file.status {
        case .changed: return Color("NeonYellow").opacity(0.03)
        case .failed: return Color.red.opacity(0.03)
        default: return Color(nsColor: .textBackgroundColor).opacity(0.3)
        }
    }

    private func shortenPath(_ path: String) -> String {
        let components = path.components(separatedBy: "/")
        if components.count <= 3 { return path }
        return components.suffix(3).joined(separator: "/")
    }
}
