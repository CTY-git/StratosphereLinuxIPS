# Must imports
from slips_files.common.imports import *

# Your imports
import json
import requests
from requests.auth import HTTPBasicAuth

class RiskIQ(Module, multiprocessing.Process):
    # Name: short name of the module. Do not use spaces
    name = 'Risk IQ'
    description = 'Module to get passive DNS info about IPs from RiskIQ'
    authors = ['Alya Gomaa']

    def init(self):
        self.c1 = self.db.subscribe('new_ip')
        self.channels = {
            'new_ip': self.c1,
        }
        self.read_configuration()

    def read_configuration(self):
        conf = ConfigParser()
        # Read the riskiq api key
        RiskIQ_credentials_path = conf.RiskIQ_credentials_path()
        try:
            with open(RiskIQ_credentials_path, 'r') as f:
                self.riskiq_email = f.readline().replace('\n', '')
                self.riskiq_key = f.readline().replace('\n', '')
                if len(self.riskiq_key) != 64:
                    raise NameError
        except (
            NameError,
            FileNotFoundError,
        ):
            self.riskiq_email = None
            self.riskiq_key = None



    def get_passive_dns(self, ip) -> list:
        """
        Get passive dns info about this ip from passive total/RiskIQ
        """
        try:
            params = {
                'query': ip
            }
            response = requests.get(
                'https://api.riskiq.net/pt/v2/dns/passive',
                params=params,
                timeout=5,
                verify=True,  # Changed from False to True to enable certificate validation
                auth=HTTPBasicAuth(self.riskiq_email, self.riskiq_key)
            )
        except (requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ReadTimeout):
            return

        if response.status_code != 200:
            return
        try:
            response = json.loads(response.text)
        except json.decoder.JSONDecodeError:
            return


        # Store the samples in our dictionary so we can sort them
        pt_data = {}
        # the response will either have 'results' key, OR 'message' key with an error,
        # make sure we have results before processing
        results = response.get('results', False)
        if not results:
            return

        for pt_results in results:
            pt_data[pt_results['lastSeen']] = [
                pt_results['firstSeen'],
                pt_results['resolve'],
                pt_results['collected'],
            ]
        # Sort them by datetime and convert to list, sort the first 10 entries only
        sorted_pt_results = sorted(pt_data.items(), reverse=True)[:10]
        return sorted_pt_results

    def pre_main(self):
        utils.drop_root_privs()
        if not self.riskiq_email or not self.riskiq_key:
            return 1

    def main(self):
        # Main loop function
        if msg := self.get_msg('new_ip'):
            ip = msg['data']
            if utils.is_ignored_ip(ip):
                # return here means keep looping
                return
            # Only get passive total dns data if we don't have it in the db
            if self.db.get_passive_dns(ip):
                return
            # we don't have it in the db , get it from passive total
            if passive_dns := self.get_passive_dns(ip):
                # we found data from passive total, store it in the db
                self.db.set_passive_dns(ip, passive_dns)

