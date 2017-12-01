#!/usr/bin/env python3

import argparse
import functools
import io
import os
import sys
import json
import logging
import collections
import threading
import http.client
import urllib
import pkg_resources
import singer
import httplib2
import oauth2 as oauth
import twitter 
from time import gmtime, strftime

from jsonschema import validate
from apiclient import discovery
from oauth2client import tools
from urllib import parse

try:
    state = {}
    config = {}
    count=10 # Default count for all Twitter requests where applicable 

    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', help='Config file', required=True)
    parser.add_argument('-s', '--state', help='State file', required=False)
    flags = parser.parse_args()

    if flags.config:
        with open(flags.config) as config_file:
            config = json.load(config_file)

    if flags.state:
        with open(flags.state) as config_file: 
            state = json.load(config_file)
       
except ImportError:
    flags = None

logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
logger = singer.get_logger()

APPLICATION_NAME = 'Singer Twitter Tap'

consumer_key = config['consumer_key']
consumer_secret = config['consumer_secret']
credentials_file_name = "twitter.json"
current_user_id = 0 
# End

# Do not change these values
request_token_url = config['request_token_url']
access_token_url= config['access_token_url']
authorize_url = config['authorize_url']
# End 

consumer = oauth.Consumer(consumer_key, consumer_secret)

def get_schema(stream=""): 

    schema_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),'tap_twitter/schemas/', stream+'.json')

    if not os.path.exists(schema_path): 
        logger.debug ("There is no schema for stream " +stream)
        return False 

    with open(schema_path, 'r') as schema: 
        schema = json.load(schema)
    return schema

def get_credentials():

    global current_user_id

    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)

    credential_path = os.path.join(credential_dir, credentials_file_name)
    credentials = ""

    if os.path.exists(credential_path):
        
        with open(credential_path, 'r') as file:
            twitter_credentials = file.read()
            if twitter_credentials:
                credentials = json.loads(twitter_credentials);

    if not credentials or credentials=="":

        credentials_file = open(credential_path, 'w+')

        # Step 1: Get a request token. This is a temporary token that is used for 
        # having the user authorize an access token and to sign the request to obtain 
        # said access token.
        client = oauth.Client(consumer)

        resp, content = client.request(request_token_url, "GET")

        if resp['status'] != '200':
            raise Exception("Invalid response %s." % resp['status'])

        request_token = dict(parse.parse_qsl(content.decode('utf-8')))

        # Step 2: Redirect to the provider. Since this is a CLI script we do not 
        # redirect. In a web application you would redirect the user to the URL
        # below.

        print ("Go to the following link in your browser:")
        print ("%s?oauth_token=%s" % (authorize_url, request_token['oauth_token']))

        # After the user has granted access to you, the consumer, the provider will
        # redirect you to whatever URL you have told them to redirect to. You can 
        # usually define this in the oauth_callback argument as well.
        accepted = 'n'
        while accepted.lower() == 'n':
            accepted = input('Have you authorized me? (y/n) ')
        oauth_verifier = input('What is the PIN? ')

        # Step 3: Once the consumer has redirected the user back to the oauth_callback
        # URL you can request the access token the user has approved. You use the 
        # request token to sign this request. After this is done you throw away the
        # request token and use the access token returned. You should store this 
        # access token somewhere safe, like a database, for future use.
        token = oauth.Token(request_token['oauth_token'],
            request_token['oauth_token_secret'])
        token.set_verifier(oauth_verifier)
        client = oauth.Client(consumer, token)

        resp, content = client.request(access_token_url, "POST")
        access_token = dict(parse.parse_qsl(content.decode('utf-8')))

        print ("Access Token:")
        print ("    - oauth_token        = %s" % access_token['oauth_token'])
        print ("    - oauth_token_secret = %s" % access_token['oauth_token_secret'])
        print ("You may now access protected resources using the access tokens above." )


        credentials_file.write(json.dumps(access_token))
        credentials_file.close()
        credentials = access_token

    if 'user_id' in credentials and not credentials['user_id']=="" : current_user_id = credentials['user_id']

    return credentials

def getCurrentUserId(): 

    global current_user_id
    if not current_user_id == 0: return current_user_id

