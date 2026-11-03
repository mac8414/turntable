// --- SHARED HELPERS ---
function escapeHtml(value) {
    const entities = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    return String(value ?? '').replace(/[&<>"']/g, ch => entities[ch]);
}

const PLACEHOLDER_COVER = 'data:image/svg+xml,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">' +
    '<rect width="100" height="100" fill="#2a1a10"/><circle cx="50" cy="50" r="32" fill="#111"/>' +
    '<circle cx="50" cy="50" r="7" fill="#fe9900"/></svg>'
);

// Swap broken or missing album art for a placeholder record
function attachCoverFallbacks(root) {
    root.querySelectorAll('img[data-cover]').forEach(img => {
        img.addEventListener('error', () => { img.src = PLACEHOLDER_COVER; }, { once: true });
    });
}

async function postJson(url, body, signal) {
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal
    });
    let data = null;
    try {
        data = await response.json();
    } catch (e) {
        // Non-JSON error page; handled below
    }
    if (!response.ok) {
        throw new Error((data && data.error) || `Request failed (${response.status})`);
    }
    return data || {};
}

const TIMEFRAMES = ['Any', '60s', '70s', '80s', '90s', '2000s', '2010s', '2020s'];
const GENRES = ['Any', 'Rock', 'Pop', 'Hip-Hop', 'Electronic', 'Jazz', 'Classical', 'R&B', 'Country', 'Metal'];

function readSettings() {
    const timeframeKnob = document.getElementById('timeframeKnob');
    const genreKnob = document.getElementById('genreKnob');
    const slider = document.getElementById('recommendationSlider');
    return {
        timeframe: TIMEFRAMES[Number(timeframeKnob && timeframeKnob.dataset.value) || 0],
        genre: GENRES[Number(genreKnob && genreKnob.dataset.value) || 0],
        count: Number(slider && slider.value) || 5
    };
}

// --- LAVA LAMP ANIMATION ---
function startLavaLamp() {
    const container = document.getElementById('lavaLamp');
    if (!container) return;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // Safari struggles with the SVG goo filter, so animate fewer blobs at half frame rate there
    const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);

    // Starting position as a fraction of the window, horizontal sway speed and phase
    const layout = [
        [0.4, 0.3, 0.3, 0], [0.6, 0.5, 0.4, 1.5], [0.5, 0.7, 0.2, 3], [0.3, 0.4, 0.25, 4.5],
        [0.7, 0.2, 0.35, 6], [0.2, 0.6, 0.15, 7.5], [0.8, 0.3, 0.3, 9], [0.4, 0.8, 0.2, 10.5],
        [0.6, 0.1, 0.25, 12], [0.2, 0.2, 0.15, 13.5]
    ];
    let blobs = layout.map(([x, y, xSpeed, phase], i) => ({
        el: document.getElementById(`blob${i + 1}`),
        x: window.innerWidth * x,
        y: window.innerHeight * y,
        xSpeed,
        phase
    })).filter(blob => blob.el);

    if (isSafari) {
        blobs.slice(6).forEach(blob => { blob.el.style.display = 'none'; });
        blobs = blobs.slice(0, 6);
    }

    function draw(blob) {
        blob.el.setAttribute('cx', blob.x);
        blob.el.setAttribute('cy', blob.y);
    }
    blobs.forEach(draw);
    if (reduceMotion) return;

    let time = 0;
    let frame = 0;
    function step() {
        requestAnimationFrame(step);
        if (isSafari && frame++ % 2) return;
        time += 0.01;
        const minX = -100;
        const maxX = window.innerWidth + 100;
        blobs.forEach(blob => {
            // Slow upward drift like rising wax, with a gentle side-to-side sway
            blob.y -= 0.1;
            blob.x += Math.sin(time * blob.xSpeed + blob.phase);
            if (blob.y < -100) {
                blob.y = window.innerHeight + 100;
                blob.x += (Math.random() - 0.5) * 100;
            }
            blob.x = Math.max(minX, Math.min(maxX, blob.x));
            draw(blob);
        });
    }
    requestAnimationFrame(step);
}

// --- RECORD PLAYER ---
let isPlaying = false;

function setPlaying(playing) {
    isPlaying = playing;
    const record = document.getElementById('record');
    const recordArm = document.getElementById('recordArm');
    if (record) record.classList.toggle('playing', playing);
    if (recordArm) recordArm.style.transform = playing ? 'rotate(-15deg)' : 'rotate(-90deg)';
}

function showOnRecord(song) {
    const albumCover = document.getElementById('albumCover');
    if (albumCover) {
        albumCover.innerHTML = `<img data-cover src="${escapeHtml(song.album_cover || PLACEHOLDER_COVER)}"
            alt="${escapeHtml(song.title)} by ${escapeHtml(song.artist)}">`;
        attachCoverFallbacks(albumCover);
    }
    setPlaying(true);
}

// --- RECOMMENDATIONS ---
let activeRecommendation = null;

// The server doesn't stream progress, so ease the bar toward ~95% while we wait
function createProgress(bar) {
    const fill = bar.querySelector('.progress');
    let current = 0;
    const start = Date.now();
    const set = pct => {
        current = Math.max(0, Math.min(100, pct));
        fill.style.width = current + '%';
        fill.style.opacity = current > 0 ? '1' : '0';
    };
    set(2);
    const interval = setInterval(() => {
        const elapsed = (Date.now() - start) / 1000;
        if (elapsed < 1) {
            set(Math.min(25, current + 8));
        } else {
            set(Math.min(95, current + 0.6 / (1 + elapsed / 6)));
        }
    }, 300);
    return {
        finish() {
            clearInterval(interval);
            set(100);
            setTimeout(() => bar.classList.add('hidden'), 200);
            setTimeout(() => bar.parentNode && bar.parentNode.remove(), 600);
        },
        cancel() {
            clearInterval(interval);
        }
    };
}

function musicLinks(title, artist) {
    const query = encodeURIComponent(`${title} ${artist}`);
    return {
        spotify: `https://open.spotify.com/search/${query}`,
        apple: `https://music.apple.com/us/search?term=${query}`
    };
}

function renderRecommendationItem(rec) {
    const links = musicLinks(rec.title, rec.artist);
    const year = rec.release_year ? ` · ${escapeHtml(rec.release_year)}` : '';
    const cover = escapeHtml(rec.album_cover || PLACEHOLDER_COVER);
    return `
        <li class="recommendation-item">
            <div class="recommendation-bg" style="background-image: url('${cover}')"></div>
            <div class="recommendation-cover">
                <img data-cover src="${cover}" alt="${escapeHtml(rec.title)} album cover" loading="lazy">
            </div>
            <div class="recommendation-info">
                <h4 class="recommendation-title">${escapeHtml(rec.title)}</h4>
                <p class="recommendation-artist">${escapeHtml(rec.artist)}${year}</p>
            </div>
            <div class="recommendation-right">
                <div class="recommendation-match">${escapeHtml(rec.similarity_score || 0)}% match</div>
                <div class="recommendation-source" title="${rec.source === 'sound'
                    ? 'Found by comparing how songs sound'
                    : 'Listeners of this song also play it'}">${rec.source === 'sound' ? 'Sounds similar' : 'Fans also play'}</div>
                <div class="musicLink">
                    <a href="${escapeHtml(links.apple)}" target="_blank" rel="noopener noreferrer">Listen on Apple Music</a>
                </div>
                <div class="musicLink">
                    <a href="${escapeHtml(links.spotify)}" target="_blank" rel="noopener noreferrer">Listen on Spotify</a>
                </div>
            </div>
        </li>
    `;
}

