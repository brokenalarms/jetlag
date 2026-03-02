import SwiftUI

/// Horizontal timeline visualization showing files as colored blocks positioned by timestamp.
/// Displays "Before" (original timestamps) and "After" (corrected timestamps) rows so users
/// can see how Jetlag fixes the timeline ordering.
struct TimelinePreviewView: View {
    let rows: [DiffTableRow]

    private static let barHeight: CGFloat = 22
    private static let barSpacing: CGFloat = 3
    private static let axisHeight: CGFloat = 24
    private static let labelWidth: CGFloat = 54
    private static let padding: CGFloat = 16

    /// Assign neon colors to files in order of appearance.
    private static let palette: [Color] = [
        Color("NeonCyan"),
        Color("NeonPink"),
        Color("NeonYellow"),
        Color("NeonPurple"),
    ]

    // MARK: - Parsed data

    private struct TimelineFile: Identifiable {
        let id: UUID
        let file: String
        let originalMinutes: Double?
        let correctedMinutes: Double?
        let color: Color
    }

    private var files: [TimelineFile] {
        let eligible = rows.filter { $0.originalTime != nil || $0.correctedTime != nil }
        return eligible.enumerated().map { index, row in
            TimelineFile(
                id: row.id,
                file: row.file,
                originalMinutes: Self.parseToMinutes(row.originalTime),
                correctedMinutes: Self.parseToMinutes(row.correctedTime),
                color: Self.palette[index % Self.palette.count]
            )
        }
    }

    /// Scale covering both original and corrected times so bars align across rows.
    private var scale: TimelineScale? {
        let allMinutes = files.flatMap { [$0.originalMinutes, $0.correctedMinutes] }.compactMap { $0 }
        guard let minTime = allMinutes.min(), let maxTime = allMinutes.max() else { return nil }
        return TimelineScale(minTime: minTime, maxTime: maxTime)
    }

    // MARK: - Body

    var body: some View {
        VStack(spacing: 0) {
            header
            if let scale, !files.isEmpty {
                timelineContent(scale: scale)
            } else {
                emptyState
            }
        }
        .frame(maxHeight: .infinity)
    }

