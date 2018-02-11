"""
Singer Tap Twitter
"""

import functools
import io
import os
import sys
import json
import logging

from time import gmtime, strftime
from urllib import parse
import http.client
import threading
import collections
import datetime
from datetime import timezone
import backoff
import dateutil

import pkg_resources
import httplib2
import oauth2 as oauth
import twitter
from jsonschema import validate
from apiclient import discovery
from oauth2client import tools

import singer
import singer.metrics as metrics
from singer import (transform,
                    UNIX_MILLISECONDS_INTEGER_DATETIME_PARSING,
                    Transformer,
                    _transform_datetime,
                    metadata,
                    utils)
from singer.catalog import Catalog, CatalogEntry
import pendulum
import attr

APPLICATION_NAME = 'Singer Twitter Tap'
CURRENT_USER_ID = 0

logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
LOGGER = singer.get_logger()
CONFIG = {}

STREAMS = ['blocks',
           'favorites',
           'followers',
           'friends',
           'home_timeline',
           'lists',
           'memberships',
           'mentions',
           'replies',
           'retweets_of_me',
           'subscriptions',
           'user_retweets',
           'user_timeline'
          ]

DEFAULT_COUNT = 10 # Default count for all Twitter requests where applicable
CREDENTIALS_FILENAME = "twitter.json"

# CONSUMER_KEY = CONFIG['consumer_key']
# CONSUMER_SECRET = CONFIG['consumer_secret']

# REQUEST_TOKEN_URL = CONFIG['request_token_url']
# ACCESS_TOKEN_URL = CONFIG['access_token_url']
# AUTHORIZE_URL = CONFIG['authorize_url']
# CONSUMER = oauth.Consumer(CONSUMER_KEY, CONSUMER_SECRET)

REQUIRED_CONFIG_KEYS = ['start_date',
                        'request_token_url',
                        'access_token_url',
                        'authorize_url',
                        'consumer_key',
                        'consumer_secret',
                        'count'
                       ]

SINCEID_KEY = 'since_id'
STARTDATE_KEY = 'start_date'

BOOKMARK_KEYS = {
    'blocks':STARTDATE_KEY,
    'favorites':SINCEID_KEY,
    'followers':STARTDATE_KEY,
    'friends':STARTDATE_KEY,
    'home_timeline':SINCEID_KEY,
    'lists':STARTDATE_KEY,
    'memberships':STARTDATE_KEY,
    'mentions':SINCEID_KEY,
    'replies':SINCEID_KEY,
    'retweets_of_me':SINCEID_KEY,
    'subscriptions':STARTDATE_KEY,
    'user_retweets':SINCEID_KEY,
    'user_timeline':SINCEID_KEY
}

class TapTwitterException(Exception):
    """ Our own exception """
    pass

class JobTimeout(TapTwitterException):
    """ Timeout exception """
    pass

def transform_datetime_string(dts):
    """ Date function """
    parsed_dt = dateutil.parser.parse(dts)
    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
    else:
        parsed_dt = parsed_dt.astimezone(timezone.utc)
    return singer.strftime(parsed_dt)

def retry_pattern(backoff_type, exception, **wait_gen_kwargs):
    """ Retry request """
    def log_retry_attempt(details):
        """ Log attempt """
        _, exception, _ = sys.exc_info()
        LOGGER.info(exception)
        LOGGER.info('Caught retryable error after %s tries. '+
                    'Waiting %s more seconds then retrying...',
                    details["tries"],
                    details["wait"])

    def should_retry_api_error(exception):
        """ Return exception object """
        # if isinstance(exception, FacebookRequestError):
        if isinstance(exception, TapTwitterException):
            return exception.api_transient_error()
        elif isinstance(exception, JobTimeout):
            return True
        return False

    return backoff.on_exception(
        backoff_type,
        exception,
        jitter=None,
        on_backoff=log_retry_attempt,
        giveup=lambda exc: not should_retry_api_error(exc),
        **wait_gen_kwargs
    )