function loadArtistFact(artist, factElem, signal) {
    postJson('/api/artist-info', { artist_name: artist }, signal)
        .then(data => {
            const info = data.artist_info || {};
            if (!info.bio) {
                factElem.textContent = 'No artist fact found.';
                return;
            }
            factElem.className = 'artist-fact';
            factElem.innerHTML = `<strong>About ${escapeHtml(artist)}:</strong> ${escapeHtml(info.bio)}`;
            if (info.tags && info.tags.length) {
                factElem.innerHTML += `<br><span class="artist-tags">${info.tags.map(escapeHtml).join(' · ')}</span>`;
            }
        })
        .catch(error => {
            if (error.name === 'AbortError') return;
            factElem.textContent = 'No artist fact found.';
        });
}

function loadRecommendations(song) {
    const recommendationBox = document.querySelector('.recommendationBox');
    if (!recommendationBox) return;

    // Only the most recent selection should update the page
    if (activeRecommendation) activeRecommendation.abort();
    const controller = new AbortController();
    activeRecommendation = controller;

    const { timeframe, genre, count } = readSettings();
    const filters = `Time Frame: ${escapeHtml(timeframe)} | Genre: ${escapeHtml(genre)}`;

    recommendationBox.innerHTML = `
        <div class="recommendations-show" aria-live="polite">
            <h3 class="recommendations-heading">Finding ${escapeHtml(count)} songs like ${escapeHtml(song.title)} by ${escapeHtml(song.artist)}...</h3>
            <div class="loading-bar-container">
                <div class="loading-bar"><div class="progress"></div></div>
            </div>
            <p>${filters}</p>
            <h5>Powered by <strong>CadenceAI</strong></h5>
            <div class="recommendation-notices"></div>
            <div class="artist-fact-container">
                <p class="artist-fact-loading">Loading artist fact...</p>
            </div>
        </div>
        <ul class="recommendation-list"></ul>
    `;

    const heading = recommendationBox.querySelector('.recommendations-heading');
    const notices = recommendationBox.querySelector('.recommendation-notices');
    const list = recommendationBox.querySelector('.recommendation-list');
    const progress = createProgress(recommendationBox.querySelector('.loading-bar'));

    loadArtistFact(song.artist, recommendationBox.querySelector('.artist-fact-loading'), controller.signal);

    postJson('/api/recommend', {
        track_id: song.id,
        track_name: song.title,
        artist_name: song.artist,
        timeframe: timeframe === 'Any' ? '' : timeframe,
        genre: genre === 'Any' ? '' : genre,
        count
    }, controller.signal)
        .then(data => {
            progress.finish();
            const recs = data.recommendations || [];
            heading.textContent = `Top results for ${song.title} by ${song.artist}`;
            notices.innerHTML = (data.notices || [])
                .map(notice => `<p class="recommendation-notice">${escapeHtml(notice)}</p>`)
                .join('');
            list.innerHTML = recs.length
                ? recs.map(renderRecommendationItem).join('')
                : '<li class="recommendation-item recommendation-empty">No recommendations found. Try another song or set the knobs to Any.</li>';
            attachCoverFallbacks(list);
        })
        .catch(error => {
            if (error.name === 'AbortError') {
                progress.cancel();
                return;
            }
            progress.finish();
            heading.textContent = error instanceof TypeError
                ? "Couldn't reach the server"
                : 'Error loading recommendations';
            notices.innerHTML = `<p class="recommendation-notice">${escapeHtml(error.message || 'Please try again.')}</p>`;
            console.error('Error fetching recommendations:', error);
        });
}

function selectSong(song) {
    const searchInput = document.getElementById('songSearch');
    if (searchInput) {
        searchInput.value = `${song.title} - ${song.artist}`;
        searchInput.dispatchEvent(new Event('value-set'));
    }
    showOnRecord(song);
    loadRecommendations(song);
}

// --- RANDOMIZER ---
const RANDOM_SEARCH_TERMS = [
    'love', 'heart', 'night', 'dream', 'fire', 'rock', 'dance', 'soul', 'blue', 'gold',
    'time', 'life', 'free', 'high', 'run', 'fly', 'star', 'sun', 'moon', 'home',
    'world', 'way', 'light', 'dark', 'wind', 'rain', 'day', 'gone', 'stay', 'move'
];

function randomizeSelection() {
    const button = document.querySelector('.randomize-button');
    if (!button || button.disabled) return;

    button.disabled = true;
    button.textContent = 'Loading...';

    const randomTerm = RANDOM_SEARCH_TERMS[Math.floor(Math.random() * RANDOM_SEARCH_TERMS.length)];
    postJson('/api/search', { query: randomTerm, limit: 25 })
        .then(data => {
            const results = data.results || [];
            if (results.length) {
                selectSong(results[Math.floor(Math.random() * results.length)]);
            }
        })
        .catch(error => console.error('Error searching for random song:', error))
        .finally(() => {
            button.disabled = false;
            button.textContent = 'Randomize';
        });
}

// --- KNOBS ---
function setupKnob(knob, valueDisplay, options, label) {
    if (!knob || !valueDisplay) return;

    const maxIndex = options.length - 1;
    const step = 270 / maxIndex;
    const rotationFor = index => index * step - 135;
    let rotation = rotationFor(Number(knob.dataset.value) || 0);

    knob.tabIndex = 0;
    knob.setAttribute('role', 'slider');
    knob.setAttribute('aria-label', label);
    knob.setAttribute('aria-valuemin', '0');
    knob.setAttribute('aria-valuemax', String(maxIndex));

    function setValue(index, snapRotation = true) {
        index = Math.max(0, Math.min(maxIndex, Math.round(index)));
        knob.dataset.value = index;
        valueDisplay.textContent = options[index];
        knob.setAttribute('aria-valuenow', String(index));
        knob.setAttribute('aria-valuetext', options[index]);
        if (snapRotation) rotation = rotationFor(index);
        knob.style.transform = `rotate(${rotationFor(index)}deg)`;
    }
    setValue(Number(knob.dataset.value) || 0);

    function pointerAngle(e, center) {
        return Math.atan2(e.clientY - center.y, e.clientX - center.x) * 180 / Math.PI;
    }

    let drag = null;
    knob.addEventListener('pointerdown', e => {
        e.preventDefault();
        knob.focus();
        knob.setPointerCapture(e.pointerId);
        const rect = knob.getBoundingClientRect();
        const center = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        drag = { center, lastAngle: pointerAngle(e, center), moved: 0 };
        knob.classList.add('knob-active');
    });

    knob.addEventListener('pointermove', e => {
        if (!drag) return;
        const angle = pointerAngle(e, drag.center);
        // Accumulate small deltas so dragging past the 180° seam doesn't jump
        let delta = angle - drag.lastAngle;
        if (delta > 180) delta -= 360;
        if (delta < -180) delta += 360;
        drag.lastAngle = angle;
        drag.moved += Math.abs(delta);
        rotation = Math.max(-135, Math.min(135, rotation + delta));
        setValue((rotation + 135) / step, false);
    });

    function endDrag(e) {
        if (!drag) return;
        // A press without much movement acts as a click: right half steps up, left half steps down
        if (e.type === 'pointerup' && drag.moved < 4) {
            const current = Number(knob.dataset.value) || 0;
            setValue(e.clientX > drag.center.x ? current + 1 : current - 1);
        } else {
            setValue(Number(knob.dataset.value) || 0);
        }
        drag = null;
        knob.classList.remove('knob-active');
    }
    knob.addEventListener('pointerup', endDrag);
    knob.addEventListener('pointercancel', endDrag);

    knob.addEventListener('keydown', e => {
        const current = Number(knob.dataset.value) || 0;
        const keyMap = { ArrowRight: current + 1, ArrowUp: current + 1, ArrowLeft: current - 1, ArrowDown: current - 1, Home: 0, End: maxIndex };
        if (e.key in keyMap) {
            e.preventDefault();
            setValue(keyMap[e.key]);
        }
    });
}

