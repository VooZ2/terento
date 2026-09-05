# Website legal notices

The current notice sources are `LEGAL-PAGE-{EN,DE,FR,PL,CS,IT}.md` and
`PRIVACY-PAGE-{EN,DE,FR,PL,CS,IT}.md`. Lithuanian notices are retired because
the website has no Lithuanian locale.

After editing a source, run:

```sh
python3 scripts/build-legal-pages.py
python3 scripts/normalize-public-shell.py
python3 scripts/build-legal-pages.py --check
Tests/run-release-legal-content-tests.sh
Tests/run-site-tests.sh
```

The renderer preserves the shared page shell and produces localized section
navigation. The site generator parity suite covers both legal pages.

Website Umami remains always on, without a consent banner. Campaign UTM
values travel through URLs without campaign browser storage. The app's
separate diagnostic settings are unchanged. These notices describe product
behavior; publication alone does not establish legal compliance.
