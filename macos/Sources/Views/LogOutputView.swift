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
                    let text = lines.map(\.text).joined(separator: "\n")
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
        scrollView.hasHorizontalScroller = true
        scrollView.autohidesScrollers = true
        scrollView.scrollerStyle = .legacy
        scrollView.drawsBackground = false
        scrollView.detachSizeFromContent()

        let textView = NSTextView(frame: NSRect(origin: .zero, size: scrollView.contentSize))
        textView.minSize = NSSize(width: 0, height: 0)
        textView.maxSize = NSSize(
            width: CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = true
        textView.textContainer?.widthTracksTextView = false
        textView.textContainer?.containerSize = NSSize(
            width: CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude)

        textView.isEditable = false
        textView.isSelectable = true
        textView.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        textView.textColor = .labelColor
        textView.backgroundColor = .clear
        textView.textContainerInset = NSSize(width: 10, height: 6)
        textView.autoresizingMask = [.width]

        scrollView.documentView = textView
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else {
            return
        }

        let newText = lines.map(\.text).joined(separator: "\n")

        // Only update if text has changed
        if textView.string != newText {
            let wasAtBottom = isScrolledToBottom(scrollView)

            textView.string = newText

            // Auto-scroll to bottom if we were already at the bottom
            if wasAtBottom {
                textView.scrollToEndOfDocument(nil)
            }
        }
    }

    private func isScrolledToBottom(_ scrollView: NSScrollView) -> Bool {
        guard let textView = scrollView.documentView as? NSTextView else {
            return false
        }
        let visibleRect = scrollView.contentView.documentVisibleRect
        let contentHeight = textView.bounds.height
        return visibleRect.maxY >= contentHeight - 10  // 10pt threshold
    }
}