// --- SEARCH ---
function setupSearch() {
    const searchInput = document.getElementById('songSearch');
    const searchResults = document.getElementById('searchResults');
    const clearBtn = document.getElementById('clearSearch');
    if (!searchInput || !searchResults) return;

    let typingTimer;
    let searchController = null;
    let activeIndex = -1;

    searchInput.setAttribute('role', 'combobox');
    searchInput.setAttribute('aria-autocomplete', 'list');
    searchInput.setAttribute('aria-controls', 'searchResults');
    searchResults.setAttribute('role', 'listbox');

    function showResults(show) {
        searchResults.style.display = show ? 'block' : 'none';
        searchInput.setAttribute('aria-expanded', String(show));
    }

    function showMessage(message) {
        searchResults.innerHTML = `<div class="searchResultItem searchResultMessage"><div class="searchResultItem-content"><p class="searching-message">${escapeHtml(message)}</p></div></div>`;
        activeIndex = -1;
        showResults(true);
    }

    function resultItems() {
        return Array.from(searchResults.querySelectorAll('.searchResultItem[data-index]'));
    }

    function setActive(index) {
        const items = resultItems();
        if (!items.length) return;
        activeIndex = (index + items.length) % items.length;
        items.forEach((item, i) => {
            item.classList.toggle('active', i === activeIndex);
            item.setAttribute('aria-selected', String(i === activeIndex));
        });
        items[activeIndex].scrollIntoView({ block: 'nearest' });
    }

    function renderResults(tracks) {
        searchResults.innerHTML = '';
        activeIndex = -1;
        tracks.forEach((track, index) => {
            const item = document.createElement('div');
            item.className = 'searchResultItem';
            item.dataset.index = index;
            item.setAttribute('role', 'option');
            item.innerHTML = `
                <div class="searchResultItem-bg" style="background-image: url('${escapeHtml(track.album_cover || '')}')"></div>
                <div class="searchResultItem-content">
                    <div class="searchResultItem-artwork">
                        <img data-cover src="${escapeHtml(track.album_cover || PLACEHOLDER_COVER)}" alt="${escapeHtml(track.title)} album cover" loading="lazy">
                    </div>
                    <div class="searchResultItem-info">
                        <p class="searchResultItem-title">${escapeHtml(track.title)}</p>
                        <p class="searchResultItem-artist">${escapeHtml(track.artist)}</p>
                    </div>
                </div>
            `;
            item.addEventListener('click', () => choose(track));
            searchResults.appendChild(item);
        });
        attachCoverFallbacks(searchResults);
        showResults(true);
        searchResults._tracks = tracks;
    }

    function choose(track) {
        showResults(false);
        selectSong(track);
    }

    function runSearch(query) {
        if (searchController) searchController.abort();
        searchController = new AbortController();
        postJson('/api/search', { query, limit: 20 }, searchController.signal)
            .then(data => {
                const results = data.results || [];
                if (results.length) {
                    renderResults(results);
                } else {
                    showMessage('No results found.');
                }
            })
            .catch(error => {
                if (error.name !== 'AbortError') showMessage('Error searching. Try again.');
            });
    }

    function updateClearButton() {
        if (clearBtn) clearBtn.style.display = searchInput.value ? 'block' : 'none';
    }

    searchInput.addEventListener('input', () => {
        clearTimeout(typingTimer);
        updateClearButton();
        const query = searchInput.value.trim();
        if (!query) {
            if (searchController) searchController.abort();
            searchResults.innerHTML = '';
            showResults(false);
            return;
        }
        showMessage('Searching...');
        typingTimer = setTimeout(() => runSearch(query), 350);
    });
    searchInput.addEventListener('value-set', updateClearButton);

    searchInput.addEventListener('keydown', e => {
        const items = resultItems();
        if (e.key === 'ArrowDown' && items.length) {
            e.preventDefault();
            showResults(true);
            setActive(activeIndex + 1);
        } else if (e.key === 'ArrowUp' && items.length) {
            e.preventDefault();
            setActive(activeIndex - 1);
        } else if (e.key === 'Enter' && items.length && searchResults._tracks) {
            e.preventDefault();
            choose(searchResults._tracks[Math.max(activeIndex, 0)]);
        } else if (e.key === 'Escape') {
            showResults(false);
        }
    });

    // Hide results when clicking outside, show them again on focus
    document.addEventListener('click', e => {
        if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) showResults(false);
    });
    searchInput.addEventListener('focus', () => {
        if (searchResults.innerHTML.trim() !== '') showResults(true);
    });

    if (clearBtn) {
        clearBtn.addEventListener('click', e => {
            e.preventDefault();
            searchInput.value = '';
            searchInput.dispatchEvent(new Event('input'));
            searchInput.focus();
        });
    }
}

document.addEventListener('DOMContentLoaded', function () {
    startLavaLamp();
    setupSearch();

    const record = document.getElementById('record');
    if (record) {
        record.style.cursor = 'pointer';
        record.addEventListener('click', () => setPlaying(!isPlaying));
    }

    setupKnob(document.getElementById('timeframeKnob'), document.getElementById('timeframeValue'), TIMEFRAMES, 'Time frame');
    setupKnob(document.getElementById('genreKnob'), document.getElementById('genreValue'), GENRES, 'Genre');

    const slider = document.getElementById('recommendationSlider');
    const sliderValue = document.getElementById('sliderValue');
    if (slider && sliderValue) {
        slider.addEventListener('input', () => { sliderValue.textContent = slider.value; });
    }

    const randomizeBtn = document.querySelector('.randomize-button');
    if (randomizeBtn) randomizeBtn.addEventListener('click', randomizeSelection);

    initializePickOfTheWeek();
});

