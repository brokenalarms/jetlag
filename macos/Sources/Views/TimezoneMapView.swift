import SwiftUI

struct TimezonePickerView: View {
    @Binding var selectedTimezone: String
    @State private var showingPicker = false

    var body: some View {
        Button {
            showingPicker = true
        } label: {
            HStack(spacing: Theme.Space.md) {
                Image(systemName: "globe")
                if selectedTimezone.isEmpty {
                    Text(Strings.Workflow.selectTimezone)
                        .foregroundStyle(Theme.Text.secondary)

                } else if let option = TimezoneCatalog.option(selectedTimezone) {
                    Text(option.city)
                    Text(option.offsetLabel)
                        .font(Theme.Typography.bodyMono)
                        .foregroundStyle(Theme.Text.secondary)
                } else {
                    Text(selectedTimezone)
                        .font(Theme.Typography.bodyMono)
                }
                Image(systemName: "chevron.up.chevron.down")
                    .font(Theme.Typography.detail)
                    .foregroundStyle(Theme.Text.secondary)
            }
            .padding(.horizontal, Theme.Space.lg)
            .padding(.vertical, Theme.Space.sm)
            .frame(minWidth: Theme.Size.timezoneListMin)
            .background(Theme.Surface.background)
            .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.field))
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.field)
                    .strokeBorder(Theme.Surface.separator, lineWidth: Theme.Stroke.hairline)
            )
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $showingPicker) {
            TimezonePickerSheet(
                selectedTimezone: $selectedTimezone,
                isPresented: $showingPicker
            )
        }
    }
}

private struct TimezonePickerSheet: View {
    @Binding var selectedTimezone: String
    @Binding var isPresented: Bool
    @State private var searchText = ""

    private var filtered: [(option: TimezoneOption, match: TimezoneMatch)] {
        TimezoneCatalog.all.compactMap { option in
            let match = searchText.isEmpty ? TimezoneMatch(place: nil) : option.match(searchText)
            return match.map { (option, $0) }
        }
    }

    private var grouped: [(region: String, items: [(option: TimezoneOption, match: TimezoneMatch)])] {
        Dictionary(grouping: filtered, by: \.option.region)
            .sorted { $0.key < $1.key }
            .map { (region: $0.key, items: $0.value) }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(Theme.Text.secondary)
                TextField(Strings.Workflow.searchTimezones, text: $searchText)
                    .textFieldStyle(.plain)
                Spacer()
                Button(Strings.Common.done) {
                    isPresented = false
                }
            }
            .padding(Theme.Space.lg)

            Divider()

            List {
                ForEach(grouped, id: \.region) { group in
                    Section(group.region) {
                        ForEach(group.items, id: \.option.id) { result in
                            let item = result.option
                            Button {
                                selectedTimezone = item.id
                                isPresented = false
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 0) {
                                        Text(item.path)
                                            .lineLimit(1)
                                            .fontWeight(item.id == selectedTimezone ? .semibold : .regular)
                                        if let place = result.match.place {
                                            Text(place)
                                                .font(Theme.Typography.caption)
                                                .foregroundStyle(Theme.Text.secondary)
                                                .lineLimit(1)
                                        }
                                    }
                                    Spacer()
                                    Text(item.offsetLabel)
                                        .font(Theme.Typography.captionMono)
                                        .foregroundStyle(Theme.Text.secondary)
                                }
                                .contentShape(Rectangle())

                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .listStyle(.plain)
        }
        .frame(width: Theme.Size.timezonePopoverWidth, height: Theme.Size.timezonePopoverHeight)
    }
}
