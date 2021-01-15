#! /usr/bin/env python3
# Copyright 2021 Akamai Technologies, Inc. All Rights Reserved.
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
#
# You may obtain a copy of the License at 
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Sample code to perform an automated migraton from one product_type to another product_type
# This code is NOT error-proof and does not handle error-situations nicely (but quickly exits in most error situations)
#
# WARNING: Please verify the code before you run it, use at your own risk
"""
akamai-get - get Akamai stuff

urldebug   - provide an akamaized url and receive information like statuscode, cpcode, origin
reference  - translate an Akamai reference or errorstring
origins    - abstract the origins used from a property configurations

Use --help to get syntax info
Full information can be reviewed using --json export.json

Eric Debeij
"""

import requests
import logging
import json
import os
import re
import datetime
import sys
import csv
import traceback 
import argparse
import html

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from urllib.parse import urlencode
from urllib.parse import urljoin
from akamai.edgegrid import EdgeGridAuth
from akamai.edgegrid import EdgeRc

class CacheControl:
    '''
    Supportclass to easily dump and load from cachefiles
    '''
    def __init__(self, cachefolder):
        self._cachefolder = os.path.expanduser(os.path.expandvars(cachefolder)).rstrip('/')

    def cachename(self, cachename, extension='.json', mkdirs=False):
        """ Common utility to calculate the full cachename """
        fullname = '{}/{}{}'.format(self._cachefolder, cachename, extension)
        if mkdirs:
            folder = os.path.dirname(cachename)
            os.makedirs('{}/{}'.format(self._cachefolder, folder), exist_ok=True)
        return fullname

    def dump(self, cachename, data, extension='.json'):
        """ Dump into the cache """
        fullname = self.cachename(cachename, mkdirs=True, extension=extension)
        with open(fullname, 'w') as fp:
            json.dump(data, fp)   

    def load(self, cachename, extension='.json'):
        """" Load object from the cache """        
        fullname = self.cachename(cachename, extension=extension, mkdirs=False)
        try:
            with open(fullname, 'r') as fp:
                data = json.load(fp)
                return data
        except FileNotFoundError:
            return None

        return None

class RuleInfo:
    '''
    Support class to flatten down a ruletree in a list of behaviors and criteria
    '''
    def __init__(self, rules):
        self._rules = rules
        self._behaviors = {}
        self._criteria = {}
        if self._rules:
            self._runrules(self._rules['rules'])
 
    def _runrules(self, rule):
        for behavior in rule['behaviors']:
            if behavior['name'] not in self._behaviors:
                self._behaviors[behavior['name']] = []
            self._behaviors[behavior['name']].append(behavior)

        if 'criteria' in rule:
            for criteria in rule['criteria']:
                if criteria['name'] not in self._criteria:
                    self._criteria[criteria['name']] = []
                criteria['rulename'] = rule['name']
                self._criteria[criteria['name']].append(criteria)

        for child in rule['children']:
            self._runrules(child)

    @property
    def behaviors(self):
        return self._behaviors

    @property
    def criteria(self):
        return self._criteria

# Link to the logger being used
LOG = logging.getLogger()
# The retry strategy ensure we attempt every call maximum 3 times and wait respectively 0.5, 1 and 2 seconds
retry_strategy = Retry(
    total=3,
    status_forcelist =[429,500,502,503,504],
    method_whitelist = ["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"],
    backoff_factor=1
)

class AkamaiBase:
    '''
    Support class to somewhat easily use the Akamai API's
    '''
    def __init__(self, config, section, account=None):
        self._config=config
        self._section=section
        self._account=account

        self.edgerc = EdgeRc(os.path.expanduser(os.path.expandvars(config)))
        self.auth= EdgeGridAuth.from_edgerc(self.edgerc, section=section)
        self.baseurl = 'https://{}'.format(self.edgerc.get(section, 'host'))
        self.adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.mount("https://", self.adapter)

    def _apipath(self, endpoint, parameters=None):
        if self._account:
            if not parameters:
                parameters = {}
            parameters['accountSwitchKey'] = self._account
        ttpath = endpoint
        if parameters and len(parameters) > 0 and '?' not in ttpath:
            ttpath += '?' + urlencode(parameters) 
        thepath = urljoin(self.baseurl, ttpath)
        LOG.info('path: %s', thepath)
        return thepath

