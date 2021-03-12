import pandas as pd
import json
import sys
import time
import requests

pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

YOUTUBE_COMMENTS_AJAX_URL = 'https://www.youtube.com/comment_service_ajax'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'

SORT_BY_POPULAR = 0
SORT_BY_RECENT = 1

FILE_NAME = 'ytb_comments.csv'


def find_value(html, key, num_chars=2, separator='"'):
    pos_begin = html.find(key) + len(key) + num_chars
    pos_end = html.find(separator, pos_begin)
    return html[pos_begin: pos_end]


def ajax_request(session, url, params=None, data=None, headers=None, retries=5, sleep=20):
    for _ in range(retries):
        response = session.post(url, params=params, data=data, headers=headers)
        if response.status_code == 200:
            return response.json()
        if response.status_code in [403, 413]:
            return {}
        else:
            time.sleep(sleep)


def download_comments(youtube_video_url, sort_by=SORT_BY_RECENT, sleep=.1):
    session = requests.Session()
    session.headers['User-Agent'] = USER_AGENT

    response = session.get(youtube_video_url)
    html = response.text
    session_token = find_value(html, 'XSRF_TOKEN', 3)
    session_token = session_token.encode('ascii').decode('unicode-escape')

    data = json.loads(find_value(html, 'var ytInitialData = ', 0, '};') + '}')
    for renderer in search_dict(data, 'itemSectionRenderer'):
        ncd = next(search_dict(renderer, 'nextContinuationData'), None)
        if ncd:
            break

    if not ncd:
        # Comments disabled?
        return

    needs_sorting = sort_by != SORT_BY_POPULAR
    continuations = [(ncd['continuation'], ncd['clickTrackingParams'], 'action_get_comments')]
    while continuations:
        continuation, itct, action = continuations.pop()
        response = ajax_request(session, YOUTUBE_COMMENTS_AJAX_URL,
                                params={action: 1,
                                        'pbj': 1,
                                        'ctoken': continuation,
                                        'continuation': continuation,
                                        'itct': itct},
                                data={'session_token': session_token},
                                headers={'X-YouTube-Client-Name': '1',
                                         'X-YouTube-Client-Version': '2.20201202.06.01'})

        if not response:
            break
        if list(search_dict(response, 'externalErrorMessage')):
            raise RuntimeError('Error returned from server: ' + next(search_dict(response, 'externalErrorMessage')))

        if needs_sorting:
            sort_menu = next(search_dict(response, 'sortFilterSubMenuRenderer'), {}).get('subMenuItems', [])
            if sort_by < len(sort_menu):
                ncd = sort_menu[sort_by]['continuation']['reloadContinuationData']
                continuations = [(ncd['continuation'], ncd['clickTrackingParams'], 'action_get_comments')]
                needs_sorting = False
                continue
            raise RuntimeError('Failed to set sorting')

        if action == 'action_get_comments':
            section = next(search_dict(response, 'itemSectionContinuation'), {})
            for continuation in section.get('continuations', []):
                ncd = continuation['nextContinuationData']
                continuations.append((ncd['continuation'], ncd['clickTrackingParams'], 'action_get_comments'))
            for item in section.get('contents', []):
                continuations.extend([(ncd['continuation'], ncd['clickTrackingParams'], 'action_get_comment_replies')
                                      for ncd in search_dict(item, 'nextContinuationData')])

        elif action == 'action_get_comment_replies':
            continuations.extend([(ncd['continuation'], ncd['clickTrackingParams'], 'action_get_comment_replies')
                                  for ncd in search_dict(response, 'nextContinuationData')])

        for comment in search_dict(response, 'commentRenderer'):
            yield {'cid': comment['commentId'],
                   'text': ''.join([c['text'] for c in comment['contentText']['runs']]),
                   'time': comment['publishedTimeText']['runs'][0]['text'],
                   'author': comment.get('authorText', {}).get('simpleText', ''),
                   'channel': comment['authorEndpoint']['browseEndpoint']['browseId'],
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
        limit = 100
        comment_df = pd.DataFrame()

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

        print(df_comment.shape, df_comment)

        # dump to a csv file
        df_comment.to_csv(FILE_NAME, encoding='utf-8')
        print('\n[{:.2f} seconds] Done!'.format(time.time() - start_time))

    except Exception as e:
        print('Error:', str(e))
        sys.exit(1)


youtube_URL = 'https://www.youtube.com/watch?v=Ucbrmw2qtXs'

main(youtube_URL)