// --- PICK OF THE WEEK ---
// Add new weeks to the top. The most recent pick is featured automatically.
const PICK_HISTORY = [
    {
        id: "2026-03-23",
        searchQuery: "Jar of Flies Alice in Chains",
        albumTitle: "Jar of Flies",
        artistName: "Alice in Chains",
        weekOf: "March 23, 2026",
        description: "Jar of Flies is the fourth studio album by American rock band Alice in Chains, released in 1994. The album is a departure from the band's heavier sound, featuring a more acoustic and introspective style. With tracks like 'No Excuses,' 'I Stay Away,' and 'Nutshell,' Jar of Flies explores themes of isolation, addiction, and emotional vulnerability. The album received critical acclaim for its raw honesty, haunting melodies, and the band's ability to create a powerful atmosphere with stripped-down arrangements. Jar of Flies remains one of Alice in Chains' most beloved and influential works, showcasing their versatility and depth as musicians."
    },
    {
        id: "2026-03-16",
        searchQuery: "The Wall Pink Floyd", 
        albumTitle: "The Wall",
        artistName: "Pink Floyd",
        weekOf: "March 16, 2026",
        description: "The Wall is the eleventh studio album by English rock band Pink Floyd, released in 1979. The album is a rock opera that tells the story of Pink, a troubled rock star who isolates himself from the world behind a metaphorical wall. With iconic tracks like 'Another Brick in the Wall,' 'Comfortably Numb,' and 'Hey You,' The Wall explores themes of alienation, mental illness, and the impact of war. The album's ambitious concept, innovative production, and powerful performances have made it one of Pink Floyd's most enduring and influential works, solidifying its place as a classic in rock history."
    },
    {
        id: "2026-03-09",
        searchQuery: "Everything Is Love The Carters",
        albumTitle: "Everything Is Love",
        artistName: "The Carters",
        weekOf: "March 9, 2026",
        description: "Everything Is Love is a collaborative studio album by American musical duo The Carters, consisting of Beyoncé and Jay-Z. Released in 2018, the album is a blend of hip-hop, R&B, and soul, showcasing the couple's chemistry and musical synergy. With tracks like 'Apeshit,' 'Summer,' and 'Boss,' Everything Is Love explores themes of love, fame, wealth, and empowerment. The album received critical acclaim for its production, lyricism, and the dynamic performances of both artists, solidifying The Carters' status as one of the most influential power couples in music history."
    },
    {
        id: "2026-03-02",
        searchQuery: "The Art of Loving Olivia Dean",
        albumTitle: "The Art of Loving",
        artistName: "Olivia Dean",
        weekOf: "March 2, 2026",
        description: "The Art of Loving is the debut studio album by British singer-songwriter Olivia Dean, released in 2023. The album is a soulful and introspective exploration of love, relationships, and self-discovery, blending elements of pop, R&B, and jazz. With standout tracks like 'The Hardest Part,' 'Show Me,' and 'The Art of Loving,' the album showcases Dean's powerful vocals, heartfelt lyrics, and sophisticated production. The Art of Loving received critical acclaim for its emotional depth and musicality, establishing Olivia Dean as a rising star in the contemporary music scene."
    },
    {
        id: "2026-02-23",
        searchQuery: "Mellon Collie and the Infinite Sadness Smashing Pumpkins",
        albumTitle: "Mellon Collie and the Infinite Sadness",
        artistName: "Smashing Pumpkins",
        weekOf: "February 23, 2026",
        description: "Mellon Collie and the Infinite Sadness is the third studio album by American alternative rock band The Smashing Pumpkins, released in 1995. The double album is a sprawling, ambitious work that explores a wide range of musical styles and themes, from aggressive rock to delicate ballads. With hits like 'Bullet with Butterfly Wings,' '1979,' and 'Tonight, Tonight,' Mellon Collie showcases the band's ability to blend heavy guitars with orchestral arrangements and introspective lyrics. The album received critical acclaim for its scope and creativity, solidifying The Smashing Pumpkins' place as one of the defining bands of the 90s alternative rock scene."
    },
    {
        id: "2026-02-16",
        searchQuery: "Dookie Green Day",
        albumTitle: "Dookie",
        artistName: "Green Day",
        weekOf: "February 16, 2026",
        description: "Dookie is the third studio album by American punk rock band Green Day, released in 1994. The album is a landmark in the punk rock genre, featuring fast-paced songs with catchy melodies and socially conscious lyrics. With hits like 'Basket Case,' 'When I Come Around,' and 'Longview,' Dookie catapulted Green Day to mainstream success and helped popularize punk rock in the 1990s. The album's raw energy, relatable themes of anxiety and alienation, and memorable hooks have made it a timeless classic that continues to resonate with fans across generations."
    },
    {
        id: "2026-02-09",
        searchQuery: "Transistor 311",
        albumTitle: "Transistor",
        artistName: "311",
        weekOf: "February 9, 2026",
        description: "Transistor is the fourth studio album by American rock band 311, released in 1997. The album is a fusion of rock, reggae, hip-hop, and funk, showcasing the band's eclectic style and musical versatility. With standout tracks like 'Beautiful Disaster, 'Transistor,' and 'Galaxy,' the album features catchy melodies, energetic rhythms, and introspective lyrics that explore themes of self-discovery, unity, and positivity. Transistor received critical acclaim for its innovative sound and remains a fan favorite, solidifying 311's place in the alternative rock scene of the late 90s."
    },
    {
        id: "2026-02-02",
        searchQuery: "Here, My Dear Marvin Gaye",
        albumTitle: "Here, My Dear",
        artistName: "Marvin Gaye",
        weekOf: "February 2, 2026",
        description: "Here, My Dear is the fifteenth studio album by American singer-songwriter Marvin Gaye, released in 1978. The album is a deeply personal and autobiographical work that chronicles Gaye's tumultuous relationship with his first wife, Anna Gordy. With its soulful melodies, introspective lyrics, and innovative production, Here, My Dear stands as a unique and emotionally raw entry in Gaye's discography. The album features standout tracks like 'Here, My Dear,' 'I Met a Little', and 'When Did You Stop Loving Me, When Did I Stop Loving You,' showcasing Gaye's ability to blend vulnerability with musical brilliance. Despite its initial commercial failure, Here, My Dear has since been re-evaluated as a classic and is regarded as one of Gaye's most honest and compelling works."
    },
    {
        id: "2026-01-26",
        searchQuery: "If You're Feeling Sinister Belle and Sebastian",
        albumTitle: "If You're Feeling Sinister",
        artistName: "Belle and Sebastian",
        weekOf: "January 26, 2026",
        description: "If You're Feeling Sinister is the second studio album by Scottish indie pop band Belle and Sebastian, released in 1996. The album is a seminal work in the indie pop genre, featuring lush arrangements, introspective lyrics, and a blend of folk and pop influences. With standout tracks like 'The Stars of Track and Field,' 'Get Me Away from Here, I'm Dying,' and the title track 'If You're Feeling Sinister,' the album showcases the band's ability to craft poignant narratives and memorable melodies. If You're Feeling Sinister received critical acclaim upon its release and has since become a cult classic, solidifying Belle and Sebastian's place in indie music history."
    },
    {
        id: "2026-01-19",
        searchQuery: "One Thing At A Time Morgan Wallen",
        albumTitle: "One Thing At A Time",
        artistName: "Morgan Wallen",
        weekOf: "January 19, 2026",
        description: "One Thing At A Time is the third studio album by American country music singer Morgan Wallen, released March 3, 2023. The 36-track double album showcases Wallen's versatility as an artist, blending traditional country sounds with modern influences like rock and pop. Featuring hit singles such as 'You Proof,' 'Thought You Should Know,' and 'Last Night,' the album explores themes of love, heartbreak, and personal growth. One Thing At A Time received critical acclaim for its songwriting and production, solidifying Wallen's status as one of country music's leading stars."
    },
    {
        id: "2026-01-12",
        searchQuery: "The Dichotomy David Kushner",
        albumTitle: "The Dichotomy",
        artistName: "David Kushner",
        weekOf: "January 12, 2026",
        description: "The Dichotomy is the debut studio album by American singer-songwriter David Kushner, released August 30, 2024. The 17-track record is an introspective, autobiographical musical journey that explores the tension between opposing forces in life—light and darkness, faith and doubt, good and evil. Across its songs, Kushner reflects on personal struggles, spiritual questions, relationships, and the human condition, crafting a narrative that moves from despair and inner conflict toward revelation and hope. The album blends pop and gothic pop influences and showcases Kushner’s emotional depth and vocal range."
    },
    {
        id: "2026-01-05",
        searchQuery: "The Low End Theory A Tribe Called Quest",
        albumTitle: "The Low End Theory",
        artistName: "A Tribe Called Quest",
        weekOf: "January 5, 2026",
        description: "A groundbreaking album in hip-hop history, The Low End Theory by A Tribe Called Quest is a masterful blend of jazz-infused beats and socially conscious lyrics. Released in 1991, the album features classic tracks like 'Check the Rhime,' 'Jazz (We've Got),' and 'Scenario,' showcasing the group's innovative approach to production and storytelling. With its smooth flows, intricate wordplay, and thought-provoking themes, The Low End Theory has become a timeless classic that continues to influence artists across genres."
    },
    {
        id: "2025-12-29",
        searchQuery: "(What's the Story) Morning Glory? Oasis",
        albumTitle: "(What's the Story) Morning Glory?",
        artistName: "Oasis",
        weekOf: "December 29, 2025",
        description: "A defining album of the Britpop era, (What's the Story) Morning Glory? by Oasis is a collection of anthemic rock songs that capture the spirit of the 1990s. Featuring iconic tracks like 'Wonderwall,' 'Don't Look Back in Anger,' and 'Champagne Supernova,' the album showcases Noel Gallagher's songwriting prowess and Liam Gallagher's distinctive vocals. With its blend of catchy melodies, powerful guitar riffs, and introspective lyrics, Morning Glory became one of the best-selling albums in UK history and solidified Oasis's status as one of the leading bands of their generation."
    },
    {
        id: "2025-12-22",
        searchQuery: "4:44 Jay-Z",
        albumTitle: "4:44",
        artistName: "Jay-Z",
        weekOf: "December 22, 2025",
        description: "A deeply personal and introspective album from Jay-Z, 4:44 is a reflection on his life, relationships, and legacy. Produced by No I.D., the album features soulful beats and poignant lyrics that address themes of infidelity, family, and self-improvement. Standout tracks like 'The Story of O.J.,' '4:44,' and 'Family Feud' showcase Jay-Z's growth as an artist and his willingness to confront his past mistakes. The album received critical acclaim for its honesty and vulnerability, solidifying Jay-Z's status as one of hip-hop's most influential figures."   
    },
    {
        id: "2025-12-15",
        searchQuery: "Mother John Lennon",
        albumTitle: "Plastic Ono Band",
        artistName: "John Lennon",
        weekOf: "December 15, 2025",
        description: "A deeply personal and raw album from John Lennon, John Lennon/Plastic Ono Band is a powerful exploration of his emotions and experiences following the breakup of The Beatles. Produced by Phil Spector, the album features sparse arrangements that highlight Lennon's vulnerable vocals and introspective lyrics. Standout tracks like 'Mother,' 'Working Class Hero,' and 'God' showcase Lennon's ability to confront his past and express his innermost thoughts. The album is widely regarded as one of Lennon's finest solo works, solidifying his legacy as a solo artist."
    },
    {
        id: "2025-12-08",
        searchQuery: "Red Headed Stranger Willie Nelson",
        albumTitle: "Red Headed Stranger",
        artistName: "Willie Nelson",
        weekOf: "December 8, 2025",
        description: "A classic country album from Willie Nelson, Red Headed Stranger is a concept album that tells the story of a fugitive on the run after killing his wife and her lover. With its sparse arrangements and haunting melodies, the album captures the essence of traditional country music while showcasing Nelson's distinctive voice and songwriting prowess. Standout tracks like 'Blue Eyes Crying in the Rain,' 'Time of the Preacher,' and the title track 'Red Headed Stranger' have become timeless classics, solidifying the album's status as one of the greatest country albums of all time."
    },
    {
        id: "2025-12-01",
        searchQuery: "Be Common",
        albumTitle: "Be",
        artistName: "Common",
        weekOf: "December 1, 2025",
        description: "A landmark album from Common, Be is a soulful and introspective journey through themes of love, life, and social consciousness. Produced by the legendary J Dilla, the album features smooth beats and jazzy instrumentation that perfectly complement Common's thoughtful lyrics. Standout tracks like 'The Light,' 'Go!,' and 'Faithful' showcase Common's lyrical prowess and his ability to craft meaningful narratives. Be is widely regarded as one of the greatest hip-hop albums of all time, solidifying Common's status as a leading voice in the genre."
    },
    {
        id: "2025-11-24",
        searchQuery: "Black Pearl Jam",
        albumTitle: "Ten",
        artistName: "Pearl Jam",
        weekOf: "November 24, 2025",
        description: "A defining album of the 1990s grunge movement, Ten by Pearl Jam is a powerful blend of raw emotion and hard-hitting rock. Featuring iconic tracks like 'Alive,' 'Even Flow,' and 'Jeremy,' the album explores themes of personal struggle, identity, and social issues. With Eddie Vedder's distinctive vocals and the band's dynamic instrumentation, Ten has become a timeless classic that continues to resonate with listeners worldwide."
    },
    {
        id: "2025-11-17",
        searchQuery: "Demon Days Gorillaz",
        albumTitle: "Demon Days",
        artistName: "Gorillaz",
        weekOf: "November 17, 2025",
        description: "A genre-defying album from Gorillaz, Demon Days blends alternative rock, hip-hop, and electronic music to create a unique sonic experience. Featuring hits like 'Feel Good Inc.,' 'DARE,' and 'Dirty Harry,' the album explores themes of environmentalism, consumerism, and societal decay. With its innovative production, eclectic collaborations, and thought-provoking lyrics, Demon Days has become a landmark album that pushes the boundaries of modern music."
    },
    {
        id: "2025-11-10",
        searchQuery: "Curtis Curtis Mayfield",
        albumTitle: "Curtis",
        artistName: "Curtis Mayfield",
        weekOf: "November 10, 2025",
        description: "A seminal soul album from Curtis Mayfield, blending funk, R&B, and socially conscious lyrics. Featuring classics like 'Move On Up,' 'Superfly,' and 'Freddie's Dead,' the album explores themes of empowerment, social justice, and personal resilience. Its innovative production and Mayfield's distinctive falsetto vocals have made it a timeless classic, influencing generations of artists across genres."
    },
    {
        id: "2025-11-03",
        searchQuery: "Exit U2",
        albumTitle: "The Joshua Tree",
        artistName: "U2",
        weekOf: "November 3, 2025",
        description: "A landmark album from U2, The Joshua Tree captures the band's exploration of American roots music while addressing themes of spirituality, politics, and personal reflection. Featuring iconic tracks like 'With or Without You,' 'I Still Haven't Found What I'm Looking For,' and 'Where the Streets Have No Name,' the album showcases U2's signature sound with The Edge's atmospheric guitar work and Bono's passionate vocals. The Joshua Tree received critical acclaim and commercial success, solidifying U2's status as one of the world's leading rock bands."
    },
    {
        id: "2025-10-27",
        searchQuery: "good kid, m.A.A.d city Kendrick Lamar",
        albumTitle: "good kid, m.A.A.d city",
        artistName: "Kendrick Lamar",
        weekOf: "October 27, 2025",
        description: "A groundbreaking album from Kendrick Lamar, good kid, m.A.A.d city is a cinematic exploration of life in Compton. Blending hip-hop with storytelling, the album features vivid narratives and complex characters. Standout tracks like 'Swimming Pools (Drank),' 'Bitch, Don't Kill My Vibe,' and 'm.A.A.d city' showcase Lamar's lyrical prowess and social commentary. The album's innovative production and cohesive concept have made it a modern classic, solidifying Lamar's status as one of the most influential rappers of his generation."
    },
    {
        id: "2025-10-20",
        searchQuery: "Nebraska Bruce Springsteen",
        albumTitle: "Nebraska",
        artistName: "Bruce Springsteen",
        weekOf: "October 20, 2025",
        description: "A stark and haunting album from Bruce Springsteen, Nebraska is a departure from his usual rock sound. Recorded as a series of solo demos, the album features raw acoustic arrangements and introspective lyrics that explore themes of isolation, despair, and the American experience. Standout tracks like 'Atlantic City,' 'Johnny 99,' and the title track 'Nebraska' showcase Springsteen's storytelling prowess and his ability to capture the struggles of everyday people. The album's minimalist production and somber tone have made it a cult favorite among fans and critics alike."
    },
    {
        id: "2025-10-13",
        searchQuery: "Californication Red Hot Chili Peppers",
        albumTitle: "Californication",
        artistName: "Red Hot Chili Peppers",
        weekOf: "October 13, 2025",
        description: "A defining album from the Red Hot Chili Peppers, Californication marked a return to form for the band. Blending funk, rock, and alternative sounds, the album features introspective lyrics and memorable melodies. Standout tracks like 'Scar Tissue,' 'Otherside,' and the title track 'Californication' showcase the band's ability to craft emotionally resonant songs with infectious grooves. The album's exploration of themes like fame, addiction, and personal growth has made it a fan favorite and a staple in the band's discography."
    },
    {
        id: "2025-10-06",
        searchQuery: "Rubber Soul The Beatles",
        albumTitle: "Rubber Soul",
        artistName: "The Beatles",
        weekOf: "October 6, 2025",
        description: "A transformative album from The Beatles, Rubber Soul marked a significant evolution in their sound and songwriting. Blending folk rock, pop, and soul influences, the album features introspective lyrics and innovative arrangements. Standout tracks like 'Norwegian Wood,' 'In My Life,' and 'Drive My Car' showcase the band's growing maturity and experimentation. Rubber Soul is often regarded as one of the greatest albums of all time, reflecting The Beatles' artistic growth and their impact on the music landscape of the 1960s."
    },
    {
        id: "2025-09-29",
        searchQuery: "Rumours Fleetwood Mac",
        albumTitle: "Rumours",
        artistName: "Fleetwood Mac",
        weekOf: "September 29, 2025",
        description: "A timeless classic from Fleetwood Mac, Rumours is an album filled with emotional depth and musical brilliance. Featuring hits like 'Go Your Own Way,' 'Dreams,' and 'The Chain,' the album explores themes of love, heartbreak, and resilience. Its blend of rock, pop, and folk elements, combined with the band's impeccable harmonies and songwriting, has made it one of the best-selling albums of all time. Rumours remains a defining work in the rock genre, showcasing Fleetwood Mac's enduring influence and artistry.",
    },
    {
        id: "2025-09-22",
        searchQuery: "The Heathen Bob Marley",
        albumTitle: "Exodus",
        artistName: "Bob Marley & The Wailers",
        weekOf: "September 22, 2025",
        description: "A seminal reggae album from Bob Marley & The Wailers, blending socially conscious lyrics with infectious rhythms. Featuring classics like 'Jamming,' 'Three Little Birds,' and the title track 'Exodus,' the album explores themes of freedom, unity, and resilience. Its fusion of reggae, rock, and soul elements helped bring Jamaican music to a global audience, solidifying Marley's status as a cultural icon and one of the most influential musicians of all time."
    },
    {
        id: "2025-09-15",
        searchQuery: "The Divine Feminine Mac Miller",
        albumTitle: "The Divine Feminine",
        artistName: "Mac Miller",
        weekOf: "September 15, 2025",
        description: "A soulful and jazzy exploration of love and relationships from the late Mac Miller. The Divine Feminine blends hip-hop with R&B, jazz, and funk influences, creating a smooth and intimate soundscape. Featuring collaborations with artists like Anderson .Paak and Ariana Grande, the album delves into themes of romance, vulnerability, and self-discovery. Its heartfelt lyrics and lush production make it a standout in Miller's discography, showcasing his growth as an artist before his untimely passing."
    },
    {
        id: "2025-09-08",
        searchQuery: "Sweet Baby James James Taylor",
        albumTitle: "Sweet Baby James",
        artistName: "James Taylor",
        weekOf: "September 8, 2025",
        description: "A classic James Taylor album filled with soothing acoustic melodies and heartfelt lyrics. Featuring timeless tracks like 'Fire and Rain' and the title track 'Sweet Baby James,' the album showcases Taylor's signature blend of folk, rock, and country influences. Its introspective themes of love, loss, and hope have resonated with listeners for decades, making it a staple in the singer-songwriter genre.",
    },
    {
        id: "2025-09-01",
        searchQuery: "Naeem Bon Iver",
        albumTitle: "i,i",
        artistName: "Bon Iver",
        weekOf: "September 1, 2025",
        description: "A lush and introspective Bon Iver album that blends folk, indie rock, and electronic elements. Featuring standout tracks like 'Hey, Ma,' 'Faith,' and 'Naeem,' it was released in 2019 as the band's fourth album."
    },
    {
        id: "2025-08-25",
        searchQuery: "Ivy Frank Ocean",
        albumTitle: "Blonde",
        artistName: "Frank Ocean",
        weekOf: "August 25, 2025",
        description: "An introspective and genre-defying masterpiece from Frank Ocean. Blonde blends R&B, pop, and experimental sounds to create a deeply personal and emotional journey. With standout tracks like 'Nights' and 'Self Control,' the album explores themes of identity, love, and vulnerability. Its innovative production and Ocean's soulful vocals have made it a defining work of the 2010s, earning critical acclaim and a dedicated fanbase."
    },
    {
        id: "2025-08-18",
        searchQuery: "Songs in the Key of Life Stevie Wonder",
        albumTitle: "Songs in the Key of Life",
        artistName: "Stevie Wonder",
        weekOf: "August 18, 2025",
        description: "A landmark double album from Stevie Wonder, blending soul, funk, jazz, and pop into a cohesive masterpiece. Featuring classics like 'Isn’t She Lovely' and 'Sir Duke,' it explores themes of love, social justice, and spirituality. The album showcases Wonder’s virtuosity on multiple instruments and his innovative production techniques. Widely regarded as one of the greatest albums of all time, it remains a defining work in the history of popular music."
    },
    {
        id: "2025-08-11",
        searchQuery: "One Beer MF DOOM",
        albumTitle: "MM..FOOD",
        artistName: "MF DOOM",
        weekOf: "August 11, 2025",
        description: "A cult classic from the late MF DOOM, MM..FOOD is a concept album that blends intricate wordplay with food metaphors. Known for its unique production and clever lyricism, it features tracks like 'Rapp Snitch Knishes' and 'Hoe Cakes.' The album showcases DOOM's signature style, combining humor, introspection, and a love for hip-hop culture. It remains a beloved work in underground rap circles."
    },
    {
        id: "2025-08-04",
        searchQuery: "Jungleland Bruce Springsteen",
        albumTitle: "Born to Run",
        artistName: "Bruce Springsteen",
        weekOf: "August 4, 2025",
        description: "A soaring and cinematic Bruce Springsteen album. It marked his breakthrough into mainstream success, blending rock, soul, and poetry into anthems of youth and escape. Featuring standout tracks like 'Born to Run' and 'Thunder Road,' the album captures themes of freedom, longing, and working-class dreams. Widely acclaimed, it became a defining work of 1970s rock and cemented Springsteen’s status as a major voice in American music."
    },
    {
        id: "2025-07-28",
        searchQuery: "The Bends Radiohead",
        albumTitle: "The Bends",
        artistName: "Radiohead",
        weekOf: "July 28, 2025",
        description: "An emotional and introspective Radiohead album. It marked a departure from their grunge-influenced debut, showcasing a more atmospheric and emotional sound. Featuring standout tracks like 'Fake Plastic Trees' and 'Street Spirit (Fade Out),' the album explores themes of alienation and identity. Though initially overlooked, it later gained acclaim as a pivotal moment in Radiohead’s evolution and a defining work of '90s alternative rock.",
    },
    {
        id: "2025-07-21",
        searchQuery: "The Freewheelin' Bob Dylan Bob Dylan",
        albumTitle: "The Freewheelin' Bob Dylan",
        artistName: "Bob Dylan",
        weekOf: "July 21, 2025",
        description: "An essential folk‑rock collection from Bob Dylan’s early years, packed with timeless originals like “Blowin’ in the Wind,” “Masters of War,” and “Girl from the North Country.” Filled with poetic lyrics about social change, protest, love and loss, this album became a defining voice of the 1960s civil rights and anti‑war movement, cementing Dylan’s role as a cultural icon.",
    },
    {
        id: "2025-07-14",
        searchQuery: "Tapestry Carole King",
        albumTitle: "Tapestry",
        artistName: "Carole King",
        weekOf: "July 14, 2025",
        description: "A soulful, piano‑driven masterwork of singer‑songwriter intimacy, Tapestry delivers hit highlights like “It’s Too Late,” “You’ve Got a Friend,” and “Natural Woman.” Carole King’s deeply personal, emotionally honest songwriting blends folk, soul, pop, and blues into a warm musical experience. Tapestry sold over 30 million copies worldwide, won multiple Grammys, and is celebrated as a cornerstone of modern pop music."
    },
    {
        id: "2025-07-07",
        searchQuery: "Igor Tyler, the Creator",
        albumTitle: "Igor",
        artistName: "Tyler, the Creator",
        weekOf: "July 7, 2025",
        description: "A bold, genre‑blending drama exploring jealousy, identity, and love through the lens of Tyler’s alter‑ego “Igor.” Driven by lush synth textures, hip‑hop beats, and emotional vocals, this album crafts a cinematic narrative soundscape with standout tracks—or individual songs—that embody modern experimental pop, emotional complexity, and boundary‑pushing production."
    },
    {
        id: "2025-06-30",
        searchQuery: "Pink Moon Nick Drake",
        albumTitle: "Pink Moon",
        artistName: "Nick Drake",
        weekOf: "June 30, 2025",
        description: "A minimalist folk gem defined by Nick Drake’s intimate acoustic guitar and piano arrangements. With introspective, melancholic lyrics and understated beauty, this album creates an emotional soundscape full of solitude and subtle reflection. It's ideal for listeners seeking lyrical depth and tranquil melodies—whether they found a specific song or discovered the album."
    },
    {
        id: "2025-06-23",
        searchQuery: "Led Zeppelin IV(Remaster) Led Zeppelin",
        albumTitle: "Led Zeppelin IV",
        artistName: "Led Zeppelin",
        weekOf: "June 23, 2025",
        description: "Known for epoch‑defining tracks like “Stairway to Heaven,” “Black Dog,” and “Rock and Roll,” this powerful fusion of hard rock, blues, folk, and classic riffs made Led Zeppelin into legends. The album delivers sweeping dynamics, timeless melodies, guitar masterpieces, and themes of mythology and Americana—an essential entry point for new fans exploring the songs."
    },
    {
        id: "2025-06-16",
        searchQuery: "Hotel California Eagles",
        albumTitle: "Hotel California",
        artistName: "Eagles",
        weekOf: "June 16, 2025",
        description: "A cinematic blend of West Coast rock, storytelling, and harmony-rich production capturing California’s myth, fame, and disillusionment. Featuring the evergreen title track plus “Life in the Fast Lane” and “New Kid in Town,” this album pairs smooth guitar work with introspective lyrics about excess and the American dream."
    },
    {
        id: "2025-06-09",
        searchQuery: "Human Nature Michael Jackson",
        albumTitle: "Thriller",
        artistName: "Michael Jackson",
        weekOf: "June 9, 2025",
        description: "The watershed moment in pop music history: an album that defined global pop culture with blockbuster hits like “Thriller,” “Billie Jean,” and “Beat It.” Blending pop, R&B, funk, and rock, it showcases cinematic production, groundbreaking dance tracks, and a universal appeal that continues to influence music today."
    },
    {
        id: "2025-06-02",
        searchQuery: "Think About You Guns N Roses",
        albumTitle: "Appetite for Destruction",
        artistName: "Guns N Roses",
        weekOf: "June 2, 2025",
        description: "Raw, rebellious, and electrifying, this debut album ignited late‑’80s hard rock with fiery songs such as “Welcome to the Jungle,” “Sweet Child o’ Mine,” and “Paradise City.” Featuring gritty lyrics, searing guitar solos, and an authentic street‑wise attitude, it transformed rock with uncompromised energy and swagger."
    },
    {
        id: "2025-05-26",
        searchQuery: "Time Pink Floyd",
        albumTitle: "The Dark Side of the Moon",
        artistName: "Pink Floyd",
        weekOf: "May 26, 2025",
        description: "A genre‑defining progressive/psychedelic rock concept album from March 1973 that explores time, money, mental health, death, consumerism, and societal alienation. It interweaves ambient soundscapes, tape loops, synthesizers, and interview snippets into a seamless emotional journey from “Speak to Me” to “Eclipse,” all bookended by a heartbeat motif. With iconic tracks like “Time,” “Money,” “Us and Them,” and “Brain Damage,” it became one of the best-selling and most influential albums ever, certified multi-platinum and sustaining legendary status for decades"
    },
];

