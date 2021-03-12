# Parse Comments from Youtube Videos

This script will dump youtube video comments to a CSV from youtube video links. Video links can be placed inside a variable or list or CSV

The script is based on [youtube-comment-downloader](https://github.com/egbertbouman/youtube-comment-downloader)

It requires **pandas**, **lxml** and **requests** modules

To run

`pip install -r requirements.txt`

`python ytb_comment_scraper.py`

The comments will be dump to a CSV file titled **'ytb_comments.csv'**
