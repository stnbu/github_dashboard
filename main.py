# -*- mode: python; coding: utf-8 -*-

import os
import sys

# FIXME
# beautiful HACK until I get some stuff figured out.
sys.path.insert(0, '../mutils')

import time
import tempfile
import re
import requests
import datetime
import pytz
import json
import urllib
from requests.auth import HTTPBasicAuth
import logging
import logging.handlers
import lockfile
from dateutil.parser import parse as parse_dt

import daemon
import daemon.pidfile

from mutils import rest

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def rr(location, query='', auth=None):
    url = urllib.parse.urlunparse(('https', 'api.github.com', location, '', query, ''))
    return rest.get_json(url, auth=auth)

def main(dir_path, daemon=True):
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
        now = datetime.datetime.now(tz=pytz.UTC)
        since = now - datetime.timedelta(days=365)
        since = since.strftime('%Y-%m-%dT%H:%M:%SZ')
        for i, repo in enumerate(repos):
            url = '/repos/{username}/{repo}/commits'.format(username=username, repo=repo['name'])
            query = 'since={since}'.format(since=since)
            commits = rr(url, query=query, auth=auth)
            logger.debug('got {} commits for repo {}'.format(len(commits), repo['name']))
            repos[i]['commits'] = commits
        with tempfile.NamedTemporaryFile(mode='w', dir='/tmp', delete=False) as f:
            logger.debug('writing out data to temp file {}'.format(f.name))
            json.dump(repos, f)
            
        logger.debug('renaming {} -> {}'.format(f.name, data_file))
        os.rename(f.name, data_file)
        logger.debug('sleeping for {}s'.format(sleep_time))
        time.sleep(sleep_time)

if __name__ == '__main__':

    from mutils.simple_daemon import daemonize

    daemonize(main)