// Store loaded album data to avoid re-fetching
const songCache = {};
let displayedPickId = null; // Track which pick is currently displayed at the top

function sortedPicks() {
    return [...PICK_HISTORY].sort((a, b) => b.id.localeCompare(a.id));
}

// The newest pick is "This Week" only while it's actually this week
function isThisWeek(pick) {
    const age = Date.now() - new Date(pick.id + 'T00:00:00').getTime();
    return age >= 0 && age < 7 * 24 * 60 * 60 * 1000;
}

function initializePickOfTheWeek() {
    const pickSection = document.querySelector('.pick-of-week-section');
    if (!pickSection) return;

    const picks = sortedPicks();
    displayedPickId = picks[0].id;

    pickSection.innerHTML = `
        <div class="pick-of-week-container">
            <h2>Pick of the Week</h2>
            <div class="featured-pick-container">
                <div class="pick-loading-inline">
                    <p>Loading this week's pick...</p>
                </div>
            </div>
            <div class="past-picks-section">
                <h3>Past Picks</h3>
                <div class="past-picks-scroll">
                    <div class="past-picks-loading">
                        <p>Loading past picks...</p>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Show the featured pick as soon as it loads rather than waiting for every past pick
    loadSongData(picks[0]).then(renderFeaturedPick);
    Promise.all(picks.map(loadSongData)).then(renderPastPicks);
}

function loosely(text) {
    return String(text || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

// Never rejects: a failed lookup still shows the pick, just with placeholder art
function loadSongData(pickConfig) {
    if (songCache[pickConfig.id]) {
        return Promise.resolve(songCache[pickConfig.id]);
    }

    const fallback = { song: { title: pickConfig.albumTitle, artist: pickConfig.artistName, album_cover: null }, config: pickConfig };

    return postJson('/api/search', { query: pickConfig.searchQuery, limit: 10 })
        .then(data => {
            const results = data.results || [];
            const sameArtist = results.filter(r => loosely(r.artist).includes(loosely(pickConfig.artistName)) ||
                                                   loosely(pickConfig.artistName).includes(loosely(r.artist)));
            const sameAlbum = sameArtist.find(r => loosely(r.album).includes(loosely(pickConfig.albumTitle)));
            const bestMatch = sameAlbum || sameArtist[0] || results[0];
            if (bestMatch) fallback.song.album_cover = bestMatch.album_cover;
            songCache[pickConfig.id] = fallback;
            return fallback;
        })
        .catch(error => {
            console.error(`Error loading pick ${pickConfig.id}:`, error);
            return fallback;
        });
}

function renderFeaturedPick() {
    const featuredContainer = document.querySelector('.featured-pick-container');
    const pickData = songCache[displayedPickId] || {
        song: {}, config: PICK_HISTORY.find(p => p.id === displayedPickId)
    };
    const { song, config } = pickData;
    const title = song.title || config.albumTitle;
    const artist = song.artist || config.artistName;
    const isLatest = config.id === sortedPicks()[0].id;
    const badge = isLatest
        ? `<div class="current-pick-badge">${isThisWeek(config) ? 'This Week' : 'Latest Pick'}</div>`
        : '<div class="past-pick-badge">Past Pick</div>';

    // Use album search links instead of song search
    const spotifyAlbumSearch = `https://open.spotify.com/search/${encodeURIComponent(`${title} ${artist}`)}/albums`;
    const appleAlbumSearch = `https://music.apple.com/us/search?term=${encodeURIComponent(`${title} ${artist}`)}`;

    featuredContainer.innerHTML = `
        <div class="featured-pick-card">
            <div class="featured-pick-image">
                <img data-cover src="${escapeHtml(song.album_cover || PLACEHOLDER_COVER)}" alt="${escapeHtml(title)} by ${escapeHtml(artist)}" class="featured-cover-image">
                ${badge}
            </div>

            <div class="featured-pick-info">
                <div class="featured-pick-details">
                    <p class="featured-pick-week">Week of ${escapeHtml(config.weekOf)}</p>
                    <h3 class="featured-pick-title">${escapeHtml(title)}</h3>
                    <p class="featured-pick-artist">by ${escapeHtml(artist)}</p>
                    ${config.description ? `<p class="featured-pick-description">${escapeHtml(config.description)}</p>` : ''}
                </div>

                <div class="featured-music-links">
                    <a href="${escapeHtml(spotifyAlbumSearch)}" target="_blank" rel="noopener noreferrer" class="music-link spotify">
                        <span class="link-icon">♪</span> Listen on Spotify
                    </a>
                    <a href="${escapeHtml(appleAlbumSearch)}" target="_blank" rel="noopener noreferrer" class="music-link apple">
                        <span class="link-icon">♪</span> Listen on Apple Music
                    </a>
                </div>
            </div>
        </div>
    `;
    attachCoverFallbacks(featuredContainer);
}

