# tap-twitter

Thank you for using my Singer Twitter Tap.

This tap: 

- Pulls data from a selection of Twitter resources
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

You will need to configure Twitter App details in configs/config.json. 

  - **consumer_key**
  - **consumer_secret**

Additionally you can configure parameters / filters for each stream. For example for "favorites": 

```
  "favorites":{
    "user_id":"",
    "screen_name":"",
    "count":"10",
    "max_id":"",
    "include_entities":"True"
  },
```

### Step 3: Select Stream

In *configs/config.json*, enter the *stream* to use. This value corresponds to one of 13 available streams: 

  1.  blocks
  - favorites
  - followers
  - friends
  - home_timeline
  - lists
  - memberships
  - mentions
  - replies
  - retweets_of_me 
  - subscriptions
  - user_retweets
  - user_timeline

For example, to get a list of mentions: 

``` "stream": "mentions",```

### Step 4: Run Twitter Tap (1st time)

It is necessary to setup Twitter credentials when running this Tap for the first time (i.e. access token). Once credentials are setup, it can be reused in subsequent requests. Credentials are stored in ~/.credentials/twitter.json

Run: ```tap-twitter -c configs/config.json``` without piping to a target. You will be prompted to authorize Twitter: 

> Go to the following link in your browser:

> https://api.twitter.com/oauth/authorize?oauth_token=CF3m3QAAAAAA3DfFAAABYAzeLmo

> Have you authorized me? (y/n) 0768235

> What is the PIN? 0768235

> Access Token:

> oauth_token = 16900279-b9uN27YEtYdHsrFOd932wGrFzYwBXbcOpRwNfrOQW
> oauth_token_secret = FirCxFzLdD1oyL3KRKorMvf4wzjmcSG41VSG3Kudxrt1P

> You may now access protected resources using the access tokens above. 


Now you can pipe twitter results to a Singer Target e.g.

``` tap-twitter -c configs/config.json -s state.json | target-gsheet -c gsheet.config.json```

Please fav my Tap! Appreciate feedback if you are using this Tap, thanks!

### Credits

* [Python Twitter](https://github.com/bear/python-twitter) by the Python-Twitter Developers


Copyright 2017 [Bernard Tai](http://bernardtai.net)
