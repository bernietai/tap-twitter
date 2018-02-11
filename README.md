# tap-twitter

Thank you for using my Singer Twitter Tap.

This tap: 

- Outputs *count* records from a selection of Twitter resources
  - Blocks
  - Favorites
  - Followers
  - Friends
  - Home Timeline
  - Lists
  - Memberships
  - Mentions
  - Replies
  - Retweets of Me 
  - Subscriptions
  - User Retweets 
  - User Timeline
- Outputs *schema* for each Twitter resource
- Outputs *state* data. Some data, for instance, *since_id* in the "mentions" stream, can be used to perform delta requests

### Install

```pip install tap-twitter```

### Step by Step

### Step 1: Create a Twitter App

To create a Twitter App for use with this Tap, visit [Twitter Apps](https://apps.twitter.com)

### Step 2: Configure stream and parameters

Each Twitter resource is a stream. 

You will need to configure Twitter App details in tap-twitter/config.json. 

  - **start_date** (Optional). Not used in Twitter API queries, leave as "1971-01-01 00:00:00"
  - **consumer_key**
  - **consumer_secret**
  - **count** - number of records to retrieve. All streams


### Step 3: Select Stream

In *tap-twitter/catalog.json*, to query 1 or more of the following streams, set its "schema" > "selected" value to "True". 

  1.  blocks
  1. favorites
  1. followers
  1. friends
  1. home_timeline
  1. lists
  1. memberships
  1. mentions
  1. replies
  1. retweets_of_me 
  1. subscriptions
  1. user_retweets
  1. user_timeline

For example, to get a list of mentions: 

``` 
...
            "tap_stream_id": "mentions",
            "replication_key": [
                "since_id"
            ],
            "schema": {
                ...
                "type": "object",
                "additionalProperties": false,
                "selected":true
            },
...
```

### Step 4: Run Twitter Tap (1st time)

It is necessary to setup Twitter credentials when running this Tap for the first time (i.e. access token). Once credentials are setup, it can be reused in subsequent requests. Credentials are stored in ~/.credentials/twitter.json

Run: ```tap-twitter -c tap-twitter/config.json``` without piping to a target. You will be prompted to authorize Twitter: 

> Go to the following link in your browser:
> https://api.twitter.com/oauth/authorize?oauth_token=CF3m3QAAAAAA3DfFAAABYAzeLmo
> Have you authorized me? (y/n) 0768235
> What is the PIN? 0768235
> Access Token:
> oauth_token = 16900279-b9uN27YEtYdHsrFOd932wGrFzYwBXbcOpRwNfrOQW
> oauth_token_secret = FirCxFzLdD1oyL3KRKorMvf4wzjmcSG41VSG3Kudxrt1P
> You may now access protected resources using the access tokens above. 

Now you can pipe twitter results to a Singer Target e.g.

``` tap-twitter -c tap-twitter/config.json -s tap-twitter/state.json | target-gsheet -c gsheet.config.json```

Please fav my Tap repo! Appreciate feedback if you are using this Tap, thanks.

### Credits

* [Python Twitter](https://github.com/bear/python-twitter) by the Python-Twitter Developers

Copyright 2018 [Bernard Tai](http://bernardtai.net)
