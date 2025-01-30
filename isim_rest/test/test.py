import json
from django.test import Client, TestCase
from isim_rest.neo4j_rest.settings import BASE_DIR


class RestTestCase(TestCase):
    def test_assets(self):
        self.client = Client()

        with open(f'{BASE_DIR}/test/test_data/assets.json') as asset_file:
            assets = json.load(asset_file)
            response = self.client.post('/assets', data=assets, content_type='application/json')
            self.assertEqual(response.status_code, 201)

            response = self.client.get('/asset_info')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.content,
                b'[{"ip":"9.66.11.12","domain_names":["mail.firechmel.ex"],"subnets":["9.66.11.0/24"],'
                b'"contacts":["admin@firechmel.ex"],"missions":[],"critical":0},{"ip":"9.66.11.13",'
                b'"domain_names":["dns.firechmel.ex"],"subnets":["9.66.11.0/24"],"contacts":["admin@firechmel.ex"],'
                b'"missions":[],"critical":0},{"ip":"9.66.11.14","domain_names":["www.firechmel.ex"],'
                b'"subnets":["9.66.11.0/24"],"contacts":["admin@firechmel.ex"],"missions":[],"critical":0}]')

    def test_missions(self):
        with open(f'{BASE_DIR}/test/test_data/cyber_czech_mission_bt1.json') as mission_file:
            missions = json.load(mission_file)
            response = self.client.post('/missions', data=missions, content_type='application/json')
            self.assertEqual(response.status_code, 201)

            response = self.client.get('/missions')
            self.assertEqual(response.status_code, 200)

            for mission in json.loads(response.content.decode('ascii'))[0]:
                self.assertIn(mission['name'], ["Public-Facing Services", "User Services", "Admin Services",
                                                "Custom Application"])
                self.assertEqual(json.loads(mission["structure"]), missions)