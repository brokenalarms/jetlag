import SwiftUI

struct LogOutputView: View {
    let lines: [LogLine]
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

            LogTextView(lines: lines)
                .background(Color(nsColor: .textBackgroundColor).opacity(0.5))
        }
        .frame(maxHeight: .infinity)
    }
}

// MARK: - NSTextView wrapper for better performance and text selection

struct LogTextView: NSViewRepresentable {
    let lines: [LogLine]

    /// Tracks how much of `lines` the text view already shows, so an update appends
    /// only what is new. Rebuilding the whole transcript per line is O(n²) over a
    /// run — thousands of lines — and was what left the app far behind the pipeline.
    final class Coordinator {
        var renderedCount = 0
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    static let font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)

    private static var textAttributes: [NSAttributedString.Key: Any] {
        [.font: font, .foregroundColor: NSColor.labelColor]
    }

    func makeNSView(context: Context) -> NSScrollView {
        Self.makeScrollView()
    }

    /// Built by hand rather than with `NSTextView.scrollableTextView()` so the scroll
    /// view is a `ContentAgnosticScrollView`: log text grows line by line while a run
    /// streams, and a scroll view that sized itself from its document would report a
    /// new min size to the inspector on every appended line.
    static func makeScrollView() -> NSScrollView {
        let scrollView = ContentAgnosticScrollView()
        scrollView.borderType = .noBorder
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = false
        scrollView.detachSizeFromContent()

        let textView = NSTextView(frame: NSRect(origin: .zero, size: scrollView.contentSize))
        textView.minSize = NSSize(width: 0, height: 0)
        textView.maxSize = NSSize(
            width: CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.containerSize = NSSize(
            width: scrollView.contentSize.width,
            height: CGFloat.greatestFiniteMagnitude)

        textView.isEditable = false
        textView.isSelectable = true
        textView.font = font
        textView.textColor = .labelColor
        textView.backgroundColor = .clear
        textView.textContainerInset = NSSize(width: 10, height: 6)
        textView.autoresizingMask = [.width]

        scrollView.documentView = textView
        return scrollView
    }

    /// Joins the lines' ANSI-stripped text for display or copying, so escape codes the
    /// scripts write for terminal-coloured stderr never reach the log panel or clipboard.
    static func displayText(for lines: [LogLine]) -> String {
        lines.map(\.strippedText).joined(separator: "\n")
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView,
              let storage = textView.textStorage else {
            return
        }
        Self.render(lines, into: storage, coordinator: context.coordinator) {
            let wasAtBottom = Self.isScrolledToBottom(scrollView)
            return {
                if wasAtBottom {
                    textView.scrollToEndOfDocument(nil)
                }
            }
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
        coordinator: Coordinator,
        beforeChange: () -> () -> Void = { { } }
    ) {
        let rendered = coordinator.renderedCount
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
        coordinator.renderedCount = lines.count
        afterChange()
    }

    private static func isScrolledToBottom(_ scrollView: NSScrollView) -> Bool {
        guard let textView = scrollView.documentView as? NSTextView else {
            return false
        }
        let visibleRect = scrollView.contentView.documentVisibleRect
        let contentHeight = textView.bounds.height
        return visibleRect.maxY >= contentHeight - 10  // 10pt threshold
    }
}
