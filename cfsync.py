#!/usr/bin/env python
# The MIT License (MIT)
# 
# Copyright (c) 2015 Jason Harvey
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import sys
import mechanize
import argparse
import json
import urllib
import git
import tempfile
import shutil
import os
import re

import ConfigParser

default_file = "/etc/cfsync.ini"
parser = argparse.ArgumentParser()
parser.add_argument('--config', '-c', default=default_file,
                    help="Specify config file location. (default: %s)" %
                    default_file)
parser.add_argument('--no-commit', '-n', dest='commit', default=True,
                    action='store_false',
                    help="Write out the JSON data but don't commit or push.")
args = parser.parse_args()


config = ConfigParser.RawConfigParser()
if not config.read([args.config]):
  print 'No config found at %s' % args.config
  sys.exit(1)
section = "cloudflare"

username = config.get(section, "username")
user_id = urllib.quote(config.get(section, "user_id"), safe='')
api_key = urllib.quote(config.get(section, "api_key"), safe='')
login_pass = config.get(section, "login_pass")
archive_repo = config.get(section, "archive_repo")

def login(br):
  login_url = "https://www.cloudflare.com/a/login"
  response = br.open(login_url)
  logindata = {
                "email":    username,
                "password": login_pass,
              }

  m = re.search('"security_token":"(.*?)"', response.read())
  if m:
    token = m.group(1)
    logindata['security_token'] = token
    response = br.open(login_url, data=urllib.urlencode(logindata))
    if "/a/account" not in response.read():
      raise Exception('Login appears to have failed.')
  else:
    raise Exception('Unable to login - no security token present' \
                    'Browser title: %s' %
                    br.title())

def get_zones(br):
  uri = 'https://api.cloudflare.com/client/v4/zones'
  response = br.open(uri)
  data = json.loads(response.read())['result']
  zones = {}
  for zone in data:
    zones[zone['name']] = zone['id']
  return zones


def get_rules(br, zone):
  uri = "https://www.cloudflare.com/api/v2/rpat/load_multi?user_id=%s&z=%s" %\
        (user_id, zone)
  response = br.open(uri)
  rpats = json.loads(response.read())['response']
  return rpats

def get_settings(br, zone_id):
  uri = 'https://api.cloudflare.com/client/v4/zones/%s/settings' % zone_id
  response = br.open(uri)
  data = json.loads(response.read())['result']
  return data

def main():
  target = tempfile.mkdtemp()
  try:
    repo = git.Repo.clone_from(archive_repo, target)
    br = mechanize.Browser()
    login(br)
    br.addheaders = [('X-Auth-Email', username),
                     ('X-Auth-Key', api_key)]
    zones = get_zones(br)

    index_modified = False
    for zone, zone_id in zones.iteritems():
      # sanitize our internet-sourced data
      zone = urllib.quote(zone, safe='')
      zone_id = urllib.quote(zone_id, safe='')
      data = {}
      data['pagerules'] = get_rules(br, zone)
      data['settings'] = get_settings(br, zone_id)
      filename = os.path.join(target, zone)

      newfile = False
      if not os.path.exists(filename):
        newfile = True
      f = open(filename, 'w')
      json.dump(data, f, indent=2, sort_keys=True)
      f.close()
      if repo.is_dirty(index=False) or newfile:
        repo.index.add([zone])
        index_modified = True

    if args.commit and index_modified:
      repo.index.commit("autocommit of changes")
      repo.remote().push()
    if not index_modified:
      print "Remote data matched archive. No changes recorded."
  finally:
    if args.commit:
      shutil.rmtree(target)
    else:
      print "Commit disabled. Changes prepared in %s." % target

if __name__ == '__main__':
  sys.exit(main())
