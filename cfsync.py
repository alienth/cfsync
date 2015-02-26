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
login_pass = config.get(section, "login_pass")
archive_repo = config.get(section, "archive_repo")

def login(br):
  response = br.open("https://www.cloudflare.com/login")
  br.select_form(name="loginForm")
  br["login_email"], br["login_pass"] = (username, login_pass)
  response = br.submit()

  m = re.search('"atok":"(.*?)"', response.read())
  if m:
    atok = m.group(1)
    return atok
  else:
    raise Exception('Unable to locate atok - login may have failed.' \
                    'Browser title: %s' %
                    br.title())


def get_zones(br, atok):
  br.addheaders = [('referer', 'https://www.cloudflare.com/my-websites')]
  uri = 'https://www.cloudflare.com/api/v2/zone/load_index?atok=%s' % atok
  response = br.open(uri)
  index = json.loads(response.read())['response']['zone_index'].values()
  zones = [zone for sublist in index for zone in sublist]
  return zones


def get_rules(br, zone):
  uri = "https://www.cloudflare.com/api/v2/rpat/load_multi?user_id=%s&z=%s" %\
        (user_id, zone)
  response = br.open(uri)
  rpats = json.loads(response.read())
  return rpats

def main():
  target = tempfile.mkdtemp()
  try:
    repo = git.Repo.clone_from(archive_repo, target)
    br = mechanize.Browser()
    atok = urllib.quote(login(br), safe='')
    zones = get_zones(br, atok)

    index_modified = False
    for zone in zones:
      # sanitize our internet-sourced data
      zone = urllib.quote(zone, safe='')
      rules = get_rules(br, zone)
      filename = os.path.join(target, zone)

      newfile = False
      if not os.path.exists(filename):
        newfile = True
      f = open(filename, 'w')
      json.dump(rules, f, indent=2, sort_keys=True)
      f.close()
      if repo.is_dirty(index=False) or newfile:
        repo.index.add([zone])
        index_modified = True

    if args.commit and index_modified:
      repo.index.commit("autocommit of changes")
      repo.remote().push()
    else:
      print "Remote rules matched archive. No changes recorded."
  finally:
    if args.commit:
      shutil.rmtree(target)
    else:
      print "Commit disabled. Changes prepared in %s." % target

if __name__ == '__main__':
  sys.exit(main())