    private var header: some View {
        HStack(spacing: 6) {
            Image(systemName: "timeline.selection")
                .foregroundStyle(.secondary)
            Text(Strings.Timeline.title)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.secondary)
            Spacer()
            if !files.isEmpty {
                Text(Strings.Timeline.fileCount(files.count))
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private func timelineContent(scale: TimelineScale) -> some View {
        GeometryReader { geo in
            let barArea = geo.size.width - Self.labelWidth - Self.padding * 2
            ScrollView(.vertical) {
                VStack(alignment: .leading, spacing: 12) {
                    // Before row
                    timelineRow(
                        label: Strings.Timeline.beforeLabel,
                        labelColor: .red.opacity(0.8),
                        files: files,
                        keyPath: \.originalMinutes,
                        scale: scale,
                        barArea: barArea,
                        dimmed: true
                    )

                    // After row
                    timelineRow(
                        label: Strings.Timeline.afterLabel,
                        labelColor: Color("NeonPink").opacity(0.8),
                        files: files,
                        keyPath: \.correctedMinutes,
                        scale: scale,
                        barArea: barArea,
                        dimmed: false
                    )

                    // Time axis
                    timeAxis(scale: scale, barArea: barArea)

                    // Legend
                    legend
                }
                .padding(Self.padding)
            }
        }
    }

    private var emptyState: some View {
        VStack {
            Spacer()
            Text(Strings.Timeline.emptyLabel)
                .font(.subheadline)
                .foregroundStyle(.tertiary)
            Spacer()
        }
    }

    // MARK: - Timeline rows

    private func timelineRow(
        label: String,
        labelColor: Color,
        files: [TimelineFile],
        keyPath: KeyPath<TimelineFile, Double?>,
        scale: TimelineScale,
        barArea: CGFloat,
        dimmed: Bool
    ) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Circle()
                    .fill(labelColor)
                    .frame(width: 6, height: 6)
                Text(label)
                    .font(.system(size: 10, weight: .semibold))
                    .textCase(.uppercase)
                    .tracking(1)
                    .foregroundStyle(labelColor)
            }

            ZStack(alignment: .leading) {
                // Track background
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.primary.opacity(0.03))
                    .frame(height: max(CGFloat(files.count) * (Self.barHeight + Self.barSpacing), Self.barHeight))

                // File bars
                VStack(alignment: .leading, spacing: Self.barSpacing) {
                    ForEach(files) { file in
                        if let minutes = file[keyPath: keyPath] {
                            fileBar(
                                file: file,
                                offset: scale.offset(minutes, in: barArea),
                                barArea: barArea,
                                dimmed: dimmed
                            )
                        } else {
                            // No timestamp — show placeholder
                            missingBar(file: file)
                        }
                    }
                }
            }
            .padding(.leading, Self.labelWidth)
        }
    }

    private func fileBar(file: TimelineFile, offset: CGFloat, barArea: CGFloat, dimmed: Bool) -> some View {
        let barWidth = max(barArea * 0.12, 60)
        let clampedOffset = min(offset, max(barArea - barWidth, 0))
        return Text(file.file)
            .font(.system(size: 9, design: .monospaced))
            .lineLimit(1)
            .truncationMode(.middle)
            .foregroundStyle(file.color.opacity(dimmed ? 0.6 : 0.9))
            .padding(.horizontal, 6)
            .frame(width: barWidth, height: Self.barHeight, alignment: .leading)
            .background(file.color.opacity(dimmed ? 0.1 : 0.2))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .strokeBorder(file.color.opacity(dimmed ? 0.15 : 0.3), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 4))
            .offset(x: clampedOffset)
    }

    private func missingBar(file: TimelineFile) -> some View {
        Text(file.file)
            .font(.system(size: 9, design: .monospaced))
            .lineLimit(1)
            .truncationMode(.middle)
            .foregroundStyle(.tertiary)
            .padding(.horizontal, 6)
            .frame(height: Self.barHeight, alignment: .leading)
    }

    // MARK: - Axis

    private func timeAxis(scale: TimelineScale, barArea: CGFloat) -> some View {
        let ticks = scale.ticks()
        return VStack(spacing: 0) {
            Rectangle()
                .fill(Color.primary.opacity(0.08))
                .frame(height: 1)

            ZStack(alignment: .leading) {
                ForEach(ticks, id: \.label) { tick in
                    let px = scale.offset(tick.minutes, in: barArea)
                    VStack(spacing: 2) {
                        Rectangle()
                            .fill(Color.primary.opacity(tick.isMajor ? 0.15 : 0.08))
                            .frame(width: 1, height: 6)
                        Text(tick.label)
                            .font(.system(size: 9))
                            .foregroundStyle(Color.primary.opacity(tick.isMajor ? 0.3 : 0.2))
                    }
                    .offset(x: px - 0.5)
                }
            }
            .frame(height: Self.axisHeight)
        }
        .padding(.leading, Self.labelWidth)
    }

    // MARK: - Legend

    private var legend: some View {
        let visible = files.prefix(8)
        return FlowLayout(spacing: 6) {
            ForEach(Array(visible)) { file in
                HStack(spacing: 4) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(file.color.opacity(0.5))
                        .frame(width: 8, height: 8)
                    Text(file.file)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            if files.count > 8 {
                Text(Strings.Timeline.moreFiles(files.count - 8))
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.leading, Self.labelWidth)
    }

    // MARK: - Timestamp parsing

    /// Parse exiftool-format timestamp "YYYY:MM:DD HH:MM:SS" to minutes since midnight.
    /// Supports multi-day spans by using day offsets.
    static func parseToMinutes(_ timestamp: String?) -> Double? {
        guard let ts = timestamp else { return nil }
        // Format: "2025:03:15 09:30:00" or "2025-03-15T09:30:00"
        let parts = ts.split(whereSeparator: { $0 == " " || $0 == "T" })
        guard parts.count >= 2 else { return nil }
        let timePart = parts[1]
        let timeComponents = timePart.split(separator: ":")
        guard timeComponents.count >= 2,
              let hours = Double(timeComponents[0]),
              let minutes = Double(timeComponents[1]) else { return nil }
        let seconds = timeComponents.count >= 3 ? (Double(timeComponents[2]) ?? 0) : 0

        // Include date for multi-day support
        let datePart = parts[0]
        let dateComponents = datePart.split(whereSeparator: { $0 == ":" || $0 == "-" })
        guard dateComponents.count >= 3,
              let day = Double(dateComponents[2]) else {
            return hours * 60 + minutes + seconds / 60
        }

        // Use day as offset (relative positioning handles the rest)
        return day * 1440 + hours * 60 + minutes + seconds / 60
    }
}

// MARK: - Timeline scale

private struct TimelineScale {
    let minTime: Double
    let maxTime: Double

    private let padMinutes: Double = 30

    var scaleStart: Double { max(0, minTime - padMinutes) }
    var scaleEnd: Double { maxTime + padMinutes }
    var duration: Double { scaleEnd - scaleStart }

    func offset(_ minutes: Double, in barArea: CGFloat) -> CGFloat {
        guard duration > 0 else { return 0 }
        let fraction = (minutes - scaleStart) / duration
        return CGFloat(fraction) * barArea
    }

    struct Tick {
        let minutes: Double
        let label: String
        let isMajor: Bool
    }

    func ticks() -> [Tick] {
        let durationMin = scaleEnd - scaleStart
        let interval: Double = durationMin > 15 * 60 ? 360 : durationMin > 6 * 60 ? 180 : durationMin > 3 * 60 ? 120 : 60

        var result: [Tick] = []
        let startHour = Int(ceil(scaleStart / 60))
        let endHour = Int(floor(scaleEnd / 60))

        for h in startHour...endHour {
            let minuteValue = Double(h * 60)
            if minuteValue.truncatingRemainder(dividingBy: interval) != 0 { continue }
            let displayHour = h % 24
            let day = h / 24
            var label = String(format: "%02d:00", displayHour)
            if day > 0 && displayHour == 0 {
                label = "Day \(day + 1)"
            }
            result.append(Tick(
                minutes: minuteValue,
                label: label,
                isMajor: minuteValue.truncatingRemainder(dividingBy: max(interval, 120)) == 0
            ))
        }
        return result
    }
}

// MARK: - Flow layout for legend

private struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = arrangeSubviews(proposal: proposal, subviews: subviews)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrangeSubviews(
            proposal: ProposedViewSize(width: bounds.width, height: bounds.height),
            subviews: subviews
        )
        for (index, position) in result.positions.enumerated() where index < subviews.count {
            subviews[index].place(at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y),
                                  proposal: .unspecified)
        }
    }

    private struct LayoutResult {
        var positions: [CGPoint]
        var size: CGSize
    }

    private func arrangeSubviews(proposal: ProposedViewSize, subviews: Subviews) -> LayoutResult {
        let maxWidth = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var maxX: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth, x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
            maxX = max(maxX, x)
        }

        return LayoutResult(
            positions: positions,
            size: CGSize(width: maxX, height: y + rowHeight)
        )
    }
}
