#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
about_source="$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/AboutTerentoView.swift"
about_content="$(cat "$about_source")"
app_source="$repo_root/app/TerentoCore/Sources/TerentoPoC/TerentoPoCApp.swift"
connect_source="$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/ConnectScreen.swift"

if ! grep -Fq 'HStack(spacing: 16)' <<<"$about_content" \
    || ! grep -Fq 'Image(nsImage: NSApplication.shared.applicationIconImage)' <<<"$about_content" \
    || ! grep -Fq 'Text("Terento")' <<<"$about_content" \
    || ! grep -Fq 'Text("Install maps on Garmin watches, simply.")' <<<"$about_content" \
    || ! grep -Fq 'Text(TerentoAppMetadata.displayVersion)' <<<"$about_content"; then
    print -u2 "FAIL: About does not use the compact dynamic logo/header block"
    exit 1
fi

if ! grep -Fq 'Text(TerentoAppMetadata.displayVersion)' \
    "$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/AboutTerentoView.swift"; then
    print -u2 "FAIL: Terento → About Terento does not use the shared display version"
    exit 1
fi

standalone_about_source="$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/AboutTerentoView.swift"
for presentation in \
    'TerentoColors.canvas' \
    '.background(TerentoColors.canvas)' \
    '.preferredColorScheme(.light)' \
    '.frame(minWidth: 520, idealWidth: 560, minHeight: 440, idealHeight: 580)' \
    '.frame(maxWidth: 680, alignment: .leading)' \
    'ScrollView {' \
    '.fixedSize(horizontal: false, vertical: true)'; do
    if ! grep -Fq "$presentation" "$standalone_about_source"; then
        print -u2 "FAIL: standalone About is missing the required presentation treatment: $presentation"
        exit 1
    fi
done

if grep -Fq '.lineLimit(1)' "$standalone_about_source"; then
    print -u2 "FAIL: standalone About description is constrained to one line"
    exit 1
fi

for treatment in \
    '.font(.terentoHeading(size: 30, weight: .semibold))' \
    '.foregroundStyle(TerentoColors.graphite)' \
    '.font(.terentoUI(size: 13, weight: .regular))' \
    '.foregroundStyle(TerentoColors.secondaryText)' \
    '.font(.terentoUI(size: 13, weight: .medium))' \
    '.foregroundStyle(TerentoColors.interactive)'; do
    if ! grep -Fq "$treatment" "$standalone_about_source"; then
        print -u2 "FAIL: standalone About is missing the established brand treatment: $treatment"
        exit 1
    fi
done

for link in \
    'supportLink("Website ↗", destination: TerentoAppLinks.websiteFromApp)' \
    'supportLink("GitHub repository ↗", destination: TerentoAppLinks.repository)' \
    'supportLink("Report an issue ↗", destination: TerentoAppLinks.issues)' \
    'supportLink("Donate ↗", destination: TerentoAppLinks.donate)'; do
    if ! grep -Fq "$link" "$standalone_about_source"; then
        print -u2 "FAIL: standalone About link or destination is missing: $link"
        exit 1
    fi
done

if grep -Fq 'aboutSection(title: "Updates")' <<<"$about_content" \
    || ! grep -Fq 'AboutPrimaryButton(title: "Update", action: updateAction)' <<<"$about_content" \
    || ! grep -Fq 'AboutSecondaryButton(title: "Manage diagnostics")' <<<"$about_content" \
    || ! grep -Fq 'private func updateAction()' <<<"$about_content"; then
    print -u2 "FAIL: About does not expose the adjacent Update and diagnostics actions"
    exit 1
fi

if grep -Fq 'TerentoPageHeader(' <<<"$about_content" \
    || grep -Fq 'private var aboutContent' "$connect_source"; then
    print -u2 "FAIL: About still contains the duplicated product identity block"
    exit 1
fi

if grep -Fq 'TerentoAppMetadata.description' <<<"$about_content" \
    || grep -Fq 'TerentoAppMetadata.description' "$standalone_about_source"; then
    print -u2 "FAIL: About still exposes the long product description"
    exit 1
