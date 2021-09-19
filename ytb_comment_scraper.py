"""
By Ahmed Shahriar Sakib
GitHub : https://github.com/ahmedshahriar

The script is based on https://github.com/egbertbouman/youtube-comment-downloader

By default, the script will download most recent 100 comments
You can change the default filter (line 33 onwards)
Variables :
COMMENT_LIMIT : How many comments you want to download 
SORT_BY_POPULAR : filter comments by popularity (0 for True , 1 for false)
SORT_BY_RECENT : filter comments by recently posted (0 for True , 1 for false)
"""

import pandas as pd
import json
import os
import sys
import re
import time

import requests

# pandas dataframe display configuration
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

YOUTUBE_COMMENTS_AJAX_URL = 'https://www.youtube.com/comment_service_ajax'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'
# csv file name
FILE_NAME = 'ytb_comments.csv'

# set parameters
# filter comments by popularity or recent, 0:False, 1:True
SORT_BY_POPULAR = 0
# default recent
SORT_BY_RECENT = 1
# set comment limit
COMMENT_LIMIT = 100

YT_CFG_RE = r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;'
YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;\s*(?:var\s+meta|</script|\n)'


def regex_search(text, pattern, group=1, default=None):
    match = re.search(pattern, text)
    return match.group(group) if match else default


def ajax_request(session, endpoint, ytcfg, retries=5, sleep=20):
    url = 'https://www.youtube.com' + endpoint['commandMetadata']['webCommandMetadata']['apiUrl']

    data = {'context': ytcfg['INNERTUBE_CONTEXT'],
            'continuation': endpoint['continuationCommand']['token']}

    for _ in range(retries):
        response = session.post(url, params={'key': ytcfg['INNERTUBE_API_KEY']}, json=data)
        if response.status_code == 200:
            return response.json()
        if response.status_code in [403, 413]:
            return {}
        else:
            time.sleep(sleep)


def download_comments(YOUTUBE_VIDEO_URL, sort_by=SORT_BY_RECENT, language=None, sleep=0.1):
    session = requests.Session()
    session.headers['User-Agent'] = USER_AGENT
    response = session.get(YOUTUBE_VIDEO_URL)

    if 'uxe=' in response.request.url:
        session.cookies.set('CONSENT', 'YES+cb', domain='.youtube.com')
        response = session.get(YOUTUBE_VIDEO_URL)

    html = response.text
    ytcfg = json.loads(regex_search(html, YT_CFG_RE, default=''))
    if not ytcfg:
        return  # Unable to extract configuration
    if language:
        ytcfg['INNERTUBE_CONTEXT']['client']['hl'] = language

    data = json.loads(regex_search(html, YT_INITIAL_DATA_RE, default=''))

    section = next(search_dict(data, 'itemSectionRenderer'), None)
    renderer = next(search_dict(section, 'continuationItemRenderer'), None) if section else None
    if not renderer:
        # Comments disabled?
        return

    needs_sorting = sort_by != SORT_BY_POPULAR
    continuations = [renderer['continuationEndpoint']]
    while continuations:
        continuation = continuations.pop()
        response = ajax_request(session, continuation, ytcfg)

        if not response:
            break
        if list(search_dict(response, 'externalErrorMessage')):
            raise RuntimeError('Error returned from server: ' + next(search_dict(response, 'externalErrorMessage')))

        if needs_sorting:
            sort_menu = next(search_dict(response, 'sortFilterSubMenuRenderer'), {}).get('subMenuItems', [])
            if sort_by < len(sort_menu):
                continuations = [sort_menu[sort_by]['serviceEndpoint']]
                needs_sorting = False
                continue
            raise RuntimeError('Failed to set sorting')

        actions = list(search_dict(response, 'reloadContinuationItemsCommand')) + \
                  list(search_dict(response, 'appendContinuationItemsAction'))
        for action in actions:
            for item in action.get('continuationItems', []):
                if action['targetId'] == 'comments-section':
                    # Process continuations for comments and replies.
                    continuations[:0] = [ep for ep in search_dict(item, 'continuationEndpoint')]
                if action['targetId'].startswith('comment-replies-item') and 'continuationItemRenderer' in item:
                    # Process the 'Show more replies' button
                    continuations.append(next(search_dict(item, 'buttonRenderer'))['command'])

        for comment in reversed(list(search_dict(response, 'commentRenderer'))):
            yield {'cid': comment['commentId'],
                   'text': ''.join([c['text'] for c in comment['contentText'].get('runs', [])]),
                   'time': comment['publishedTimeText']['runs'][0]['text'],
                   'author': comment.get('authorText', {}).get('simpleText', ''),
                   'channel': comment['authorEndpoint']['browseEndpoint'].get('browseId', ''),
                   'votes': comment.get('voteCount', {}).get('simpleText', '0'),
                   'photo': comment['authorThumbnail']['thumbnails'][-1]['url'],
                   'heart': next(search_dict(comment, 'isHearted'), False)}

        time.sleep(sleep)


