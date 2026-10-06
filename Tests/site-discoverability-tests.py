#!/usr/bin/env python3
"""Offline discovery boundaries, full public inventory and static content contracts."""
import importlib.util
import hashlib
import json
import re
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'site/metadata.json').read_text())
BASE = CONFIG['baseUrl']


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.meta, self.links, self.canonical = {}, [], []
        self.title, self.text = [], []
        self.in_title = self.in_main = False
        self.skip = 0
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.meta[attrs.get('name', attrs.get('property'))] = attrs.get('content')
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical.append(attrs.get('href'))
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag == 'title': self.in_title = True
        if tag == 'main': self.in_main = True
        if tag in ('script', 'style'): self.skip += 1

    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
        if tag == 'main': self.in_main = False
        if tag in ('script', 'style'): self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if self.in_title: self.title.append(data)
        if self.in_main and not self.skip: self.text.append(data)


class DiscoverabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {p['path']: Page((ROOT / p['file']).read_text()) for p in CONFIG['pages']}

    def test_robots_public_and_private_for_every_crawler(self):
        robots_source = (ROOT / 'site/robots.txt').read_text()
        self.assertEqual(re.findall(r'(?mi)^Content-Signal:\s*(.+)$', robots_source),
                         ['ai-train=yes, search=yes, ai-input=no'])
        self.assertIn(f'Agentmap: {BASE}/.well-known/ard.json', robots_source)
        robots = RobotFileParser()
        robots.parse(robots_source.splitlines())
        self.assertEqual(robots.site_maps(), [BASE + '/sitemap.xml'])
        for agent in ('OAI-SearchBot', 'ChatGPT-User', 'Claude-SearchBot', 'Claude-User',
                      'Googlebot', 'Google-Extended', 'bingbot', 'GPTBot', 'ClaudeBot', 'other'):
            for path in [*self.pages, '/llms.txt', '/styles.css', '/compatibility.js']:
                self.assertTrue(robots.can_fetch(agent, BASE + path), (agent, path))
            for path in ('/admin', '/admin/login', '/admin?next=/', '/internal/operations',
                         '/api/private', '/diagnostics/', '/preview/', '/lab/', '/test/'):
                self.assertFalse(robots.can_fetch(agent, BASE + path), (agent, path))

    def test_sitemap_exact_inventory_limits_and_metadata(self):
        source = (ROOT / 'site/sitemap.xml').read_bytes()
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        tree = ET.fromstring(source)
        urls = [node.text for node in tree.findall('s:url/s:loc', ns)]
        expected = [BASE + p['path'] for p in CONFIG['pages'] if p.get('indexable', True)]
        self.assertCountEqual(urls, expected)
        self.assertEqual(len(urls), len(set(urls)))
        self.assertLessEqual(len(urls), 50000)
        self.assertLessEqual(len(source), 50 * 1024 * 1024)
        for url in urls:
            parsed = urlsplit(url)
            self.assertEqual((parsed.scheme, parsed.netloc, parsed.query, parsed.fragment),
                             ('https', 'terento.app', '', ''))
            page = self.pages[parsed.path]
            self.assertEqual(page.canonical, [url])
            self.assertEqual(page.meta['robots'], 'index,follow')
        titles, descriptions = [], []
        for path, page in self.pages.items():
            title = ''.join(page.title)
            description = page.meta['description']
            self.assertTrue(title and description, path)
            self.assertEqual(page.canonical, [BASE + path])
            self.assertEqual(page.meta['og:url'], BASE + path)
            self.assertEqual(page.meta['og:title'], title)
            self.assertEqual(page.meta['og:description'], description)
            self.assertGreater(len(' '.join(page.text).strip()), 300, path)
            titles.append(title); descriptions.append(description)
        self.assertEqual(len(titles), len(set(titles)))
        self.assertEqual(len(descriptions), len(set(descriptions)))

    def test_no_unregistered_html_and_all_pages_reachable_by_links(self):
        registered = {ROOT / page['file'] for page in CONFIG['pages']}
        exceptions = {ROOT / 'site/404.html', ROOT / 'site/supported-watches/index.html'}
        self.assertEqual(set((ROOT / 'site').rglob('*.html')), registered | exceptions)
        reached, pending = set(), ['/']
        while pending:
            path = pending.pop()
            if path in reached: continue
            reached.add(path)
            for href in self.pages[path].links:
                url = urlsplit(urljoin(BASE + path, href))
                if url.netloc == 'terento.app' and url.path in self.pages and url.path not in reached:
                    pending.append(url.path)
        self.assertEqual(reached, set(self.pages))
        for path in exceptions:
            self.assertIn('noindex', Page(path.read_text()).meta['robots'])

    def test_compatibility_cards_are_generated_from_snapshot(self):
        spec = importlib.util.spec_from_file_location('compatibility', ROOT / 'scripts/build-compatibility-pages.py')
        generator = importlib.util.module_from_spec(spec); spec.loader.exec_module(generator)
        snapshot = generator.load_snapshot()
        for locale in CONFIG['locales']:
            path = ROOT / 'site' / ('' if locale == 'en' else locale) / 'compatibility/index.html'
            source = path.read_text()
            self.assertEqual(source.count('class="watch-card"'), len(snapshot['models']))
            for model in snapshot['models']:
                self.assertIn(generator.card_markup(model, locale), source)

    def test_supplemental_index_has_only_canonical_public_links(self):
        source = (ROOT / 'site/llms.txt').read_text()
        links = re.findall(r'\]\((https://[^)]+)\)', source)
        allowed = {BASE + p['path'] for p in CONFIG['pages'] if p.get('indexable', True)}
        allowed.add('https://github.com/VooZ2/terento')
        self.assertTrue(set(links) <= allowed)
        for path in ('/', '/about/', '/compatibility/', '/download/', '/guides/install-garmin-maps-mac/', '/guides/troubleshooting/'):
            self.assertIn(BASE + path, links)

    def test_markdown_negotiation_representations_match_public_html(self):
        spec = importlib.util.spec_from_file_location('markdown_pages', ROOT / 'scripts/build-markdown-pages.py')
        generator = importlib.util.module_from_spec(spec); spec.loader.exec_module(generator)
        expected_files = set()
        for page in CONFIG['pages']:
            markdown_path = (ROOT / page['file']).with_name('index.md')
            expected_files.add(markdown_path)
            rendered = generator.render_page(page)
            self.assertEqual(markdown_path.read_text(), rendered, page['path'])
            self.assertTrue(rendered.startswith('---\ntitle: '), page['path'])
            self.assertIn(f"canonical: {BASE}{page['path']}", rendered)
            self.assertNotRegex(rendered, r'<(?:html|head|body|script|style)\b')
            self.assertGreater(len(rendered), 300, page['path'])
        self.assertEqual(set((ROOT / 'site').rglob('index.md')), expected_files)

        caddy = (ROOT / 'site-deploy/Caddyfile').read_text()
        self.assertIn('header Accept *text/markdown*', caddy)
        self.assertIn('method GET HEAD', caddy)
        self.assertIn('path_regexp markdownPage ^/([a-zA-Z0-9_-]+/)*$', caddy)
        self.assertIn('header @negotiatedPage Vary Accept', caddy)
        self.assertIn('rewrite * {path}index.md', caddy)
        self.assertIn('header Vary "Accept"', caddy)
        self.assertIn('header Content-Type "text/markdown; charset=utf-8"', caddy)

    def test_api_catalog_links_and_openapi_routes(self):
        catalog = json.loads((ROOT / 'site/.well-known/api-catalog').read_text())
        self.assertEqual(len(catalog['linkset']), 1)
        entry = catalog['linkset'][0]
        self.assertEqual(entry['anchor'], 'https://api.terento.app')
        for relation in ('service-desc', 'service-doc', 'status'):
            self.assertTrue(entry[relation])
            for link in entry[relation]:
                parsed = urlsplit(link['href'])
                self.assertEqual(parsed.scheme, 'https')
                self.assertTrue(parsed.netloc)
                self.assertFalse(parsed.query or parsed.fragment)
        self.assertEqual(entry['service-desc'][0]['href'], BASE + '/openapi.json')
        self.assertEqual(entry['status'][0]['href'], entry['anchor'] + '/health')
        spec = json.loads((ROOT / 'site/openapi.json').read_text())
        self.assertEqual(spec['openapi'], '3.1.0')
        self.assertEqual(spec['servers'], [{'url': entry['anchor']}])
        self.assertEqual(spec['externalDocs']['url'], entry['service-doc'][0]['href'])
        self.assertEqual(set(spec['paths']), {
            '/health', '/maps/catalog.json', '/maps/catalog-v3.json',
            '/maps/catalog-v4.json', '/devices/catalog.json',
            '/devices/installation-policy.json', '/compatibility/public/models.json',
            '/compatibility/public/top-models.json',
        })
        implementation = (ROOT / 'backend/catalog-api/src/terento_catalog/http_api.py').read_text()
        operation_ids = []
        for path, operations in spec['paths'].items():
            self.assertIn('"' + path + '"', implementation)
            self.assertEqual(set(operations), {'get'})
            self.assertIn('200', operations['get']['responses'])
            operation_ids.append(operations['get']['operationId'])
        self.assertEqual(len(operation_ids), len(set(operation_ids)))
        robots = RobotFileParser()
        robots.parse((ROOT / 'site/robots.txt').read_text().splitlines())
        for path in ('/.well-known/api-catalog', '/openapi.json',
                     '/.well-known/ai-catalog.json', '/.well-known/ard.json',
                     '/.well-known/agent-skills/index.json',
                     '/.well-known/agent-skills/terento-map-catalog/SKILL.md'):
            self.assertTrue(robots.can_fetch('*', BASE + path))
        caddy = (ROOT / 'site-deploy/Caddyfile').read_text()
        self.assertIn('@apiCatalog path /.well-known/api-catalog', caddy)
        self.assertIn('Content-Type "application/linkset+json"', caddy)
        self.assertIn('header Link "<https://terento.app/.well-known/api-catalog>; rel=api-catalog"', caddy)
        self.assertIn('header @openAPI Content-Type "application/vnd.oai.openapi+json"', caddy)

    def test_ard_manifest_and_legacy_catalog_alias(self):
        canonical_path = ROOT / 'site/.well-known/ard.json'
        scanner_path = ROOT / 'site/.well-known/ai-catalog.json'
        self.assertEqual(canonical_path.read_bytes(), scanner_path.read_bytes())
        manifest = json.loads(canonical_path.read_text())
        self.assertEqual(manifest['specVersion'], '1.0')
        self.assertEqual(manifest['host'], {
            'displayName': 'Terento',
            'identifier': BASE,
        })
        self.assertEqual(len(manifest['entries']), 2)

        expected = {
            'urn:air:terento.app:api:public-catalog': ('Terento Public Catalog API', 'application/json'),
            'urn:air:terento.app:skill:map-catalog': ('Terento Map Catalog Skill', 'text/markdown'),
        }
        identifiers = set()
        for entry in manifest['entries']:
            identifier = entry['identifier']
            self.assertRegex(identifier, r'^urn:air:terento\.app:[a-z0-9-]+:[a-z0-9-]+$')
            self.assertNotIn(identifier, identifiers)
            identifiers.add(identifier)
            self.assertEqual(entry['@context'], 'https://agenticresourcediscovery.org/context/v1')
            self.assertEqual(entry['@id'], identifier)
            self.assertEqual((entry['displayName'], entry['type']), expected[identifier])
            self.assertEqual(('url' in entry) + ('data' in entry), 1)
            self.assertIn(entry['type'], {'application/json', 'text/markdown'})
            queries = entry['representativeQueries']
            self.assertGreaterEqual(len(queries), 2)
            self.assertLessEqual(len(queries), 5)
            self.assertTrue(all(isinstance(query, str) and query.strip() for query in queries))

            parsed = urlsplit(entry['url'])
            self.assertEqual((parsed.scheme, parsed.netloc, parsed.query, parsed.fragment),
                             ('https', 'terento.app', '', ''))
            if identifier.endswith(':public-catalog'):
                self.assertEqual(parsed.path, '/openapi.json')
                self.assertEqual(json.loads((ROOT / 'site/openapi.json').read_text())['openapi'], '3.1.0')
            else:
                self.assertEqual(parsed.path, '/.well-known/agent-skills/terento-map-catalog/SKILL.md')
                self.assertTrue((ROOT / 'site' / parsed.path.lstrip('/')).is_file())

        self.assertEqual(identifiers, set(expected))
        caddy = (ROOT / 'site-deploy/Caddyfile').read_text()
        self.assertIn('@ardManifest path /.well-known/ai-catalog.json /.well-known/ard.json', caddy)
        self.assertIn('Content-Type "application/json"', caddy)
        self.assertIn('Access-Control-Allow-Origin "*"', caddy)

    def test_agent_skills_index_and_artifact_digest(self):
        index_path = ROOT / 'site/.well-known/agent-skills/index.json'
        index = json.loads(index_path.read_text())
        self.assertEqual(index['$schema'], 'https://schemas.agentskills.io/discovery/0.2.0/schema.json')
        self.assertEqual(len(index['skills']), 1)

        names = set()
        for skill in index['skills']:
            self.assertTrue(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', skill['name']))
            self.assertLessEqual(len(skill['name']), 64)
            self.assertNotIn(skill['name'], names)
            names.add(skill['name'])
            self.assertEqual(skill['type'], 'skill-md')
            self.assertTrue(skill['description'].strip())
            parsed = urlsplit(skill['url'])
            self.assertEqual((parsed.scheme, parsed.netloc, parsed.query, parsed.fragment),
                             ('https', 'terento.app', '', ''))
            self.assertRegex(parsed.path, r'^/\.well-known/agent-skills/[a-z0-9-]+/SKILL\.md$')
            artifact = ROOT / 'site' / parsed.path.lstrip('/')
            content = artifact.read_bytes()
            self.assertRegex(skill['digest'], r'^sha256:[0-9a-f]{64}$')
            self.assertEqual(skill['digest'], 'sha256:' + hashlib.sha256(content).hexdigest())

            frontmatter = content.decode('utf-8').split('---', 2)
            self.assertEqual(frontmatter[0], '')
            self.assertEqual(frontmatter[1].splitlines()[0], '')
            self.assertIn(f'name: {skill["name"]}', frontmatter[1])
            self.assertIn(f'description: {skill["description"]}', frontmatter[1])

        caddy = (ROOT / 'site-deploy/Caddyfile').read_text()
        self.assertIn('@agentSkill path /.well-known/agent-skills/*/SKILL.md', caddy)
        self.assertIn('Content-Type "text/markdown; charset=utf-8"', caddy)

    def test_public_json_is_available_but_not_indexable(self):
        site = (ROOT / 'site-deploy/Caddyfile').read_text()
        self.assertIn('@machineMetadata path *.json', site)
        self.assertIn('header @machineMetadata X-Robots-Tag "noindex, nofollow"', site)


if __name__ == '__main__':
    unittest.main()