fi

for label in 'GitHub repository ↗' 'Report an issue ↗' 'Website ↗' 'Donate ↗'; do
    if ! grep -Fq "$label" <<<"$about_content"; then
        print -u2 "FAIL: Support link is missing: $label"
        exit 1
    fi
done

if ! grep -Fq 'ViewThatFits(in: .horizontal)' <<<"$about_content" \
    || ! grep -Fq 'HStack(spacing: 16) { supportLinks }' <<<"$about_content" \
    || ! grep -Fq 'VStack(alignment: .leading, spacing: 10) { supportLinks }' <<<"$about_content"; then
    print -u2 "FAIL: Support links do not have one-line and narrow-width layouts"
    exit 1
fi

for privacy_link in \
    'supportLink("Privacy ↗", destination: TerentoAppLinks.privacyFromApp)' \
    'supportLink("Legal ↗", destination: TerentoAppLinks.legalFromApp)'; do
    if ! grep -Fq "$privacy_link" <<<"$about_content"; then
        print -u2 "FAIL: Privacy/Legal link is missing: $privacy_link"
        exit 1
    fi
done

for update_contract in \
    '@ObservedObject var appUpdateController: AppUpdateController' \
    '.disabled(appUpdateController.isChecking)' \
    'switch appUpdateController.state' \
    'case .idle:' \
    'case .checking:' \
    'case .upToDate:' \
    'case let .available(update):' \
    'case let .incompatible(update):' \
    'case let .failed(message):' \
    'if case let .available(update) = appUpdateController.state' \
    'appUpdateController.openDownload(for: update)' \
    'appUpdateController.checkForUpdates()'; do
    if ! grep -Fq "$update_contract" "$about_source"; then
        print -u2 "FAIL: About shared update controller contract is missing: $update_contract"
        exit 1
    fi
done

for privacy_copy in \
    'Terento sends privacy-minimised diagnostics by default' \
    'Device state, maps, manifests, Unit IDs, serial numbers, and local paths stay on this Mac.' \
    'Terento may contact terento.app when the app starts to check whether a newer version is available.' \
    'This request is not used for analytics or user tracking.'; do
    if ! grep -Fq "$privacy_copy" "$about_source"; then
        print -u2 "FAIL: consolidated About lost its privacy disclosure: $privacy_copy"
        exit 1
    fi
done

for menu_contract in \
    'Button("About Terento")' \
    'openWindow(id: "about")' \
    'Window("About Terento", id: "about")' \
    'AboutTerentoView(appUpdateController: appUpdateController)'; do
    if ! grep -Fq "$menu_contract" "$app_source"; then
        print -u2 "FAIL: canonical About menu/window wiring is missing: $menu_contract"
        exit 1
    fi
done

for referral in \
    'utm_source=terento_app' \
    'utm_medium=referral' \
    'utm_campaign=app_about'; do
    if ! grep -Fq "$referral" "$repo_root/app/TerentoCore/Sources/TerentoPoC/Views/AppLinks.swift"; then
        print -u2 "FAIL: app referral parameter is missing: $referral"
        exit 1
    fi
done

if grep -Fq 'deleteUploadedReportsLink' <<<"$about_content" \
    || grep -Fq 'Delete uploaded reports' "$about_source"; then
    print -u2 "FAIL: About still exposes uploaded-report deletion"
    exit 1
fi

if ! grep -Fq 'AboutSecondaryButton(title: "Manage diagnostics")' <<<"$about_content" \
    || ! grep -Fq 'openWindow(id: "diagnostics")' <<<"$about_content"; then
    print -u2 "FAIL: About does not expose the Diagnostics settings entry point"
    exit 1
fi

if grep -Fq '.buttonStyle(.link)' <<<"$about_content"; then
    print -u2 "FAIL: Privacy action still uses the default system-link button style"
    exit 1
fi

print "PASS: compact About header, responsive Support row, and consistent Privacy links"
