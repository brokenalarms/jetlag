import SwiftUI

@dynamicMemberLookup
struct Dirtyable<T> {
    private(set) var original: T
    private var updated: T?
    private(set) var touched = false

    var current: T { updated ?? original }

    init(_ initialValue: T) {
        original = initialValue
    }

    var isDirty: Bool { updated != nil }

    mutating func markTouched() {
        touched = true
    }

    var value: T {
        get { updated ?? original }
        set {
            if updated == nil { updated = original }
            updated = newValue
        }
    }

    subscript<V>(dynamicMember keyPath: WritableKeyPath<T, V>) -> V {
        get { (updated ?? original)[keyPath: keyPath] }
        set {
            if updated == nil { updated = original }
            updated![keyPath: keyPath] = newValue
        }
    }

    mutating func commit() {
        if let updated {
            original = updated
            self.updated = nil
        }
    }

    mutating func rollback() {
        updated = nil
    }
}

extension Dirtyable where T: Equatable {
    var isDirty: Bool {
        guard let updated else { return false }
        return updated != original
    }
}

extension View {
    @ViewBuilder
    func fieldError(_ error: String?, show: Bool) -> some View {
        self
        if let error, show {
            Label(error, systemImage: "exclamationmark.triangle.fill")
                .font(.caption)
                .foregroundStyle(.red)
        }
    }
}
