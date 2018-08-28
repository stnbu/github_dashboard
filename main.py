# -*- mode: python; coding: utf-8 -*-

import os
import sys
import time
import tempfile
import re
import requests
import json
import urllib
from requests.auth import HTTPBasicAuth
import logging
import logging.handlers
import lockfile
from dateutil.parser import parse as parse_dt

import daemon
import daemon.pidfile

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# # syslog... this is not working. cannot set LEVEL. only see warn+
# kwargs = {}
# if os.path.exists('/var/run/syslog'):
#     kwargs['address'] = '/var/run/syslog'
# syslog_handler = logging.handlers.SysLogHandler(**kwargs)
# syslog_handler.setLevel(logging.DEBUG)
# logger.addHandler(syslog_handler)

def rr(location, query='', auth=None):
    """request+response -- given a location and query, just return the (json) data.
    Handle errors appropriately.
    """

    location = '/' + location.lstrip('/')

    url = urllib.parse.urlparse(urllib.parse.urlunparse(
        ('https', 'api.github.com', location, '', query, '')
    )).geturl()

    logger.debug('trying to get {}'.format(url))
    response = requests.get(url, auth=auth)
    
    if response.status_code != 200:
        logger.error('when getting {}: {}'.format(url, response.reason))
        raise Exception(response.reason)
    return response.json()

def main(dir_path):
    """Given a writable directory `dir_path`, get interesting, recent repo data from github

    A file called `API_AUTH` containing a string `username:auth_token` is expectied to exist. `username` is used both
    for authentication and identifying the github user.
    """
    
    # syslog?
    fh = logging.FileHandler(os.path.join(dir_path, 'logs'))
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)

    sleep_time = 3600

    api_auth_file = os.path.join(dir_path, 'API_AUTH')
    logger.debug('reading {}'.format(api_auth_file))
    username, api_token = open(api_auth_file).read().strip().split(':')
    auth = HTTPBasicAuth(username, api_token)
    data_file = os.path.join(dir_path, 'repos.json')
    
    while True:
        data = rr('/users/{username}/repos'.format(username=username), auth=auth)
        public_repos = [r for r in data if not r['private']]
        repos = sorted(public_repos, key=lambda r: parse_dt(r['updated_at']), reverse=True)[:5]
        logger.debug('got {} repo records'.format(len(repos)))
        with tempfile.NamedTemporaryFile(mode='w', dir='/tmp', delete=False) as f:
            logger.debug('writing out data to temp file {}'.format(f.name))
            json.dump(repos, f)
            
        logger.debug('renaming {} -> {}'.format(f.name, data_file))
        os.rename(f.name, data_file)
        logger.debug('sleeping for {}s'.format(sleep_time))
        time.sleep(sleep_time)

if __name__ == '__main__':

    script_name, dir_path = sys.argv

    logger.debug('starting daemon {} using path {}'.format(script_name, dir_path))
    
    with daemon.DaemonContext(
            working_directory=dir_path,
            pidfile=daemon.pidfile.PIDLockFile(os.path.join(dir_path, 'pid')),
            
    ):
        main(dir_path)
    
