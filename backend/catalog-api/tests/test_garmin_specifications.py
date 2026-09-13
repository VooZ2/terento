import json
import unittest

from terento_catalog.collectors.garmin.specifications import parse_specifications


class GarminSpecificationTests(unittest.TestCase):
    def page(self, skus):
        return 'var GarminAppBootstrap = ' + json.dumps({'skus': skus}) + ';'

    def sku(self, display, product='123', part='010-12345-00'):
        return {'productId': product, 'partNumber': part, 'tabs': {'specsTab': {'content':
            '<table><tr><th>Display type</th><td>' + display + '</td></tr></table>'}}}

    def test_display_from_specs_without_marketing_name(self):
        result = parse_specifications(self.page({'a': self.sku('AMOLED (up to 3000 NITS)')}), '123')
        self.assertEqual(result['screen_technology'], 'AMOLED')
        self.assertIsNone(result['solar'])
        self.assertIsNone(result['inreach'])

    def test_other_product_on_page_is_not_evidence(self):
        result = parse_specifications(self.page({'a': self.sku('AMOLED'), 'b': self.sku('MicroLED', '456')}), '123')
        self.assertEqual(result['screen_technology'], 'AMOLED')

    def test_conflicting_same_product_skus_do_not_choose_first(self):
        result = parse_specifications(self.page({'a': self.sku('AMOLED'), 'b': self.sku('MicroLED', part='010-12345-01')}), '123')
        self.assertIsNone(result['screen_technology'])
        self.assertEqual(len(result['retail_skus']), 2)

    def test_mip_and_unknown_are_distinct(self):
        self.assertEqual(parse_specifications(self.page({'a': self.sku('transflective memory-in-pixel (MIP)')}), '123')['screen_technology'], 'MIP')
        self.assertIsNone(parse_specifications(self.page({'a': self.sku('color')}), '123')['screen_technology'])

    def test_conflicting_specification_cells_are_not_screen_evidence(self):
        sku = self.sku('AMOLED')
        sku['tabs']['specsTab']['content'] += '<table><tr><th>Display type</th><td>MicroLED</td></tr></table>'
        self.assertIsNone(parse_specifications(self.page({'a': sku}), '123')['screen_technology'])
        self.assertIsNone(parse_specifications(self.page({'a': self.sku('AMOLED or MicroLED')}), '123')['screen_technology'])

    def test_satellite_specification_proves_inreach_only_when_explicit(self):
        sku = self.sku('AMOLED')
        sku['tabs']['specsTab']['content'] += '<table><tr><th>Satellite communication</th><td>yes (inReach plan required)</td></tr></table>'
        self.assertIs(parse_specifications(self.page({'a': sku}), '123')['inreach'], True)
        self.assertIsNone(parse_specifications(self.page({'a': self.sku('AMOLED')}), '123')['inreach'])