class AkamaiDiag(AkamaiBase):
    def __init__(self, config, section, account=None):
        super().__init__(config, section, account=account)

    def urldebug(self, urltotest):
        response = self.session.get(
            self._apipath('/diagnostic-tools/v2/url-debug',
                parameters=dict(url=urltotest)
            )
        )
        return response.json()

    def reference(self, errorCode):
        errorCode = html.unescape(errorCode)
        if '#' in errorCode:
            errorCode = errorCode.split('#')[1]
        response = self.session.get(
            self._apipath(f'/diagnostic-tools/v2/errors/{errorCode}/translated-error'
            )
        )
        return response.json()

    def estats(self, urltotest):
        response = self.session.get(
            self._apipath('/diagnostic-tools/v2/estat',
                parameters=dict(url=urltotest)
            )
        )
        return response.json()

    def cpstats(self, cpcode):
        response = self.session.get(
            self._apipath(f'/diagnostic-tools/v2/cpcodes/{cpcode}/estats')
        )
        return response.json()

    def propertybyhostname(self, hostname):
        reqbody = dict(hostname=hostname)
        response = self.session.post(
            self._apipath('/papi/v1/search/find-by-value'), 
            json=reqbody, 
            headers={"Content-Type": "application/json"}
        )
        for x in response.json()["versions"]["items"]:
            if x["productionStatus"] == "ACTIVE":
                return x
        return None

    def propertyrules(self, hostname):
        property = self.propertybyhostname(hostname)
        if property:
            propertyId = property["propertyId"]
            propertyVersion = property["propertyVersion"]
            response = self.session.get(
                self._apipath(f'/papi/v1/properties/{propertyId}/versions/{propertyVersion}/rules',
                    parameters=dict(contractId=property["contractId"], groupId =property["groupId"],
                    validateMode="fast", validateRules="false"))       
            )
            return response.json()
        return None
            
    def origins(self, hostname):
        rules = self.propertyrules(hostname)
        if rules:
            ruleinfo = RuleInfo(rules)
            return ruleinfo.behaviors['origin']
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter)
    
    parser.add_argument('--account', help='account selector')
    parser.add_argument('--edgerc', default='~/.edgerc', help='Path to the edgerc file')
    parser.add_argument('--section', default='default', help='Edgerc section')
    parser.add_argument('--json', help='Export into json')
    parser.add_argument('--debug', help='Do some logging')

    subparsers = parser.add_subparsers(dest="command")
    
    parser_urldebug = subparsers.add_parser("urldebug")
    parser_urldebug.add_argument('URL', help='url to test')

    parser_urldebug = subparsers.add_parser("reference")
    parser_urldebug.add_argument('reference', help='Akamai error reference')

    parser_origins = subparsers.add_parser("origins")
    parser_origins.add_argument("hostname", help="akamaized hostname")

    args = parser.parse_args()

    if args.debug:
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler = logging.FileHandler(args.debug)
        handler.setFormatter(formatter)
        LOG.addHandler(handler)
        LOG.setLevel(logging.DEBUG)

    akadiag = AkamaiDiag(args.edgerc, args.section, args.account)
    
    if args.command == 'urldebug':
        result = akadiag.urldebug(args.URL)

        try:
            for x in result["urlDebug"]["httpResponse"]:
                if x['value']:
                    print('{name:<22}: {value}'.format(**x))
        except:
            print(json.dumps(result, indent=2))

    elif args.command == 'reference':
        result = akadiag.reference(args.reference)
        te=result["translatedError"]
        for x in te:
            if te[x] and (isinstance(te[x], int) or isinstance(te[x],str)):
                print('{:<22}: {}'.format(x, te[x]))

    elif args.command == 'origins':
        result = akadiag.origins(args.hostname)
        if result is None:
            print('Problem, hostname incorrect or issue with accessing the API', file=sys.stderr)
        else:
            for x in result:
                o = x['options']
                if o["originType"] == "CUSTOMER":
                    print('{hostname}'.format(**o))
                elif o["originType"] == "NET_STORAGE":
                    print('{downloadDomainName}'.format(**o['netStorage']))

    else:
        parser.print_help()

    if args.json:
        with open(args.json, 'w') as fp:
            json.dump(result, fp)




