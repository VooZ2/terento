## Summary

<!-- What changed and why? -->

## Validation

- [ ] I ran the relevant automated validation.
- [ ] I documented the commands and results below.
- [ ] I did not claim hardware validation that was not performed.

If a previous check failed, identify the failing assertion/step, evidenced cause,
whether runtime or the test changed, and why the required behavior is still
covered. A successful retry alone does not establish a fix.

Commands and results:

    <!-- Add commands and concise results here. -->

## Documentation impact

- [ ] Canonical documentation was updated for every durable behavior change, or this change has no durable documentation impact.
- [ ] Superseded guidance was removed or rewritten; no conflicting old rule remains.
- [ ] User/help/release copy was reviewed if user-visible behavior changed.

## Safety and compatibility

- [ ] No unrelated Garmin files are silently overwritten, removed, or renamed.
- [ ] Device identity, ownership, compatibility, storage, and transfer checks remain fail-closed.
- [ ] No secrets, private device data, map binaries, or proprietary assets are included.
- [ ] Map provider attribution and third-party notices are preserved.
- [ ] Garmin trademark and independence language remains accurate.

## Real-device testing

Describe the device model, test scope, and result, or write Not performed with the reason.

## Limitations and follow-up

<!-- What is intentionally not included or still pending? -->

## Brand and user-facing changes

<!-- Complete this section only when the PR changes user-facing UI, public copy,
styling, icons, screenshots, or visual assets. Otherwise select N/A. -->

- [ ] Canonical logo reused without geometry changes.
- [ ] Approved semantic tokens used instead of new raw brand colors.
- [ ] `Interactive Primary` remains the single primary action family.
- [ ] `Warm Stone` is not used as a primary CTA.
- [ ] Font roles remain correct.
- [ ] Status uses explicit text, an icon, and supporting color.
- [ ] Normal UI describes outcomes rather than implementation mechanics.
- [ ] Public claims match the current release.
- [ ] Accessibility and keyboard focus behavior were checked.
- [ ] Not applicable: this PR has no user-facing changes.
