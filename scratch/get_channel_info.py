import urllib.request
import re

url = 'https://www.youtube.com/channel/UC3cuNGcJ39dJ1IbEmIxllfQ'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
    match = re.search(r'<title>(.*?)</title>', html)
    if match:
        print('Canal YouTube:', match.group(1))
    match_handle = re.search(r'"canonicalBaseUrl":"(.*?)"', html)
    if match_handle:
        print('Handle YouTube:', match_handle.group(1))
except Exception as e:
    print('Erro:', e)
