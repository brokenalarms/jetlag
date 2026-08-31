import SwiftUI

struct LogOutputView: View {
    let lines: [LogLine]
    let holder: LogViewHolder
    var onClear: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: "terminal")
                    .foregroundStyle(.secondary)
                Text(Strings.LogOutput.title)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.secondary)
                Spacer()
                if !lines.isEmpty {
                    Text(Strings.LogOutput.lineCount(lines.count))
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
                Button {
                    let text = LogTextView.displayText(for: lines)
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(text, forType: .string)
                } label: {
                    Label(
                        Strings.LogOutput.copyAllButton,
                        systemImage: "doc.on.doc"
                    )
                }
                .buttonStyle(.borderless)
                .font(.caption)
                .disabled(lines.isEmpty)

                Button(Strings.LogOutput.clearButton) { onClear() }
                    .buttonStyle(.borderless)
                    .font(.caption)
                    .disabled(lines.isEmpty)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)

            LogTextView(lines: lines, holder: holder)
                .background(Color(nsColor: .textBackgroundColor).opacity(0.5))
        }
        .frame(maxHeight: .infinity)
    }
}

// MARK: - NSTextView wrapper for better performance and text selection

/// Shows the transcript in the session's own scroll view rather than one of its own, so
/// closing and reopening the panel neither rebuilds the text nor loses the user's place.
struct LogTextView: NSViewRepresentable {
    let lines: [LogLine]
    let holder: LogViewHolder

    static let font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)

    private static var textAttributes: [NSAttributedString.Key: Any] {
        [.font: font, .foregroundColor: NSColor.labelColor]
    }

    func makeNSView(context: Context) -> LogScrollView {
        holder.scrollView
    }

    /// Joins the lines' ANSI-stripped text for display or copying, so escape codes the
    /// scripts write for terminal-coloured stderr never reach the log panel or clipboard.
    static func displayText(for lines: [LogLine]) -> String {
        lines.map(\.strippedText).joined(separator: "\n")
    }

    func updateNSView(_ scrollView: LogScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView,
              let storage = textView.textStorage else {
            return
        }
        Self.render(lines, into: storage, holder: holder) {
            let wasAtBottom = Self.isScrolledToBottom(scrollView)
            return { scrollView.followTail(wasAtBottom) }
        }
    }

    /// Brings `storage` up to date with `lines` by appending only the lines added
    /// since the last render; a transcript that was cleared (fewer lines than
    /// rendered) is rebuilt. `beforeChange` runs only when something will change and
    /// returns the follow-up to run after it — the scroll-to-bottom decision has to be
    /// taken before the document grows.
    static func render(
        _ lines: [LogLine],
        into storage: NSTextStorage,
        holder: LogViewHolder,
        beforeChange: () -> () -> Void = { { } }
    ) {
        let rendered = holder.renderedCount
        if lines.count == rendered { return }
        let afterChange = beforeChange()
        if lines.count < rendered {
            storage.setAttributedString(
                NSAttributedString(string: displayText(for: lines), attributes: textAttributes))
        } else {
            let appended = lines[rendered...].map(\.strippedText).joined(separator: "\n")
            let prefix = rendered == 0 ? "" : "\n"
            storage.append(NSAttributedString(string: prefix + appended, attributes: textAttributes))
        }
        holder.renderedCount = lines.count
        afterChange()
    }

    private static func isScrolledToBottom(_ scrollView: NSScrollView) -> Bool {
        guard let textView = scrollView.documentView as? NSTextView else {
            return false
        }
        let visible = scrollView.contentView.documentVisibleRect
        // A panel opening for the first time renders its lines before it has been laid
        // out. There is no position the user chose to preserve in a view with no height,
        // and the log opens on the newest output, so it counts as parked at the tail.
        guard visible.height > 0 else { return true }
        return TableTailFollowing.isAtBottom(
            visibleMaxY: visible.maxY,
            documentHeight: textView.bounds.height)
    }
}