function renderPastPicks() {
    const pastPicksScroll = document.querySelector('.past-picks-scroll');
    const pastPicks = sortedPicks().filter(pick => pick.id !== displayedPickId);

    if (pastPicks.length === 0) {
        pastPicksScroll.innerHTML = '<p class="no-past-picks">No past albums to show</p>';
        return;
    }

    const latestId = sortedPicks()[0].id;
    pastPicksScroll.innerHTML = pastPicks.map(pick => {
        const { song } = songCache[pick.id] || { song: {} };
        const title = song.title || pick.albumTitle;
        const artist = song.artist || pick.artistName;
        return `
            <div class="past-pick-card" data-pick-id="${escapeHtml(pick.id)}" role="button" tabindex="0"
                 aria-label="Show ${escapeHtml(title)} by ${escapeHtml(artist)}">
                <div class="past-pick-content">
                    <div class="past-pick-image">
                        <img data-cover src="${escapeHtml(song.album_cover || PLACEHOLDER_COVER)}" alt="" class="past-cover-image" loading="lazy">
                        ${pick.id === latestId ? '<div class="current-indicator">Latest</div>' : ''}
                    </div>
                    <div class="past-pick-info">
                        <p class="past-pick-week">${escapeHtml(pick.weekOf)}</p>
                        <h4 class="past-pick-title">${escapeHtml(title)}</h4>
                        <p class="past-pick-artist">${escapeHtml(artist)}</p>
                    </div>
                </div>
            </div>
        `;
    }).join('');
    attachCoverFallbacks(pastPicksScroll);

    pastPicksScroll.querySelectorAll('.past-pick-card').forEach(card => {
        card.style.cursor = 'pointer';
        card.addEventListener('click', () => switchToPickWithAnimation(card.dataset.pickId));
        card.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                switchToPickWithAnimation(card.dataset.pickId);
            }
        });
    });
}

function switchToPickWithAnimation(newPickId) {
    if (!newPickId || newPickId === displayedPickId) return;
    const featuredContainer = document.querySelector('.featured-pick-container');

    featuredContainer.style.opacity = '0.5';
    featuredContainer.style.transform = 'scale(0.95)';

    setTimeout(() => {
        displayedPickId = newPickId;
        renderFeaturedPick();
        renderPastPicks();
        featuredContainer.style.opacity = '1';
        featuredContainer.style.transform = 'scale(1)';
        featuredContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 200);
}
