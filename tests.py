import unittest
import subprocess
import time, os
from zandronumserver import ZandronumServer
from dotenv import load_dotenv

load_dotenv()

class TestZandronumServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        iwad = f'{os.getenv('IWAD_PATH')}/DOOM.WAD'

        if not os.path.exists(iwad):
            raise unittest.SkipTest('Can\'t find IWAD for zandronum')

        cls.server_process = subprocess.Popen(
            [
                'zandronum-server',
                '-host', '8',
                '-private',
                '-useip', '127.0.0.1',
                '-port', '10666',
                '-iwad', f'{os.getenv('IWAD_PATH')}/DOOM.WAD',
                '+sv_hostname', 'test-server'
            ], 
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        time.sleep(3)

        cls.server = ZandronumServer('127.0.0.1', 10666)


    @classmethod
    def tearDownClass(cls):
        cls.server_process.terminate()
        cls.server_process.wait()

    def test_connection_to_server(cls):
        cls.server.update_info()

        cls.assertEqual(cls.server.name, 'test-server')
        cls.assertEqual(cls.server.maxclients, 8)
    
    def test_rcon_login(cls):
        cls.server.login_rcon('testtest')

if __name__ == '__main__':
    unittest.main()