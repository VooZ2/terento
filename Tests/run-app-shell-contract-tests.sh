#!/bin/zsh
set -euo pipefail

repo_root="${0:A:h:h}"
icon_directory="$repo_root/app/Terento/Assets.xcassets/AppIcon.appiconset"
icon_contents="$icon_directory/Contents.json"
app_source="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/TerentoPoCApp.swift"
about_source="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/AboutTerentoView.swift"
links_source="$repo_root/lab/native-connectivity-poc/Sources/TerentoPoC/Views/AppLinks.swift"
project_file="$repo_root/Terento.xcodeproj/project.pbxproj"

[[ -f "$icon_contents" ]] || { print -u2 "Missing AppIcon Contents.json"; exit 1; }
[[ "$(rg -c '"filename"' "$icon_contents")" == "10" ]] || {
    print -u2 "AppIcon must declare ten macOS scale entries"
    exit 1
}

for size in 16 32 64 128 256 512 1024; do
    icon="$icon_directory/AppIcon-$size.png"
    [[ -f "$icon" ]] || { print -u2 "Missing $icon"; exit 1; }
    dimensions="$(sips -g pixelWidth -g pixelHeight "$icon" | awk '/pixelWidth|pixelHeight/ { print $2 }' | paste -sd 'x' -)"
    [[ "$dimensions" == "$size"x"$size" ]] || {
        print -u2 "Unexpected dimensions for $icon: $dimensions"
        exit 1
    }
done

rg -Fq 'brand/logo/logo.svg' "$repo_root/Packaging/generate-app-icon.swift"
rg -Fq '#7898A8' "$repo_root/Packaging/generate-app-icon.swift"
rg -Fq '#F7F3EC' "$repo_root/Packaging/generate-app-icon.swift"
rg -Fq 'ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon' "$project_file"
rg -Fq 'CFBundleIconName' "$repo_root/app/Terento/Info.plist"

rg -Fq 'CommandGroup(replacing: .appInfo)' "$app_source"
rg -Fq 'CommandGroup(replacing: .help)' "$app_source"
rg -Fq 'Window("About Terento", id: "about")' "$app_source"
rg -Fq 'Window("Diagnostics", id: "diagnostics")' "$app_source"
rg -Fq 'Image(nsImage: NSApplication.shared.applicationIconImage)' "$about_source"
app_info_commands="$(sed -n '/CommandGroup(replacing: .appInfo)/,/CommandGroup(replacing: .help)/p' "$app_source")"
if ! grep -Fq 'Button("About Terento")' <<<"$app_info_commands" \
    || ! grep -Fq 'openWindow(id: "about")' <<<"$app_info_commands" \
    || ! grep -Fq 'Button("Diagnostics")' <<<"$app_info_commands" \
    || ! grep -Fq 'openWindow(id: "diagnostics")' <<<"$app_info_commands" \
    || ! grep -Fq 'Button("Check updates")' <<<"$app_info_commands" \
    || ! grep -Fq 'appUpdateController.checkForUpdates()' <<<"$app_info_commands" \
    || [[ "$(rg -Fc 'Button("About Terento")' "$app_source")" != "1" ]]; then
    print -u2 "FAIL: standard macOS About is not the single custom About route"
    exit 1
fi

help_commands="$(sed -n '/CommandGroup(replacing: .help)/,/^            }/p' "$app_source")"
if grep -Fq 'Button("About Terento")' <<<"$help_commands"; then
    print -u2 "FAIL: Help still contains a duplicate About entry"
    exit 1
fi

for label in 'Terento Website' 'Documentation' 'Report an Issue' 'GitHub Repository'; do
    rg -Fq "Button(\"$label\")" "$app_source"
done
for url in 'https://terento.app' 'https://github.com/VooZ2/terento#readme' 'https://github.com/VooZ2/terento/issues' 'https://github.com/VooZ2/terento'; do
    rg -Fq "$url" "$links_source"
done

if rg -Fq "Help isn't available for Terento." "$repo_root/lab/native-connectivity-poc/Sources"; then
    print -u2 "The default unavailable Help message is still present"
    exit 1
fi

print "App shell checks passed: AppIcon assets, Help commands, About window, and links."
