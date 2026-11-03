"""
Build or grow the song catalog the recommender searches for sound-alikes.

Takes Last.fm's top tracks for a spread of genre tags, finds them on Deezer and analyzes their
previews with Discogs-EffNet. Songs already in the catalog are skipped, so it's safe to rerun.
The app also adds every song it analyzes while recommending, so the catalog grows with use.

Run from the app directory:  python build_catalog.py [tracks per tag, default 50]
"""
import sys
import time

from crud import MusicRecommender, Track

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


def main(tracks_per_tag: int = 50):
    recommender = MusicRecommender()
    catalog = recommender.catalog
    starting_size = len(catalog)
    start = time.time()

    for tag in TAGS:
        top_tracks = recommender.lastfm_client.get_tag_top_tracks(tag, tracks_per_tag)
        new = [Track(id=0, title=title, artist_name=artist)
               for title, artist in top_tracks if not catalog.find(title, artist)]
        recommender.embed_tracks([t for t in recommender._resolve_tracks(new) if t.embedding is None])
        catalog.save()
        print(f"{tag:18s} +{len(catalog) - starting_size:5d} songs so far, catalog {len(catalog)}, "
              f"{time.time() - start:.0f}s", flush=True)

    print(f"Done: added {len(catalog) - starting_size} songs, catalog now has {len(catalog)}")


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 50)
