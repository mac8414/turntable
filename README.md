# Contributers

McKay Hunter, Rasim Crnica, Zach Ainge, Dallin Munger

Start Date: March 25th, 2025

End of Version 2 production: July 26th, 2025

# Turntable

This project is a simple website that helps people expand their music taste. This website uses CadenceAI, an AI we built, to find recommendations based on the input song from the user. We added picks of the week to the project that the
users can view from previous weeks. We also kept hommage to the randomizer from V1 by adding nobs to the interface for the user to find 5 recommendations for a random song.

## Table of Contents

- [About](#about)
- [Features](#features)

---

## About

We created this project to help music goers find new albums to listen to.
This is mainly for anyone looking to expand what their taste in music is.
We think it has easy functionality and is fun for anyone to use.

## Features

- A search bar implemented for a user to enter in a song. That then finds 1-10 recommended songs based on how the input song sounds.
- Time Frame and Genre knobs that filter the recommendations (drag, click, or use the arrow keys).
- A Randomize button that picks a random song to get recommendations for.
- A list of previous album recommendations we used as our picks of the week.

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd app && python3 -m flask run
```

Create a `.env` file in the project root:

```
LASTFM_API_KEY=...
LASTFM_API_SECRET=...
RECAPTCHA_SITE_KEY=...
RECAPTCHA_SECRET_KEY=...
MAIL_PASSWORD=...        # Gmail app password for turntablehelp@gmail.com
SECRET_KEY=...           # any long random string
```

Run the tests with `pip install -r requirements-dev.txt && python3 -m pytest tests`.

## How CadenceAI works

CadenceAI is a hybrid: it finds candidates two ways and scores them all on sound plus listener context.

1. **Find the song** on Deezer (the exact track the user clicked) and analyze its preview.
2. **Ask listeners** (Last.fm): tracks similar listeners play, top tracks from similar artists, and a few from the same artist. Each gets a *context score* from Last.fm's match rating.
3. **Ask the sound** (the song catalog): the ~40 songs whose audio is closest to the seed, by artists other than the seed's. This is how it finds artists Last.fm wouldn't suggest.
4. **Filter** out the song itself, live/remix versions and duplicates (including "A & B" vs "B & A" credits), then apply the Genre (Last.fm artist tags) and Time Frame (Deezer release year) knobs.
5. **Score** everything: 65% how close it sounds to the seed, 35% how related listeners consider it. Catalog finds earn context when their artist is among the seed artist's similar artists.
6. **Diversify** so the results show at most one song per artist when possible. Each result is labeled *Fans also play* or *Sounds similar* depending on how it was found.

**Listening** uses [Discogs-EffNet](https://essentia.upf.edu/models.html), a model trained to recognize ~400 music styles, which turns the middle 15 seconds of a preview into 1280 numbers describing how it sounds. It replaced the earlier hand-built librosa features after scoring about 3x better in `experiments/`. Four songs are packed into each model run, about 0.1s per song.

**The song catalog** (`app/data`) stores every song analyzed so far, so no song is analyzed twice and repeat searches take about a second. Start it from Last.fm's genre charts with:

```bash
cd app && python build_catalog.py      # ~2,000 songs, about 15 minutes; safe to rerun
```

The model (18 MB) downloads automatically to `app/models` on first run. Without a catalog the app still works, but only re-ranks Last.fm's suggestions.