def search_dict(partial, search_key):
    stack = [partial]
    while stack:
        current_item = stack.pop()
        if isinstance(current_item, dict):
            for key, value in current_item.items():
                if key == search_key:
                    yield value
                else:
                    stack.append(value)
        elif isinstance(current_item, list):
            for value in current_item:
                stack.append(value)


def main(url):
    df_comment = pd.DataFrame()
    try:
        youtube_url = url
        limit = COMMENT_LIMIT

        print('Downloading Youtube comments for video:', youtube_url)

        count = 0

        start_time = time.time()

        for comment in download_comments(youtube_url):

            df_comment = df_comment.append(comment, ignore_index=True)

            # comments overview
            comment_json = json.dumps(comment, ensure_ascii=False)
            print(comment_json)

            count += 1

            if limit and count >= limit:
                break

        print("DataFrame Shape: ", df_comment.shape, "\nComment DataFrame: ", df_comment)

        if not os.path.isfile(FILE_NAME):
            df_comment.to_csv(FILE_NAME, encoding='utf-8', index=False)
        else:  # else it exists so append without writing the header
            df_comment.to_csv(FILE_NAME, mode='a', encoding='utf-8', index=False, header=False)

        print('\n[{:.2f} seconds] Done!'.format(time.time() - start_time))

    except Exception as e:
        print('Error:', str(e))
        sys.exit(1)

    # dumping youtube comments


""" 
1. Dump comments to a csv  from a single video

"""
# youtube_URL = 'https://www.youtube.com/watch?v=fucUDHaZ0Ug'
# main(youtube_URL)

"""
2. Dump comments to a csv by parsing links from a csv with video links

Example -
Create a csv with one column titled 'link'
a sample is given below

'ytb_video_list.csv'

link
https://www.youtube.com/watch?v=-t_uhBBDbA4
https://www.youtube.com/watch?v=75vjjRza7IU
https://www.youtube.com/watch?v=j6dmaPzOBHY
https://www.youtube.com/watch?v=Yj2efyQV1RI
https://www.youtube.com/watch?v=HV652F7U6Qs
https://www.youtube.com/watch?v=47iXEucg3eo
https://www.youtube.com/watch?v=ofHXBLEE3TQ
https://www.youtube.com/watch?v=X6lGqSfVRT8
https://www.youtube.com/watch?v=a_-z9FhGBrE
https://www.youtube.com/watch?v=wTUM_4cVlE4


"""
# df_video_list = pd.read_csv('ytb_video_list.csv')
# print(df_video_list['link'].map(lambda x: main(x)))
# print(main(pd.read_csv('ytb_video_list.csv')['link']))


"""
3. Dump to a csv from a a list with video links
"""
ytb_video_list = ['https://www.youtube.com/watch?v=-t_uhBBDbA4',
                  'https://www.youtube.com/watch?v=75vjjRza7IU',
                  'https://www.youtube.com/watch?v=j6dmaPzOBHY',
                  'https://www.youtube.com/watch?v=Yj2efyQV1RI']

for video_link in ytb_video_list:
    main(video_link)