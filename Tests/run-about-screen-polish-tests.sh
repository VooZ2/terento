#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
about_source="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/ConnectScreen.swift"
about_content="$(sed -n '/private var aboutContent/,/private var managedMapsContent/p' "$about_source")"

if ! grep -Fq 'HStack(alignment: .center, spacing: 16)' <<<"$about_content" \
    || ! grep -Fq 'ResourceImage(name: "logo", subdirectory: "Brand")' <<<"$about_content" \
    || ! grep -Fq 'Text("About Terento")' <<<"$about_content" \
    || ! grep -Fq 'Text("Your device, ready for where you' <<<"$about_content" \
    || ! grep -Fq 'Text(TerentoAppMetadata.displayVersion)' <<<"$about_content"; then
    print -u2 "FAIL: About does not use the compact dynamic logo/header block"
    exit 1
fi

if ! grep -Fq 'Text(TerentoAppMetadata.displayVersion)' \
    "$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/AboutTerentoView.swift"; then
    print -u2 "FAIL: Help → About does not use the shared display version"
    exit 1
fi

if grep -Fq 'Install update' <<<"$about_content" \
    || ! grep -Fq 'SecondaryButton(title: "Download")' <<<"$about_content" \
    || ! grep -Fq 'What’s new' <<<"$about_content"; then
    print -u2 "FAIL: About update actions do not use Download and What’s new wording"
    exit 1
fi

if grep -Fq 'TerentoPageHeader(' <<<"$about_content" \
    || grep -Fq 'Text("Terento")' <<<"$about_content"; then
    print -u2 "FAIL: About still contains the duplicated product identity block"
    exit 1
fi

if ! grep -Fq 'TerentoAppMetadata.description' <<<"$about_content"; then
    print -u2 "FAIL: About product description is missing"
    exit 1
fi

for label in 'GitHub repository ↗' 'Report an issue ↗' 'Website ↗'; do
    if ! grep -Fq "$label" <<<"$about_content"; then
        print -u2 "FAIL: Support link is missing: $label"
        exit 1
    fi
done

if ! grep -Fq 'ViewThatFits(in: .horizontal)' <<<"$about_content" \
    || ! grep -Fq 'HStack(alignment: .firstTextBaseline, spacing: 18)' <<<"$about_content" \
    || ! grep -Fq 'VStack(alignment: .leading, spacing: 8)' <<<"$about_content"; then
    print -u2 "FAIL: Support links do not have one-line and narrow-width layouts"
    exit 1
fi

if ! grep -Fq 'deleteUploadedReportsLink' <<<"$about_content" \
    || ! grep -Fq '.buttonStyle(.plain)' "$about_source" \
    || ! grep -Fq '.foregroundStyle(TerentoColors.interactive)' "$about_source"; then
    print -u2 "FAIL: Delete uploaded reports does not use the standard Terento link treatment"
    exit 1
fi

if grep -Fq '.buttonStyle(.link)' <<<"$about_content"; then
    print -u2 "FAIL: Privacy action still uses the default system-link button style"
    exit 1
fi

print "PASS: compact About header, responsive Support row, and consistent Privacy links"