@attr.s
class Stream(object):
    """ Declare stream type """
    name = attr.ib()
    # account= attr.ib()
    api = attr.ib()
    stream_alias = attr.ib()
    annotated_schema = attr.ib()
    state = attr.ib()

    def fields(self):
        """ Stream fields """
        fields = set()
        if self.annotated_schema:
            props = self.annotated_schema.properties # pylint: disable=no-member
            for k, val in props.items():
                inclusion = val.inclusion
                selected = val.selected
                if selected or inclusion == 'automatic':
                    fields.add(k)
        return fields

@attr.s
class IncrementalStream(Stream):
    """ Declare incremental stream type """
    state = attr.ib()
    
    def _iterate(self, recordset):
        """ iterate stream items """
        max_bookmark = None
        since_id = get_start(self, BOOKMARK_KEYS.get(self.name)) # updated_at
        for record in recordset:
            if record.id and record.id <= since_id:
                continue
            if not max_bookmark or record.id > max_bookmark:
                max_bookmark = record.id
            yield {'record': json.loads(str(record))}

        if max_bookmark:
            yield {'state': advance_bookmark(self, SINCEID_KEY, max_bookmark)}

class Block(Stream):
    """ Block stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=1, factor=1)
        def do_request():
            """ Perform request """
            return self.api.GetBlocks() # skip_status=False,# include_entities=False
        items = do_request()

        for i in items: # pylint: disable=invalid-name
            yield {'record': json.loads(str(i))}

class Favorite(IncrementalStream):
    """ Favorite (favourite) stream object """
    key_properties = ['id']

    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            since_id = get_start(self, BOOKMARK_KEYS.get(self.name))
            count = get_count()
            return self.api.GetFavorites(count=count,
                                         since_id=since_id,
                                         # user_id=user_id,
                                         # screen_name=screen_name,
                                         # max_id=max_id,
                                         # include_entities=include_entities
                                        )

        items = do_request()
        for message in self._iterate(items):
            yield message

        # max_bookmark = None
        # for i in items: # pylint: disable=invalid-name
        #     since_id = get_start(self, BOOKMARK_KEYS.get(self.name))
        #     if since_id == None:
        #         since_id = 0
        #     if i.id > since_id:
        #         max_bookmark = i.id
        #     yield {'record': json.loads(str(i))}

        # if max_bookmark:
        #     yield {'state' : advance_bookmark(self, SINCEID_KEY, str(max_bookmark))}

class Follower(Stream):
    """ Follower stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            count = get_count()
            return self.api.GetFollowers(total_count=count,
                                         # count=count,
                                         # user_id=user_id,
                                         # screen_name=screen_name,
                                         # cursor=cursor,
                                         # total_count=total_count,
                                         # skip_status=skip_status,
                                         # include_user_entities=include_user_entities
                                        )
        items = do_request()
        for i in items: # pylint: disable=invalid-name
            yield {'record': json.loads(str(i))}

class Friends(Stream):
    """ Friends stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            count = get_count()
            return self.api.GetFriends(total_count=count
                                       # count=total_count,
                                       # user_id=user_id,
                                       # screen_name=screen_name,
                                       # cursor=cursor,
                                       # skip_status=skip_status,
                                       # include_user_entities=include_user_entities
                                      )
        items = do_request()
        for i in items: # pylint: disable=invalid-name
            yield {'record': json.loads(str(i))}

class HomeTimeline(IncrementalStream):
    """ Home timeline stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            since_id = get_start(self, BOOKMARK_KEYS.get(self.name))
            count = get_count()

            return self.api.GetHomeTimeline(count=count,
                                            since_id=since_id
                                            # max_id=max_id,
                                            # trim_user=trim_user,
                                            # exclude_replies=exclude_replies,
                                            # contributor_details=contributor_details,
                                            # include_entities=include_entities
                                           )
        items = do_request()
        for message in self._iterate(items):
            yield message

class Lists(Stream):
    """ Lists stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            return self.api.GetLists() # user_id=user_id, # screen_name=screen_name
        items = do_request()
        for i in items: # pylint: disable=invalid-name
            yield {'record': json.loads(str(i))}

class Memberships(Stream):
    """ Memberships stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            count = get_count()
            return self.api.GetMemberships(count=count
                                           # user_id=user_id,
                                           # screen_name=screen_name,
                                           # cursor=cursor,
                                           # filter_to_owned_lists=filter_to_owned_lists
                                          )
        items = do_request()
        for i in items: # pylint: disable=invalid-name
            yield {'record': json.loads(str(i))}