def main():
 
    global state
    global count 

    credentials = get_credentials()
    token = credentials['oauth_token']
    token_secret = credentials['oauth_token_secret']
    api = twitter.Api(consumer_key,consumer_secret,token,token_secret)

    stream = config.get('stream')
    state[stream] = {}

    last_run = strftime("%Y-%m-%d %H:%M:%S", gmtime())
    state[stream]['last_run'] = last_run

    if stream == "user_timeline": 

        if 'user_timeline' in state and 'since_id' in state['user_timeline'] and not state['user_timeline']['since_id'] == "":
            since_id = state['user_timeline']['since_id']
        else: since_id = ""

        screen_name=''
        include_rts=''
        trim_user = ''
        exclude_replies = ''

        if stream in config: 

            c = config[stream]
            if 'user_id' in c: user_id = c['user_id']
            if 'screen_name' in c: screen_name = c['screen_name']            
            if 'count' in c : count = c['count']
            if 'include_rts' in c : include_rts = c['include_rts']
            if 'trim_user' in c : trim_user = c['trim_user']
            if 'exclude_replies' in c : exclude_replies = c['exclude_replies']

        items = api.GetUserTimeline(since_id=since_id, 
                                    user_id=user_id, 
                                    screen_name=screen_name, 
                                    count=5,
                                    include_rts=include_rts,
                                    trim_user=trim_user,
                                    exclude_replies=exclude_replies)

        if len(items) and items[0].id:
            state[stream] = {}
            state[stream]['since_id'] = items[0].id

    elif stream=="home_timeline":

        if stream in state and 'since_id' in state[stream] and not state[stream]['since_id'] == "":
            since_id = state[stream]['since_id']
        else: since_id = ""

        max_id=''
        trim_user=''
        exclude_replies=''
        contributor_details=''
        include_entities=''

        if stream in config:

            c = config[stream]
            if 'count' in c: count = c['count']
            if 'max_id' in c: max_id = c['max_id']
            if 'trim_user' in c: trim_user = c['trim_user']
            if 'exclude_replies' in c: exclude_replies = c['exclude_replies']
            if 'contributor_details' in c: contributor_details = c['contributor_details']
            if 'include_entities' in c: include_entities = c['include_entities']

        items = api.GetHomeTimeline(count=count,
                                    since_id=since_id,
                                    max_id=max_id,
                                    trim_user=trim_user,
                                    exclude_replies=exclude_replies,
                                    contributor_details=contributor_details,
                                    include_entities=include_entities
                                    )    


        if len(items) and items[0].id:
            state[stream] = {}
            state[stream]['since_id'] = items[0].id

    elif stream=="user_retweets":
        
        if stream in state and 'since_id' in state[stream] and not state[stream]['since_id'] == "":
            since_id = state[stream]['since_id']
        else: since_id = ""

        max_id = ''
        trim_user = ''

        if stream in config:

            c = config[stream]
            if 'count' in c: count = c['count']
            if 'max_id' in c: max_id = c['max_id']
            if 'trim_user' in c: trim_user = c['trim_user']

        items = api.GetUserRetweets(
                                    count=count,
                                    since_id=since_id,
                                    max_id=max_id,
                                    trim_user=trim_user
                                    )            

        if len(items) and items[0].id:
            state[stream] = {}
            state[stream]['since_id'] = items[0].id


    elif stream=="replies":

        if stream in state and 'since_id' in state[stream] and not state[stream]['since_id'] == "":
            since_id = state[stream]['since_id']
        else: since_id = ""

        items = api.GetReplies( since_id=since_id,
                                count=count,
                                max_id=max_id,
                                trim_user=trim_user
                                )

        if len(items) and items[0].id:
            state[stream] = {}
            state[stream]['since_id'] = items[0].id

    elif stream=="retweets_of_me":

        if stream in state and 'since_id' in state[stream] and not state[stream]['since_id'] == "":
            since_id = state[stream]['since_id']
        else: since_id = ""

        max_id = ''
        trim_user = ''
        include_entities = ''
        include_user_entities = ''

        if stream in config:

            c = config[stream]
            if 'count' in c: count = c['count']
            if 'max_id' in c: max_id = c['max_id']
            if 'trim_user' in c: trim_user = c['trim_user']
            if 'include_entities' in c: include_entities = c['include_entities']
            if 'include_user_entities' in c: include_user_entities = c['include_user_entities']

        items = api.GetRetweetsOfMe(count=count,
                                    since_id=since_id,
                                    max_id=max_id,
                                    trim_user=trim_user,
                                    include_entites=include_entities,
                                    include_user_entities=include_user_entities
                                    )        

        if len(items) and items[0].id:
            state[stream] = {}
            state[stream]['since_id'] = items[0].id

    elif stream=="blocks":

        skip_status = ''
        include_entities = ''

        if stream in config:

            c = config[stream]
            if 'skip_status' in c: skip_status = c['skip_status']
            if 'include_entities' in c: include_entities = c['include_entities']

        items = api.GetBlocks(  skip_status=skip_status,
                                include_entities=include_entities)   

    elif stream=="mutes":

        skip_status = ''
        include_entities = ''

        if stream in config:

            c = config[stream]
            if 'skip_status' in c: skip_status = c['skip_status']
            if 'include_entities' in c: include_entities = c['include_entities']

        items = api.GetMutes(   skip_status=skip_status,
                                include_entities=include_entities
                                )
    elif stream=="followers":

        user_id=''
        screen_name=''
        cursor=''
        total_count=10
        skip_status = ''
        include_user_entities = ''

        if stream in config:

            c = config[stream]
            if 'user_id' in c: user_id = c['user_id']
            if 'screen_name' in c: screen_name = c['screen_name']
            if 'cursor' in c: cursor = c['cursor']
            if 'count' in c: count = c['count']            
            if 'total_count' in c and not c['total_count']=="" : total_count = c['total_count']
            if 'skip_status' in c: skip_status = c['skip_status']
            if 'include_user_entities' in c: include_user_entities = c['include_user_entities']

        items = api.GetFollowers(   user_id=user_id,
                                    screen_name=screen_name,
                                    cursor=cursor,
                                    count=count,
                                    total_count=total_count,
                                    skip_status=skip_status,
                                    include_user_entities=include_user_entities
                                )     

    elif stream=="friends":

        user_id=''
        screen_name=''
        cursor=''
        total_count=10
        skip_status = ''
        include_user_entities = ''

        if stream in config:

            c = config[stream]
            if 'user_id' in c: user_id = c['user_id']
            if 'screen_name' in c: screen_name = c['screen_name']
            if 'cursor' in c: cursor = c['cursor']
            if 'count' in c: count = c['count']            
            if 'total_count' in c and not c['total_count']=="" : total_count = c['total_count']
            if 'skip_status' in c: skip_status = c['skip_status']
            if 'include_user_entities' in c: include_user_entities = c['include_user_entities']

        items = api.GetFriends( user_id=user_id,
                                screen_name=screen_name,
                                cursor=cursor,
                                count=count,
                                total_count=total_count,
                                skip_status=skip_status,
                                include_user_entities=include_user_entities
                                )     
    
    elif stream=="favorites" or stream=="favourites":

        stream = "favorites"

        if stream in state and 'since_id' in state[stream] and not state[stream]['since_id'] == "":
            since_id = state[stream]['since_id']
        else: since_id = ""

        user_id=''
        screen_name=''
        max_id = ''
        include_entities = ''

        if stream in config:

            c = config[stream]
            if 'user_id' in c: user_id = c['user_id']
            if 'screen_name' in c: screen_name = c['screen_name']
            if 'count' in c: count = c['count']            
            if 'max_id' in c: max_id = c['max_id']
            if 'include_entities' in c: include_entities = c['include_entities']

        items = api.GetFavorites(   user_id=user_id,
                                    screen_name=screen_name,
                                    count=count,
                                    since_id=since_id,
                                    max_id=max_id,
                                    include_entities=include_entities
                                )   

        if len(items) and items[0].id:
            state[stream] = {}
            state[stream]['since_id'] = items[0].id

    elif stream=="mentions":
        
        if stream in state and 'since_id' in state[stream] and not state[stream]['since_id'] == "":
            since_id = state[stream]['since_id']
        else: since_id = ""

        max_id = ''
        trim_user = ''
        contributor_details = ''
        include_entities = ''

        if stream in config:

            c = config[stream]
            if 'count' in c: count = c['count']            
            if 'max_id' in c: max_id = c['max_id']
            if 'trim_user' in c: trim_user = c['trim_user']            
            if 'contributor_details' in c: contributor_details = c['contributor_details']            
            if 'include_entities' in c: include_entities = c['include_entities']

        items = api.GetMentions(    count=count,
                                    since_id=since_id,
                                    max_id=max_id,
                                    trim_user=trim_user,
                                    contributor_details=contributor_details,
                                    include_entities=include_entities
                                    )

        if len(items) and items[0].id:
            state[stream]['since_id'] = items[0].id

    elif stream=="subscriptions":

        user_id = ''
        screen_name = ''
        cursor = ''

        if stream in config:

            c = config[stream]
            if 'user_id' in c: user_id = c['user_id']            
            if 'screen_name' in c: screen_name = c['screen_name']                        
            if 'count' in c: count = c['count']            
            if 'cursor' in c: cursor = c['cursor']

        items = api.GetSubscriptions(   user_id=user_id,
                                        screen_name=screen_name,
                                        count=count,
                                        cursor=cursor
                                        )            

    elif stream=="memberships":

        user_id = ''
        screen_name = ''
        cursor = ''
        filter_to_owned_lists = ''
        
        if stream in config:

            c = config[stream]
            if 'user_id' in c: user_id = c['user_id']            
            if 'screen_name' in c: screen_name = c['screen_name']                        
            if 'count' in c: count = c['count']            
            if 'cursor' in c: cursor = c['cursor']
            if 'filter_to_owned_lists' in c: filter_to_owned_lists = c['filter_to_owned_lists']

        items = api.GetMemberships( user_id=user_id,
                                    screen_name=screen_name,
                                    count=count,
                                    cursor=cursor,
                                    filter_to_owned_lists=filter_to_owned_lists
                                    )

    elif stream=="lists":        

        user_id = getCurrentUserId()
        screen_name = ''

        if stream in config:

            c = config[stream]
            if 'user_id' in c and not c['user_id']=="": user_id = int(c['user_id'])
            if 'screen_name' in c: screen_name = c['screen_name']    

        items = api.GetLists(   
                                user_id=user_id,
                                screen_name=screen_name
                                )         
    else:
        logger.debug('Stream not found')
        return False

    schema = get_schema(stream)
    singer.write_schema(stream, schema, 'id')
    status = []
    for t in items: 
        status.append(json.loads(str(t)))
    singer.write_records(stream, status)
    singer.write_state(state)
    sys.exit(-1)
    logger.debug("Exiting normally")

if __name__ == '__main__':
    main()
