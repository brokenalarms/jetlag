import SwiftUI
import Quartz

/// Feeds the shared Quick Look panel the file(s) a context-menu or Space-key
/// action picked. No custom previewer: a format with no Quick Look generator
/// simply shows the panel's generic icon.
final class QuickLookCoordinator: NSObject, QLPreviewPanelDataSource {
    private var items: [URL] = []

    func show(_ urls: [URL]) {
        guard !urls.isEmpty, let panel = QLPreviewPanel.shared() else { return }
        items = urls
        panel.dataSource = self
        panel.reloadData()
        panel.makeKeyAndOrderFront(nil)
    }

    func numberOfPreviewItems(in panel: QLPreviewPanel!) -> Int {
        items.count
    }

    func previewPanel(_ panel: QLPreviewPanel!, previewItemAt index: Int) -> QLPreviewItem! {
        items[index] as NSURL
    }
}
