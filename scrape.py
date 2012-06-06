#!/usr/bin/env python
import json
import re
import requests
import sqlite3
import sys
import tweepy
import urllib


from pprint import pprint


class GerritScrape(object):

    def __init__(self):
        self.headers = {
            "Accept": "application/json,application/json,application/jsonrequest",
            "Content-Type": "application/json; charset=UTF-8",
            "DNT": "1",
            "Origin": "https://review.openstack.org",
            "Referer": "https://review.openstack.org/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_4) " \
                "AppleWebKit/537.1+ (KHTML, like Gecko) Version/5.1.7 " \
                "Safari/534.57.2"
        }
        self.dbconn = sqlite3.connect('gerritwatch.db')

        CONSUMER_KEY = 'fF3J8WKSXjD2EII1HYntA'
        CONSUMER_SECRET = 'WexHW61I8cxQP6OJKX74kfkOedbxqau81EFS6Ss7fRs'
        ACCESS_KEY = '537832144-4Hl8hbnaoP8NYqqy7vpFb7crz0Y8Z13w1ey3mvMI'
        ACCESS_SECRET = 'fDnMVGCzBDyU965mOZllLPsdyyEC2KIpon2opPdJICQ'

        auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
        auth.set_access_token(ACCESS_KEY, ACCESS_SECRET)
        self.api = tweepy.API(auth)

    def change_record_exists(self, change_id):
        c = self.dbconn.cursor()
        t = (change_id,)
        c.execute('SELECT COUNT(id) FROM changes WHERE id=?', t)
        if c.next()[0] == 0:
            return False
        else:
            return True

    def find_changed_reviews(self):
        statuses = ['open', 'merged', 'abandoned']
        for status in statuses:
            sortkey = 'z'
            while True:
                reviews = self.get_reviews(status, sortkey)
                sortkey = self.process_reviews(reviews)
                if sortkey == None:
                    break

    def has_status_changed(self, change_id, status):
        c = self.dbconn.cursor()
        t = (change_id,)
        c.execute('SELECT status FROM changes WHERE id=?', t)
        if c.next()[0] == status:
            return False
        else:
            return True

    def insert_change_record(self, record_tuple):
        c = self.dbconn.cursor()
        c.execute('insert into changes values (?,?)', record_tuple)

    def get_reviews(self, status='open', sortkey='z'):
        payload = {
            "jsonrpc": "2.0",
            "method": "allQueryNext",
            "params": ["status:%s" % status, sortkey, 100],
            "id": 1,
        }
        url = "https://review.openstack.org/gerrit/rpc/ChangeListService"
        r = requests.post(url, verify=False, data=json.dumps(payload),
            headers=self.headers)
        try:
            result = json.loads(r.text)
        except Exception:
            raise Exception(r.text)
        return result

    def process_reviews(self, reviews):
        changes = reviews['result']['changes']
        accounts = reviews['result']['accounts']['accounts']
        last_sortkey = None
        for change in changes:
            change_id = change['id']['id']
            status = str(change['status'])
            last_sortkey = change['sortKey']

            print "Checking %s (%s)... " % (change_id, status),

            if self.change_record_exists(change_id):
                if self.has_status_changed(change_id, status):
                    self.update_status(change_id, status)
                    print "***status changed***"
                else:
                    print
                    continue
            else:
                self.insert_change_record((change_id, status))
                print "***no database record***"

            # Make a notification message
            subject = change['subject']
            if len(subject) > 80:
                subject = "%s..." % subject[:75]
            project = change['project']['key']['name']
            project = re.sub(r'.*/(python-)*', '', project)
            account_id = change['owner']['id']
            try:
                owner = [x['fullName'] for x in accounts 
                    if 'fullName' in x and x['id']['id'] == account_id][0]
                owner = "(%s)" % owner
            except:
                owner = ''

            shortlink = self.shorten_link(change_id)

            message = "%s [%s]: %s %s %s" % (project, status, subject, owner,
                shortlink)
            print message
            self.tweet_update(message)

        self.dbconn.commit()
        return last_sortkey

    def shorten_link(self, change_id):
        url = "https://review.openstack.org/#/c/%s/" % change_id
        r = requests.get('http://is.gd/create.php?format=simple&url=%s' % (
            urllib.quote_plus(url)))
        return str(r.text).strip()

    def tweet_update(self, message):
        self.api.update_status(message)

    def update_status(self, change_id, status):
        c = self.dbconn.cursor()
        c.execute('update changes set status=? where id=?',
            (status, change_id))


g = GerritScrape()
g.find_changed_reviews()