class Mentions(IncrementalStream):
    """ Mentions stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            since_id = get_start(self, BOOKMARK_KEYS.get(self.name))
            count = get_count()
            return self.api.GetMentions(count=count,
                                        since_id=since_id
                                        # max_id=max_id,
                                        # trim_user=trim_user,
                                        # contributor_details=contributor_details,
                                        # include_entities=include_entities
                                       )
        items = do_request()
        for message in self._iterate(items):
            yield message

class Replies(IncrementalStream):
    """ Replies stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            since_id = get_start(self, BOOKMARK_KEYS.get(self.name))
            count = get_count()
            return self.api.GetReplies(count=count,
                                       since_id=since_id
                                       # max_id=max_id,
                                       # trim_user=trim_user
                                      )
        items = do_request()
        for message in self._iterate(items):
            yield message

class RetweetsOfMe(IncrementalStream):
    """ Retweets stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            since_id = get_start(self, BOOKMARK_KEYS.get(self.name))
            count = get_count()
            return self.api.GetRetweetsOfMe(count=count,
                                            since_id=since_id,
                                            # max_id=max_id,
                                            # trim_user=trim_user,
                                            # include_entites=include_entities,
                                            # include_user_entities=include_user_entities
                                           )
        items = do_request()
        for message in self._iterate(items):
            yield message

class Subscriptions(Stream):
    """ Subscriptions stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            count = get_count()
            return self.api.GetSubscriptions(count=count
                                             # user_id=user_id,
                                             # screen_name=screen_name,
                                             # cursor=cursor
                                            )
        items = do_request()
        for i in items: # pylint: disable=invalid-name
            yield {'record': json.loads(str(i))}

