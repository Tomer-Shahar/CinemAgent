import os
import json
import re
import supabase
from dotenv import load_dotenv

load_dotenv()
client = supabase.create_client(os.environ['SUPABASE_PROJECT_URL'], os.environ['SUPABASE_KEY'])

def slugify(s_title):
    return re.sub(r'[^a-z0-9]+', '-', s_title.lower()).strip('-')

with open('src/output/imdb_cache.json', 'r', encoding='utf-8') as f:
    cache = json.load(f)

for title, data in cache.items():
    poster_val = data.get('poster_url', '')
    if poster_val.startswith('data:image'):
        header, encoded = poster_val.split(',', 1)
        ext = header.split(';')[0].split('/')[1] if '/' in header else 'jpg'
        if ext == 'jpeg': ext = 'jpg'
        
        file_name = f"{slugify(title)}.{ext}"
        public_url = client.storage.from_("posters").get_public_url(file_name)
        
        # update DB where title is this
        client.table('screenings').update({'poster_url': public_url}).eq('title', title).execute()
        print(f"Updated DB for {title}")
