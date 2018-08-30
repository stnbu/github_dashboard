# -*- mode: python; coding: utf-8 -*-

import os
import sys

# FIXME
# beautiful HACK until I get some stuff figured out.
sys.path.insert(0, '../mutils')

import sys
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

from sqlalchemy import String, ForeignKey
import daemon
import daemon.pidfile

from mutils import rest, simple_alchemy

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

DIR_PATH = None

repos_schema = [
    ('name', String),
    ('description', String),
    ('owner_login', String),
]

commits_schema = [
    ('repo', ((String, ForeignKey('repos.name')), {'nullable': False})),
    ('sha', ((String,), {'primary_key': True})),
    ('commit_message', String),
    ('author_login', String),
]

class GithubFeed(object):

    _session = None

    @classmethod
    def get_db_session(cls):
        if cls._session is not None:
            return cls._session
        db_path = os.path.join(os.path.abspath(DIR_PATH), 'db.sqlite3')
        cls._session = simple_alchemy.get_session(db_path)
        return cls._session

    def __init__(self, dir_path):
        global DIR_PATH
        self.dir_path = DIR_PATH = os.path.abspath(dir_path)
        self.repos = simple_alchemy.get_table_class('repos', schema=repos_schema)
        self.commits = simple_alchemy.get_table_class('commits', schema=commits_schema, include_id=False)

    def get_repos(self):
        api_auth_file = os.path.join(self.dir_path, 'API_AUTH')
        logger.debug('reading {}'.format(api_auth_file))
        username, api_token = open(api_auth_file).read().strip().split(':')
        auth = HTTPBasicAuth(username, api_token)
        location = '/users/{username}/repos'.format(username=username)
        url = urllib.parse.urlunparse(('https', 'api.github.com', location, '', '', ''))
        data = rest.get_json(url, auth=auth)
        public_repos = [r for r in data if not r['private']]
        repos = sorted(public_repos, key=lambda r: parse_dt(r['updated_at']), reverse=True)[:5]
        logger.debug('got {} repo records'.format(len(repos)))
        return repos

    def update_repos(self, repos):
        session = self.get_db_session()
        updates = []
        for repo in repos:
            repo_data = {}
            repo_data['name'] = repo['name']
            repo_data['description'] = repo['description']
            repo_data['owner_login'] = repo['owner']['login']
            updates.append(self.repos(**repo_data))
        session.add_all(updates)
        session.commit()

    def update_commits(self, repos):
        api_auth_file = os.path.join(self.dir_path, 'API_AUTH')
        logger.debug('reading {}'.format(api_auth_file))
        username, api_token = open(api_auth_file).read().strip().split(':')
        auth = HTTPBasicAuth(username, api_token)
        location = '/users/{username}/repos'.format(username=username)
        url = urllib.parse.urlunparse(('https', 'api.github.com', location, '', '', ''))
        now = datetime.datetime.now(tz=pytz.UTC)
        since = now - datetime.timedelta(days=365)
        since = since.strftime('%Y-%m-%dT%H:%M:%SZ')
        session = self.get_db_session()
        updates = []
        for repo in repos:
            location = '/repos/{username}/{repo}/commits'.format(username=username, repo=repo['name'])
            query = 'since={since}'.format(since=since)
            url = urllib.parse.urlunparse(('https', 'api.github.com', location, '', query, ''))
            commits = rest.get_json(url, auth=auth)
            logger.debug('got {} commits for repo {}'.format(len(commits), repo['name']))
            commit_data = {}
            # TODO: how are they ordered? Get the most recent...
            for commit in commits:
                commit_data['repo'] = repo['name']
                commit_data['sha'] = commit['sha']
                commit_data['commit_message'] = commit['commit']['message']
                commit_data['author_login'] = commit['author']['login']
                updates.append(self.commits(**commit_data))
        session.add_all(updates)
        session.commit()

if __name__ == '__main__':

    hf = GithubFeed(dir_path='.')
    data = hf.get_repos()
    hf.update_repos(data)
    hf.update_commits(data)
