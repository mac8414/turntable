"""
Step 5a: build a catalog of songs embedded with Discogs-EffNet, so recommendations can search
"everything that sounds like this" instead of only reranking Last.fm's shortlist.

Songs come from Last.fm's top tracks for a spread of genre tags. Previews are deleted after
embedding; only metadata and embeddings are kept. Safe to stop and rerun: it resumes.
Run from the project root:  python experiments/catalog_build.py
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from evaluation import CACHE_DIR
from sources import EffnetEmbedder, download, find_on_deezer, lastfm, normalize_artist

TRACKS_PER_TAG = 50
TAGS = [
    'rock', 'classic rock', 'hard rock', 'alternative rock', 'indie rock', 'grunge', 'punk', 'emo', 'shoegaze',
    'metal', 'heavy metal', 'thrash metal', 'death metal',
    'hip-hop', 'rap', 'trap', 'boom bap',
    'electronic', 'house', 'techno', 'ambient', 'drum and bass', 'synthpop', 'disco',
    'jazz', 'bebop', 'smooth jazz',
    'classical', 'piano', 'baroque',
    'country', 'classic country', 'bluegrass',
    'soul', 'rnb', 'funk', 'motown', 'neo-soul',
    'reggae', 'dub', 'ska',
    'folk', 'indie folk', 'singer-songwriter',
    'pop', 'dance', 'blues', 'latin', 'k-pop', 'lo-fi',
]
META_PATH = os.path.join(CACHE_DIR, 'catalog.json')
EMBED_PATH = os.path.join(CACHE_DIR, 'catalog_embeddings.npy')


def gather_candidates():
    seen, candidates = set(), []
    for tag in TAGS:
        tracks = lastfm('tag.getTopTracks', tag=tag, limit=TRACKS_PER_TAG).get('tracks', {}).get('track', [])
        for t in tracks:
            key = (t['name'].lower(), normalize_artist(t['artist']['name']))
            if key not in seen:
                seen.add(key)
                candidates.append({'title': t['name'], 'artist': t['artist']['name'], 'tag': tag})
    return candidates


def main():
    catalog = json.load(open(META_PATH)) if os.path.exists(META_PATH) else []
    embeddings = list(np.load(EMBED_PATH)) if os.path.exists(EMBED_PATH) else []
    done = {(c['title'].lower(), normalize_artist(c['artist'])) for c in catalog}

    candidates = [c for c in gather_candidates()
                  if (c['title'].lower(), normalize_artist(c['artist'])) not in done]
    print(f"{len(catalog)} songs already in catalog, {len(candidates)} to add")

    embedder = EffnetEmbedder()
    start = time.time()

    def fetch(candidate):
        found = find_on_deezer(candidate['title'], candidate['artist'])
        return candidate, found, download(found['preview']) if found else None

    # Deezer lookups and downloads in parallel; the model runs on the main thread
    with ThreadPoolExecutor(max_workers=6) as executor:
        for i, (candidate, found, path) in enumerate(executor.map(fetch, candidates), 1):
            if path:
                try:
                    embeddings.append(embedder.embed_file(path))
                    catalog.append({'title': candidate['title'], 'artist': candidate['artist'], 'tag': candidate['tag'],
                                    'deezer_id': found['deezer_id'], 'cover': found['cover']})
                except Exception as e:
                    print(f"  failed to embed {candidate['title']}: {e}")
                finally:
                    os.remove(path)
            if i % 100 == 0 or i == len(candidates):
                json.dump(catalog, open(META_PATH, 'w'))
                np.save(EMBED_PATH, np.array(embeddings, dtype=np.float32))
                print(f"  {i}/{len(candidates)} processed, catalog size {len(catalog)}, "
                      f"{time.time() - start:.0f}s elapsed", flush=True)

    print(f"Done: {len(catalog)} songs, embeddings {np.array(embeddings).shape}")


if __name__ == '__main__':
    main()