class UserRetweets(IncrementalStream):
    """ User retweets stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            since_id = get_start(self, BOOKMARK_KEYS.get(self.name))
            count = get_count()
            return self.api.GetUserRetweets(count=count,
                                            since_id=since_id,
                                            # max_id=max_id,
                                            # trim_user=trim_user
                                           )
        items = do_request()
        for message in self._iterate(items):
            yield message

class UserTimeline(IncrementalStream):
    """ User timeline stream object """
    key_properties = ['id']
    def __iter__(self):
        @retry_pattern(backoff.expo, TapTwitterException, max_tries=5, factor=5)
        def do_request():
            """ Perform request """
            since_id = get_start(self, BOOKMARK_KEYS.get(self.name))
            count = get_count()
            return self.api.GetUserTimeline(count=count,
                                            since_id=since_id,
                                            # user_id=user_id,
                                            # screen_name=screen_name,
                                            # include_rts=include_rts,
                                            # trim_user=trim_user,
                                            # exclude_replies=exclude_replies
                                           )
        items = do_request()
        for message in self._iterate(items):
            yield message

def get_count():
    """ Get config count if available"""
    if CONFIG['count']:
        return CONFIG['count']
    return DEFAULT_COUNT

def get_start(stream, bookmark_key):
    """ Get start date """
    tap_stream_id = stream.name
    state = stream.state or {}
    current_bookmark = singer.get_bookmark(state, tap_stream_id, bookmark_key)

    if bookmark_key == STARTDATE_KEY:
        if current_bookmark is None:
            if not isinstance(stream, IncrementalStream):
                LOGGER.info("no bookmark found for %s, using start_date instead...%s",
                            tap_stream_id,
                            CONFIG['start_date']
                           )
                return pendulum.parse(CONFIG['start_date']).to_datetime_string()
            return None
        return pendulum.parse(current_bookmark).to_datetime_string()
    elif current_bookmark is not None and current_bookmark is not "" and type(current_bookmark) == int:
        return current_bookmark
    else:
        return 0

def advance_bookmark(stream, bookmark_key, since):
    """ Update bookmark """
    tap_stream_id = stream.name
    state = stream.state or {}
    LOGGER.info('advance(%s, %s)', tap_stream_id, since)

    if bookmark_key == STARTDATE_KEY:
        state_since = pendulum.parse(since) if since else None
    else:
        state_since = since

    current_bookmark = get_start(stream, bookmark_key)

    if state_since is None:
        LOGGER.info('Did not get a date for stream %s '+
                    ' not advancing bookmark',
                    tap_stream_id)
    elif not current_bookmark or state_since > current_bookmark:
        LOGGER.info('Bookmark for stream %s is currently %s, ' +
                    'advancing to %s',
                    tap_stream_id, current_bookmark, state_since)
        state = singer.write_bookmark(state, tap_stream_id, bookmark_key, str(state_since))
    else:
        LOGGER.info('Bookmark for stream %s is currently %s ' +
                    'not changing to to %s',
                    tap_stream_id, current_bookmark, state_since)
    return state

def set_current_user_id(user_id):
    """ Set current user ID """
    global CURRENT_USER_ID
    CURRENT_USER_ID = user_id

def get_schema(stream=""):
    """ Get Schema """
    schema_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__))+'/schemas/', stream+'.json')

    if not os.path.exists(schema_path):
        LOGGER.debug("There is no schema for stream " +stream)
        return False

    with open(schema_path, 'r') as schema:
        schema = json.load(schema)
    return schema

def get_credentials():
    """ Get credentials """
    global CURRENT_USER_ID

    consumer = oauth.Consumer(CONFIG['consumer_key'], CONFIG['consumer_secret'])
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)

    credential_path = os.path.join(credential_dir, CREDENTIALS_FILENAME)
    credentials = ""
    if os.path.exists(credential_path):
        with open(credential_path, 'r') as file:
            twitter_credentials = file.read()
            if twitter_credentials:
                credentials = json.loads(twitter_credentials)

    if not credentials or credentials == "":
        credentials_file = open(credential_path, 'w+')

        # Step 1: Get a request token. This is a temporary token that is used for
        # having the user authorize an access token and to sign the request to obtain
        # said access token.
        client = oauth.Client(consumer)
        resp, content = client.request(CONFIG['request_token_url'], "GET")
        if resp['status'] != '200':
            raise Exception("Invalid response %s." % resp['status'])

        request_token = dict(parse.parse_qsl(content.decode('utf-8')))

        # Step 2: Redirect to the provider. Since this is a CLI script we do not
        # redirect. In a web application you would redirect the user to the URL
        # below.

        print("Go to the following link in your browser:")
        print("%s?oauth_token=%s" % (CONFIG['authorize_url'], request_token['oauth_token']))

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
        token = oauth.Token(
            request_token['oauth_token'],
            request_token['oauth_token_secret'])
        token.set_verifier(oauth_verifier)
        client = oauth.Client(consumer, token)

        resp, content = client.request(CONFIG['access_token_url'], "POST")
        access_token = dict(parse.parse_qsl(content.decode('utf-8')))

        print("Access Token:")
        print("    - oauth_token        = %s" % access_token['oauth_token'])
        print("    - oauth_token_secret = %s" % access_token['oauth_token_secret'])
        print("You may now access protected resources using the access tokens above.")

        credentials_file.write(json.dumps(access_token))
        credentials_file.close()
        credentials = access_token

    if 'user_id' in credentials and credentials['user_id'] != "":
        CURRENT_USER_ID = credentials['user_id']

    return credentials

def initialize_stream(name, api, stream_alias, annotated_schema, state):
    """ Create instance of each stream """
    if name == "blocks":
        return Block(name, api, stream_alias, annotated_schema, state=state)
    elif name == "favorites" or name == "favourites":
        return Favorite(name, api, stream_alias, annotated_schema, state=state)
    elif name == "followers":
        return Follower(name, api, stream_alias, annotated_schema, state=state)
    elif name == "friends":
        return Friends(name, api, stream_alias, annotated_schema, state=state)
    elif name == "home_timeline":
        return HomeTimeline(name, api, stream_alias, annotated_schema, state=state)
    elif name == "lists":
        return Lists(name, api, stream_alias, annotated_schema, state=state)
    elif name == "memberships":
        return Memberships(name, api, stream_alias, annotated_schema, state=state)
    elif name == "mentions":
        return Mentions(name, api, stream_alias, annotated_schema, state=state)
    elif name == "replies":
        return Replies(name, api, stream_alias, annotated_schema, state=state)
    elif name == "retweets_of_me":
        return RetweetsOfMe(name, api, stream_alias, annotated_schema, state=state)
    elif name == "subscriptions":
        return Subscriptions(name, api, stream_alias, annotated_schema, state=state)
    elif name == "user_retweets":
        return UserRetweets(name, api, stream_alias, annotated_schema, state=state)
    elif name == "user_timeline":
        return UserTimeline(name, api, stream_alias, annotated_schema, state=state)
    else:
        raise TapTwitterException('Unknown stream {} '.format(name))

def discover_schemas():
    """ Discover API schemas """
    result = {'streams':[]}
    for name in STREAMS:
        LOGGER.info('Loading schema for %s', name)
        schema = get_schema(name)
        mdata = metadata.new()
        metadata.write(mdata,
                       ('properties', 'since_id'),
                       'inclusion',
                       'automatic'
                      )
        result['streams'].append({
            'stream':name,
            'tap_stream_id':name,
            'key_properties':["id"],
            'replication_key':["updated_at"],
            'replication_method':"INCREMENTAL",
            'metadata':metadata.to_list(mdata),
            'schema':schema
            })

    return result

def get_streams_to_sync(api, catalog, state):
    """ Get required streams """
    streams = []
    for stream in STREAMS:
        try:
            selected_stream = next((s for s in catalog.streams if s.tap_stream_id == stream), None)
            if(selected_stream and
               hasattr(selected_stream.schema, 'selected') and
               selected_stream.schema.selected):
                schema = selected_stream.schema
                name = selected_stream.stream
                stream_alias = selected_stream.stream_alias
                streams.append(initialize_stream(name, api, stream_alias, schema, state))
        except TapTwitterException as exception:
            LOGGER.exception(exception)
            continue
    return streams

def do_discover():
    """ Schema discovery """
    LOGGER.info('Loading schemas')
    json.dump(discover_schemas(), sys.stdout, indent=4)

def transform_date_hook(data, typ, schema):
    """ Convert date to string """
    if typ == 'string' and schema.get('format') == 'date-time' and isinstance(data, str):
        transformed = transform_datetime_string(data)
        return transformed
    return data

def do_sync(api, catalog, state):
    """ Perform sync """
    streams_to_sync = get_streams_to_sync(api, catalog, state)

    for stream in streams_to_sync:
        schema = get_schema(stream.name)
        bookmark_key = BOOKMARK_KEYS.get(stream.name)
        singer.write_schema(stream.name,
                            schema,
                            stream.key_properties,
                            bookmark_key,
                            stream.stream_alias
                           )

        with Transformer(pre_hook=transform_date_hook) as transformer:
            with metrics.record_counter(stream.name) as counter:
                for message in stream:
                    if 'record' in message:
                        counter.increment()
                        time_extracted = utils.now()
                        record = transformer.transform(message['record'], schema)
                        singer.write_record(stream.name,
                                            record,
                                            stream.stream_alias,
                                            time_extracted
                                           )
                    elif 'state' in message:
                        singer.write_state(message['state'])
                    else:
                        raise TapTwitterException('Unrecognized message {}'.format(message))

def main_impl():
    """ Main implementation """
    args = utils.parse_args(REQUIRED_CONFIG_KEYS)
    CONFIG.update(args.config)
    credentials = get_credentials()
    access_token = credentials['oauth_token']
    token_secret = credentials['oauth_token_secret']
    api = twitter.Api(
        consumer_key=args.config['consumer_key'],
        consumer_secret=args.config['consumer_secret'],
        access_token_key=access_token,
        access_token_secret=token_secret,
        sleep_on_rate_limit=True
    )

    if args.discover:
        do_discover()
    elif args.properties:
        catalog = Catalog.from_dict(args.properties)
        do_sync(api, catalog, args.state)
    else:
        LOGGER.info("No properties were selected")

def main():
    """ Starting point """
    try:
        main_impl()
    except TapTwitterException as exception:
        LOGGER.critical(exception)
        sys.exit(1)
    except Exception as exception:
        LOGGER.exception(exception)
        for line in str(exception).splitlines():
            LOGGER.critical(line)
        raise exception

if __name__ == '__main__':
    main()
