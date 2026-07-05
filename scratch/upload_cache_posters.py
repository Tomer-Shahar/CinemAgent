import os
import json
import base64
import re
import supabase
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get('SUPABASE_PROJECT_URL')
key = os.environ.get('SUPABASE_KEY')
client = supabase.create_client(url, key)

def slugify(s_title):
    return re.sub(r'[^a-z0-9]+', '-', s_title.lower()).strip('-')

with open('src/output/imdb_cache.json', 'r', encoding='utf-8') as f:
    cache = json.load(f)

uploaded = 0
for title, data in cache.items():
    poster_val = data.get('poster_url', '')
    if poster_val.startswith('data:image'):
        header, encoded = poster_val.split(',', 1)
        ext = header.split(';')[0].split('/')[1] if '/' in header else 'jpg'
        if ext == 'jpeg': ext = 'jpg'
        
        image_data = base64.b64decode(encoded)
        title_slug = slugify(title)
        file_name = f"{title_slug}.{ext}"
        
        try:
            res = client.storage.from_('posters').upload(
                file_name,
                image_data,
                {"content-type": f"image/{ext}", "upsert": "true"}
            )
            print(f"Uploaded: {file_name}")
            uploaded += 1
        except Exception as e:
            print(f"Skipped/Error for {file_name}: {e}")

print(f"Total uploaded: {uploaded}")
