#!/bin/zsh
set -euo pipefail

# One dialog standard: every sheet or alert in the app's views is built on the
# shared TerentoConfirmationDialog (SupportReportSheet is the wide variant
# built from the shared header and buttons). The quit NSAlert stays native.
# Only errors and confirmations may be popups (allowlist below).
project_root="$(cd "$(dirname "$0")/.." && pwd)"

python3 - "$project_root/Sources/TerentoPoC/Views" <<'PY'
import pathlib, re, sys
views = pathlib.Path(sys.argv[1])
sources = {p.name: p.read_text() for p in views.glob('*.swift')}
everything = '\n'.join(sources.values())

def struct_body(name):
    m = re.search(r'struct ' + name + r': View \{', everything)
    assert m, f'{name} not found'
    end = everything.index('\n}\n', m.start())
    return everything[m.start():end]

for name, text in sources.items():
    assert '.alert(' not in text and 'Alert(' not in text, f'{name} uses a system alert instead of the shared dialog'
    assert 'confirmationDialog(' not in text, f'{name} uses a system confirmation dialog'
    assert 'sheetButton(' not in text and 'dialogButton(' not in text, f'{name} has a hand-made dialog button'

presented = []
for name, text in sources.items():
    for m in re.finditer(r'\.sheet\(', text):
        tail = text[m.end():]
        body = tail[tail.index('{') + 1:]
        view = re.search(r'\b([A-Z][A-Za-z]+)\(', body).group(1)
        presented.append(view)
assert presented, 'no sheets found'
for view in presented:
    if view == 'TerentoConfirmationDialog':
        continue
    body = struct_body(view)
    if view == 'SupportReportSheet':
        assert 'TerentoDialogHeader(' in body and 'TerentoDialogButton(' in body, 'Send report does not use the shared header and buttons'
        assert 'TerentoDialogMetrics.wideWidth' in body, 'Send report is not the wide dialog variant'
        continue
    assert 'TerentoConfirmationDialog(' in body, f'{view} is a sheet that does not use the shared dialog'

dialog = struct_body('TerentoConfirmationDialog')
assert 'TerentoDialogHeader(' in dialog and 'TerentoDialogMetrics.width' in dialog
assert dialog.count('.keyboardShortcut(.defaultAction)') == 1, 'more than one Return action in the dialog'
destructive = dialog[dialog.index('if isDestructive {'):dialog.index('} else {', dialog.index('if isDestructive {'))]
assert '.keyboardShortcut' not in destructive, 'a destructive dialog binds Return'

metrics = everything[everything.index('enum TerentoDialogMetrics'):]
metrics = metrics[:metrics.index('\n}\n')]
for needle in ['iconSize: CGFloat = 20', 'iconCircle: CGFloat = 36', 'iconTintOpacity: Double = 0.12',
               'titleSize: CGFloat = 20', 'bodySize: CGFloat = 14', 'supportingSize: CGFloat = 13',
               'padding: CGFloat = 24', 'width: CGFloat = 440', 'wideWidth: CGFloat = 560',
               'buttonHeight: CGFloat = 40', 'buttonGap: CGFloat = 8',
               'sheetRadius: CGFloat = TerentoGeneratedTokens.Radius.large',
               'buttonRadius: CGFloat = TerentoGeneratedTokens.Radius.control']:
    assert needle in metrics, f'dialog metric missing: {needle}'

role = everything[everything.index('enum TerentoDialogRole'):]
role = role[:role.index('\n}\n')]
for needle in ['case .error: return TerentoColors.error', 'case .warning: return TerentoColors.warning',
               'case .success: return TerentoColors.lichenDark', 'case .info: return TerentoColors.interactive']:
    assert needle in role, f'dialog role colour missing: {needle}'

screen = sources['ConnectScreen.swift']
assert 'MapLifecycleConfirmationCopy.removeTitle(' in screen and 'MapLifecycleConfirmationCopy.removeMessage(' in screen

def check(ok, message):
    if not ok:
        print(f'FAIL: {message}')
        sys.exit(1)

def branch(body, label):
    check('if isDestructive {' in body, f'{label} has no destructive branch')
    start = body.index('if isDestructive {')
    return body[start:body.index('} else {', start)]

# Remove map: presentation -> destructive sheet branch -> destructive confirm button.
call_start = screen.find('MapLifecycleConfirmationSheet(')
check(call_start >= 0, 'the map Remove confirmation sheet is not presented')
call = screen[call_start:screen.index('onConfirm:', call_start)]
check('"Remove map"' in call and 'isDestructive: confirmation.action == .remove' in call,
      'the map Remove confirmation is not presented as destructive')
check('isDestructive: true' in branch(struct_body('MapLifecycleConfirmationSheet'), 'MapLifecycleConfirmationSheet'),
      'the map Remove sheet does not open the shared dialog as destructive')
check('TerentoDialogButton(primaryLabel, kind: .destructive' in destructive,
      'the destructive dialog confirm button is not the destructive kind')
# Popup rule (app/TerentoCore/AGENTS.md): a sheet or alert is only for an
# error or a confirmation. Results, waiting, offers and sharing questions stay
# on the page. Any new popup must be added here on purpose.
POPUP_ALLOWLIST = {
    'InstallationFailureDialog',          # error
    'SupportReportSheet',                 # error follow-up from the failure dialog
    'MapLifecycleConfirmationSheet',      # confirmation: Remove / Update
    'CustomMapImportConfirmationSheet',   # confirmation: import an unrecognized file
    'File could not be confirmed as a map',  # error (shared dialog, by title)
}
popups = []
for view in presented:
    popups.append(view)
for m in re.finditer(r'\.sheet\(', everything):
    tail = everything[m.end():]
    body = tail[tail.index('{') + 1:]
    if re.search(r'\b([A-Z][A-Za-z]+)\(', body).group(1) == 'TerentoConfirmationDialog':
        title = re.search(r'title: "([^"]+)"', body[:600])
        popups.remove('TerentoConfirmationDialog')
        popups.append(title.group(1) if title else 'TerentoConfirmationDialog (no literal title)')
for popup in popups:
    check(popup in POPUP_ALLOWLIST, f'{popup} is a popup but is not an error or confirmation on the allowlist')
for name in ('WatchReconnectWaitDialog', 'AppUpdatePromptView', 'InstallSharingDialog'):
    check(name not in popups, f'{name} must be shown on the page, not as a popup')

# Outside the views: only the quit-while-writing NSAlert, nothing else modal.
app_sources = pathlib.Path(sys.argv[1]).parent
for path in app_sources.rglob('*.swift'):
    if path.parent == views:
        continue
    text = path.read_text()
    for needle in ('.sheet(', '.alert(', 'confirmationDialog(', 'beginSheet', '.popover('):
        check(needle not in text, f'{path.name} presents a popup ({needle}) outside the allowlist')
    alerts = text.count('NSAlert()')
    if path.name == 'TerentoPoCApp.swift':
        check(alerts == 1 and 'writesToDevice(' in text, 'the only NSAlert must be the quit-while-writing alert')
    else:
        check(alerts == 0, f'{path.name} shows an NSAlert outside the allowlist')

print(f'PASS: {len(presented)} sheets use the shared dialog standard; map Remove uses the destructive dialog; '
      f'{len(popups)} popups, all errors or confirmations on the allowlist')
PY
