# tap-twitter

Thank you for using my Singer Twitter Tap.

This tap: 

- Outputs [count] records from a selection of Twitter *streams*
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
- Outputs *schema* for each selected Twitter stream
- Outputs *state* data. *since_id* can be used to perform delta requests on selected Twitter streams

### Install

```pip install tap-twitter```

### Step 1: Create a Twitter App

You require a Twitter developer account. Visit [Twitter Apps](https://apps.twitter.com)

### Step 2: Configure stream and parameters

Once you have setup a Twitter App, provide requires details in *tap-twitter/config.json*. 

  - **start_date** (Optional). Not used in Twitter API queries, leave as "1971-01-01 00:00:00"
  - **consumer_key** - See your Twitter App setup. 
  - **consumer_secret** - See your Twitter App setup. 
  - **count** - number of records to retrieve. Applies to all streams. Default 10

Do not edit *request_token_url*, *access_token_url*, *authorize_url*

### Step 3: Select Stream(s)

To query 1 or more of the following Twitter streams, in *tap-twitter/catalog.json*, set its "schema" > "selected" value to "True". 

  1. Blocks 
  1. Favorites
  1. Followers
  1. Friends
  1. Home_timeline (by default, selected=True)
  1. Lists
  1. Memberships
  1. Mentions
  1. Replies
  1. Retweets_of_me 
  1. Subscriptions
  1. User_retweets
  1. User_timeline

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

When running tap for the first time, it is necessary to setup Twitter *credentials*. Once credentials are setup, it can be reused in subsequent requests. Credentials are stored in ~/.credentials/twitter.json

Run: ```tap-twitter -c tap-twitter/config.json``` without piping to a target. You will be prompted to authorize Twitter: 

> Go to the following link in your browser:
> https://api.twitter.com/oauth/authorize?oauth_token=CF3m3QAAAAAA3DfFAAABYAzeLmo
> Have you authorized me? (y/n) 0768235
> What is the PIN? 0768235
> Access Token:
> oauth_token = 16900279-b9uN27YEtYdHsrFOd932wGrFzYwBXbcOpRwNfrOQw
> oauth_token_secret = FirCxFzLdD1oyL3KRKorMvf4wzjmcSG41VSG3Kudxrt1p
> You may now access protected resources using the access tokens above. 

Now you can pipe stream results to a Singer Target e.g.

``` tap-twitter -c tap-twitter/config.json -s tap-twitter/state.json | target-gsheet -c gsheet.config.json```

### Step 5: Use tap-twitter/state.json to filter results since *since_id*

```
{
  "bookmarks": {
    "favorites" : {
      "since_id":0
    },
    "home_timeline" : {
      "since_id":0
    },
    "mentions" : {
      "since_id":0
    }
  }
}
```

## Before you go...

This tap was developed with Python 3.5. Tested on Singer Docker image singerio/singer-base:0.0.1. 

Let me know if you encounter issues using this Tap. Appreciate your feedback! Please raise issues in Github Twitter Tap repo. I will attempt to resolve where possible, and of course appreciate assistance from the greater Singer community. Fork away. 

Please fav my Tap repo! Appreciate feedback if you are using this Tap, thanks.

### Credits

* [Python Twitter](https://github.com/bear/python-twitter) by Python-Twitter Developers

Copyright 2018 [Bernard Tai](http://bernardtai.net)
