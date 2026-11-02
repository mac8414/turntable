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

1. **Find the song** on Deezer (using the exact track the user clicked) and download its 30 second preview.
2. **Gather candidates** from Last.fm: tracks similar listeners play, top tracks from similar artists, and a few from the same artist. Each gets a *context score* from Last.fm's match rating.
3. **Filter** out the song itself, live/remix/acoustic versions and duplicates, then apply the Genre (Last.fm artist tags) and Time Frame (Deezer release date) knobs.
4. **Analyze audio** for the most related ~30 candidates with librosa: timbre (MFCCs), spectral texture, energy and dynamics, tempo, harmony (chroma) and key.
5. **Score** each candidate. Audio features are scaled across the candidate pool so no single feature dominates, tempo is compared with half/double-time treated as close, and keys are compared on the circle of fifths. The final match is 65% audio similarity and 35% context score.
6. **Diversify** so the results show at most one song per artist when possible.

Deezer and Last.fm results and audio features are cached in memory, so repeat searches are fast.
