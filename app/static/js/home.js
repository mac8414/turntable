// --- IMAGE COMPRESSION UTILITY ---
function compressImageUrl(originalUrl, width = 300, height = 300, quality = 0.8) {
    // If it's a Spotify image, we can use their built-in resizing
    if (originalUrl && originalUrl.includes('i.scdn.co')) {
        // Spotify images can be resized by changing the URL
        return originalUrl.replace(/\/\d+x\d+\//, `/${width}x${height}/`);
    }
    
    // For other images, we'll create a compressed version using canvas
    return new Promise((resolve) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        
        img.onload = function() {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            
            // Set canvas size to desired dimensions
            canvas.width = width;
            canvas.height = height;
            
            // Draw and compress
            ctx.drawImage(img, 0, 0, width, height);
            
            // Convert to compressed data URL
            const compressedUrl = canvas.toDataURL('image/jpeg', quality);
            resolve(compressedUrl);
        };
        
        img.onerror = function() {
            // If compression fails, return original URL
            resolve(originalUrl);
        };
        
        img.src = originalUrl;
    });
}

// Synchronous version for Spotify URLs (most common case)
function getCompressedImageUrl(originalUrl, size = 'medium') {
    if (!originalUrl) return originalUrl;
    
    // For Spotify images, use their resizing
    if (originalUrl.includes('i.scdn.co')) {
        const sizeMap = {
            'small': '150x150',
            'medium': '300x300', 
            'large': '640x640'
        };
        return originalUrl.replace(/\/\d+x\d+\//, `/${sizeMap[size] || sizeMap.medium}/`);
    }
    
    // For other images, return original (you could implement server-side compression)
    return originalUrl;
}

// --- LAVA LAMP ANIMATION ---
document.addEventListener('DOMContentLoaded', function() {
    // Check if Vue is available
    if (typeof Vue === 'undefined') {
        console.error('Vue is not loaded! Using plain JavaScript for animation instead.');
        animateLavaLamp();
        return;
    }
    
    window.isPlaying = false;

    // Use Vue if available
    const { createApp } = Vue;
    
    createApp({
        data() {
            return {
                blobs: [
                    { id: 'blob1', x: window.innerWidth * 0.4, y: window.innerHeight * 0.3, 
                      xSpeed: 0.3, ySpeed: 0.4, xOffset: 0, yOffset: 0, phase: 0 },
                    { id: 'blob2', x: window.innerWidth * 0.6, y: window.innerHeight * 0.5, 
                      xSpeed: 0.4, ySpeed: 0.5, xOffset: 1, yOffset: 2, phase: 1.5 },
                    { id: 'blob3', x: window.innerWidth * 0.5, y: window.innerHeight * 0.7, 
                      xSpeed: 0.2, ySpeed: 0.3, xOffset: 2, yOffset: 1, phase: 3 },
                    { id: 'blob4', x: window.innerWidth * 0.3, y: window.innerHeight * 0.4, 
                      xSpeed: 0.25, ySpeed: 0.35, xOffset: 3, yOffset: 3, phase: 4.5 },
                    { id: 'blob5', x: window.innerWidth * 0.7, y: window.innerHeight * 0.2, 
                      xSpeed: 0.35, ySpeed: 0.2, xOffset: 4, yOffset: 2, phase: 6 },
                    { id: 'blob6', x: window.innerWidth * 0.2, y: window.innerHeight * 0.6, 
                      xSpeed: 0.15, ySpeed: 0.25, xOffset: 5, yOffset: 5, phase: 7.5 },
                    { id: 'blob7', x: window.innerWidth * 0.8, y: window.innerHeight * 0.3, 
                      xSpeed: 0.3, ySpeed: 0.15, xOffset: 6, yOffset: 4, phase: 9 },
                    { id: 'blob8', x: window.innerWidth * 0.4, y: window.innerHeight * 0.8, 
                      xSpeed: 0.2, ySpeed: 0.3, xOffset: 7, yOffset: 1, phase: 10.5 },
                    { id: 'blob9', x: window.innerWidth * 0.6, y: window.innerHeight * 0.1, 
                      xSpeed: 0.25, ySpeed: 0.2, xOffset: 8, yOffset: 6, phase: 12 },
                    { id: 'blob10', x: window.innerWidth * 0.2, y: window.innerHeight * 0.2, 
                      xSpeed: 0.15, ySpeed: 0.15, xOffset: 9, yOffset: 3, phase: 13.5 }
                ],
                bounds: {
                    minX: -100,
                    minY: -100,
                    maxX: window.innerWidth + 100,
                    maxY: window.innerHeight + 100
                },
                time: 0
            };
        },
        mounted() {
            // Set initial positions
            this.setInitialPositions();
            
            // Update boundaries on window resize
            window.addEventListener('resize', () => {
                this.bounds.maxX = window.innerWidth + 100;
                this.bounds.maxY = window.innerHeight + 100;
            });
            
            // Start animation using requestAnimationFrame for smoother animation
            this.animate();
        },
        methods: {
            setInitialPositions() {
                this.blobs.forEach(blob => {
                    const element = document.getElementById(blob.id);
                    if (element) {
                        element.setAttribute('cx', blob.x);
                        element.setAttribute('cy', blob.y);
                    }
                });
            },
            animate() {
                // Update time
                this.time += 0.01;
                
                // Update all blob positions
                this.blobs.forEach(blob => {
                    this.updateBlobPosition(blob);
                });
                
                // Continue animation
                requestAnimationFrame(this.animate);
            },
            updateBlobPosition(blob) {
                // Use sinusoidal motion for more fluid, organic movement
                const xWave = Math.sin(this.time * blob.xSpeed + blob.phase) * 50;
                const yWave = Math.cos(this.time * blob.ySpeed + blob.phase) * 50;
                
                // Add slow drift upward to simulate rising heat
                blob.y -= 0.1;
                
                // Add wave motion
                blob.x += xWave * 0.02;
                
                // Boundary checks with smooth transitions
                if (blob.y < this.bounds.minY) {
                    // When a blob reaches the top, reset it to the bottom
                    blob.y = this.bounds.maxY;
                    // Randomize horizontal position slightly
                    blob.x = Math.max(this.bounds.minX, Math.min(this.bounds.maxX, blob.x + (Math.random() - 0.5) * 100));
                }
                
                if (blob.x < this.bounds.minX) {
                    blob.x = this.bounds.minX;
                    blob.xSpeed = Math.abs(blob.xSpeed);
                } else if (blob.x > this.bounds.maxX) {
                    blob.x = this.bounds.maxX;
                    blob.xSpeed = -Math.abs(blob.xSpeed);
                }
                
                // Update SVG element position
                const element = document.getElementById(blob.id);
                if (element) {
                    element.setAttribute('cx', blob.x);
                    element.setAttribute('cy', blob.y);
                }
            }
        }
    }).mount('#lavaLamp');
    
    // Fallback animation function if Vue is not available
    function animateLavaLamp() {
        // Plain JavaScript implementation of the same animation
        // This would be very similar to the Vue implementation but using
        // vanilla JS for state management instead
        console.log('Fallback animation running.');
        
        // Implementation details would go here
    }
});

// --- LAST.FM API INTEGRATION ---
const LASTFM_API_KEY = 'YOUR_LASTFM_API_KEY'; // You'll need to get this from Last.fm
const LASTFM_BASE_URL = 'https://ws.audioscrobbler.com/2.0/';

// Function to fetch artist info from your Flask backend
async function fetchArtistInfo(artistName) {
    try {
        const response = await fetch('/api/artist-info', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ artist_name: artistName })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.artist_info && data.artist_info.bio) {
            return data.artist_info.bio;
        }
        
        return null;
    } catch (error) {
        console.error('Error fetching artist info:', error);
        return null;
    }
}

// Function to update recommendation display with artist fact
function updateRecommendationWithArtistFact(recommendationBox, title, artist, timeframe, genre, count) {
    // Initial loading UI with a placeholder for the artist fact
    recommendationBox.innerHTML = `
        <div class="recommendations-show">
            <h3>Loading recommendations for ${title} by ${artist}...</h3>
            <p>Time Frame: ${timeframe} | Genre: ${genre} | Count: ${count}</p>
            <h5>Powered by <strong>CadenceAI</strong></h5>
            <div class="artist-fact-container">
                <p class="artist-fact-loading" id="artistFactLoading">Loading artist fact...</p>
            </div>
        </div>
    `;

    // Fetch artist fact and update only the artist fact section
    fetchArtistInfo(artist)
        .then(artistFact => {
            const factElem = document.getElementById('artistFactLoading');
            if (factElem && artistFact) {
                factElem.className = 'artist-fact';
                factElem.innerHTML = `<strong>About ${artist}:</strong> ${artistFact}`;
            } else if (factElem) {
                factElem.textContent = "No artist fact found.";
            }
        })
        .catch(error => {
            const factElem = document.getElementById('artistFactLoading');
            if (factElem) factElem.textContent = "Error loading artist fact.";
            console.error('Error fetching artist fact:', error);
        });

    // Fetch recommendations WITHOUT timeout - let it run as long as needed
    fetch('/api/recommend', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
            track_name: title, 
            artist_name: artist,
            timeframe: timeframe === 'Any' ? '' : timeframe,
            genre: genre === 'Any' ? '' : genre,
            count: count
        })
        // Removed the signal parameter - no more timeout!
    })
    .then(response => {
        // Check if the response is HTML (error page) instead of JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            throw new Error(`Server returned ${response.status}: ${response.statusText}. Expected JSON but got ${contentType}`);
        }
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return response.json();
    })
    .then(recData => {
        let recHTML = `
            <div class="recommendations-show">
                <h3>Top results for ${title} by ${artist}</h3>
                <p>Time Frame: ${timeframe} | Genre: ${genre}</p>
                <h5>Powered by <strong>CadenceAI</strong></h5>
            </div>
            <ul class="recommendation-list">
        `;
        if (recData.recommendations && recData.recommendations.length > 0) {
            recData.recommendations.forEach(rec => {
                const albumCoverUrl = rec.album_cover || '/api/placeholder/50/50';
                const spotifyLink = rec.spotify_link || `https://open.spotify.com/search/${encodeURIComponent(rec.title + ' ' + rec.artist)}`;
                const appleMusicLink = rec.apple_music_link || `https://music.apple.com/us/search?term=${encodeURIComponent(rec.title + ' ' + rec.artist)}`;
                recHTML += `
                    <li class="recommendation-item">
                        <div class="recommendation-bg" style="background-image: url('${albumCoverUrl}')"></div>
                        <div class="recommendation-cover">
                            <img src="${albumCoverUrl}" alt="${rec.title} album cover">
                        </div>
                        <div class="recommendation-info">
                            <h4 class="recommendation-title">${rec.title}</h4>
                            <p class="recommendation-artist">${rec.artist}</p>
                        </div>
                        <div class="recommendation-right">
                            <div class="recommendation-match">${rec.similarity_score || 0}% match</div>
                            <div class="musicLink">
                                <a href="${appleMusicLink}" target="_blank" rel="noopener noreferrer">
                                    Listen on Apple Music
                                </a>
                            </div>
                            <div class="musicLink">
                                <a href="${spotifyLink}" target="_blank" rel="noopener noreferrer">
                                    Listen on Spotify
                                </a>
                            </div>
                        </div>
                    </li>
                `;
            });
        } else {
            recHTML += `<li class="recommendation-item">No recommendations found</li>`;
        }
        recHTML += `</ul>`;

        // Replace the entire recommendationBox content (removes the artist fact)
        recommendationBox.innerHTML = recHTML;
    })
    .catch(error => {
        let errorMessage = 'Error loading recommendations';
        if (error.message.includes('504')) {
            errorMessage = 'Server timeout - the recommendation system is taking too long';
        } else if (error.message.includes('500')) {
            errorMessage = 'Internal server error - please try again';
        }
        
        recommendationBox.innerHTML = `
            <div class="recommendations-show">
                <h3>${errorMessage}</h3>
                <p>Please try again with a different song or fewer recommendations.</p>
                <h5>Powered by <strong>CadenceAI</strong></h5>
            </div>
        `;
        console.error('Error fetching recommendations:', error);
    });
}

// --- RANDOMIZER LOGIC (UPDATED TO USE ARTIST FACTS) ---
function randomizeSelection() {
    console.log('Randomize button clicked!');
    
    const button = document.querySelector('.randomize-button') || document.querySelector('.randomizeButton');
    const searchInput = document.getElementById('songSearch');
    
    if (!button || !searchInput) {
        console.error('Button or search input not found!');
        return;
    }
    
    button.disabled = true;
    button.textContent = "Loading...";
    
    // Array of random search terms to get different results
    const randomSearchTerms = [
        'love', 'heart', 'night', 'dream', 'fire', 'rock', 'dance', 'soul', 'blue', 'gold',
        'time', 'life', 'free', 'high', 'run', 'fly', 'star', 'sun', 'moon', 'home',
        'world', 'way', 'light', 'dark', 'wind', 'rain', 'day', 'gone', 'stay', 'move'
    ];
    
    // Pick a random search term
    const randomTerm = randomSearchTerms[Math.floor(Math.random() * randomSearchTerms.length)];
    
    console.log(`Searching for random term: ${randomTerm}`);
    
    // Use your existing search API
    fetch('/api/search', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ query: randomTerm, limit: 20 }) // <-- Add limit here
    })
    .then(response => response.json())
    .then(data => {
        console.log('Search results:', data);
        
        if (data.results && data.results.length > 0) {
            // Pick a random song from the results
            const randomSong = data.results[Math.floor(Math.random() * data.results.length)];
            
            // Update the search input
            searchInput.value = `${randomSong.title} - ${randomSong.artist}`;
            console.log(`Selected random song: ${randomSong.title} - ${randomSong.artist}`);
            
            // Trigger the search result selection logic
            const albumCover = document.getElementById('albumCover');
            const record = document.getElementById('record');
            const recordArm = document.getElementById('recordArm');
            const recommendationBox = document.querySelector('.recommendationBox');
            
            // Update record player
            if (albumCover && randomSong.album_cover) {
                albumCover.innerHTML = `<img src="${randomSong.album_cover}" alt="${randomSong.title} by ${randomSong.artist}">`;
            }
            
            // Start record playing
            if (record && !window.isPlaying) {
                window.isPlaying = true;
                record.classList.add('playing');
                if (recordArm) recordArm.style.transform = 'rotate(-15deg)';
            }
            
            // Get recommendation settings
            const timeframeKnob = document.getElementById('timeframeKnob');
            const genreKnob = document.getElementById('genreKnob');
            const recommendationSlider = document.getElementById('recommendationSlider');
            
            const timeframes = ['Any', '60s', '70s', '80s', '90s', '2000s', '2010s', '2020s'];
            const genres = ['Any', 'Rock', 'Pop', 'Hip-Hop', 'Electronic', 'Jazz', 'Classical', 'R&B', 'Country', 'Metal'];
            
            const timeframe = timeframes[parseInt((timeframeKnob && timeframeKnob.dataset.value) || 0)];
            const genre = genres[parseInt((genreKnob && genreKnob.dataset.value) || 0)];
            const count = parseInt((recommendationSlider && recommendationSlider.value) || 5);
            
            // Load recommendations with artist fact
            if (recommendationBox) {
                updateRecommendationWithArtistFact(recommendationBox, randomSong.title, randomSong.artist, timeframe, genre, count);
            }
            
        } else {
            console.log("No search results found");
            searchInput.value = '';
        }
        
        // Re-enable button
        button.disabled = false;
        button.textContent = "Randomize";
    })
    .catch(error => {
        console.error('Error searching for random song:', error);
        button.disabled = false;
        button.textContent = "Randomize";
    });
}

// Make sure the button click event is properly attached
document.addEventListener('DOMContentLoaded', function() {
    const randomizeBtn = document.querySelector('.randomize-button') || document.querySelector('.randomizeButton');
    if (randomizeBtn) {
        randomizeBtn.addEventListener('click', randomizeSelection);
        console.log('Randomize button event listener attached');
    } else {
        console.error('Could not find randomize button to attach event listener');
    }
    
    // Initialize the global playing state
    if (typeof window.isPlaying === 'undefined') {
        window.isPlaying = false;
    }
});

function toggleSelection(button) {
    document.querySelectorAll('.optionButton').forEach(btn => btn.classList.remove('selected'));
    button.classList.add('selected');
    console.log(`Selected option: ${button.textContent}`);

    const yearDropdown = document.querySelector('.dropDownTimePeriod');
    if (button.textContent === "Artist") {
        yearDropdown.disabled = true;
        yearDropdown.value = "";
        console.log("Year dropdown disabled for Artist selection.");
    } else {
        yearDropdown.disabled = false;
        console.log("Year dropdown enabled.");
    }
}

// --- ENHANCED SEARCH AND RECOMMENDATION SYSTEM ---
document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('songSearch');
    const searchResults = document.getElementById('searchResults');
    const albumCover = document.getElementById('albumCover');
    const record = document.getElementById('record');
    const recordArm = document.getElementById('recordArm');
    const recommendationBox = document.querySelector('.recommendationBox');
    
    // Knob controls - only timeframe and genre remain
    const timeframeKnob = document.getElementById('timeframeKnob');
    const timeframeValue = document.getElementById('timeframeValue');
    const genreKnob = document.getElementById('genreKnob');
    const genreValue = document.getElementById('genreValue');
    
    // Slider
    const recommendationSlider = document.getElementById('recommendationSlider');
    const sliderValue = document.getElementById('sliderValue');
    
    let typingTimer;
    const typingDelay = 500;
    
    // Timeframe options
    const timeframes = ['Any', '60s', '70s', '80s', '90s', '2000s', '2010s', '2020s'];
    
    // Genre options
    const genres = ['Any', 'Rock', 'Pop', 'Hip-Hop', 'Electronic', 'Jazz', 'Classical', 'R&B', 'Country', 'Metal'];

    // Track whether a song is playing
    let isPlaying = false;
    
    // Add cursor:pointer to record CSS if record element exists
    if (record) {
        record.style.cursor = 'pointer';
        
        // Function to toggle play/stop
        function togglePlayState() {
            isPlaying = !isPlaying;
            
            if (isPlaying) {
                record.classList.add('playing');
                if (recordArm) recordArm.style.transform = 'rotate(-15deg)';
            } else {
                record.classList.remove('playing');
                if (recordArm) recordArm.style.transform = 'rotate(-90deg)';
            }
        }
        
        // Make record clickable
        record.addEventListener('click', togglePlayState);
    }
    
    // Initialize knob positions
    function rotateKnob(knob, value, maxValue) {
        if (!knob) return;
        const rotation = value * (270 / maxValue) - 135;
        knob.style.transform = `rotate(${rotation}deg)`;
    }
    
    // Initialize knobs if they exist
    if (timeframeKnob && timeframeValue) {
        rotateKnob(timeframeKnob, timeframeKnob.dataset.value || 0, timeframes.length - 1);
        timeframeValue.textContent = timeframes[timeframeKnob.dataset.value || 0];
    }
    
    if (genreKnob && genreValue) {
        rotateKnob(genreKnob, genreKnob.dataset.value || 0, genres.length - 1);
        genreValue.textContent = genres[genreKnob.dataset.value || 0];
    }
    
    // Improved knob event listeners
    function setupKnob(knob, valueDisplay, options) {
        if (!knob || !valueDisplay) return;
        
        let isDragging = false;
        let startAngle = 0;
        let startRotation = 0;
        let currentRotation = 0;
        let knobRect = knob.getBoundingClientRect();
        let knobCenter = {
            x: knobRect.left + knobRect.width / 2,
            y: knobRect.top + knobRect.height / 2
        };
        
        // Add visual indication that knobs are interactive
        knob.style.cursor = 'grab';
        
        // Get angle between points
        function getAngle(x1, y1, x2, y2) {
            return Math.atan2(y2 - y1, x2 - x1) * (180 / Math.PI);
        }
        
        // Update knob rotation and value display
        function updateKnobValue(rotation) {
            // Normalize rotation to 0-270 range (-135 to +135 degrees)
            let normalizedRotation = rotation;
            while (normalizedRotation < -135) normalizedRotation += 360;
            while (normalizedRotation > 135) normalizedRotation -= 360;
            
            // Clamp to valid range
            normalizedRotation = Math.max(-135, Math.min(135, normalizedRotation));
            
            // Convert to 0-270 scale
            const normalizedAngle = normalizedRotation + 135;
            
            // Calculate value based on angle
            const value = Math.round(normalizedAngle / (270 / (options.length - 1)));
            
            // Update knob
            knob.style.transform = `rotate(${normalizedRotation}deg)`;
            knob.dataset.value = value;
            valueDisplay.textContent = options[value];
            
            return normalizedRotation;
        }
        
        knob.addEventListener('mousedown', (e) => {
            e.preventDefault();
            
            // Update knob center position
            knobRect = knob.getBoundingClientRect();
            knobCenter = {
                x: knobRect.left + knobRect.width / 2,
                y: knobRect.top + knobRect.height / 2
            };
            
            // Get initial angle
            startAngle = getAngle(knobCenter.x, knobCenter.y, e.clientX, e.clientY);
            
            // Get current rotation from transform or default to 0
            const transform = window.getComputedStyle(knob).getPropertyValue('transform');
            let matrix = new DOMMatrix(transform);
            startRotation = Math.atan2(matrix.b, matrix.a) * (180 / Math.PI);
            currentRotation = startRotation;
            
            isDragging = true;
            knob.style.cursor = 'grabbing';
            document.body.style.cursor = 'grabbing';
            
            knob.classList.add('knob-active');
        });
        
        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            
            // Calculate new angle
            const currentAngle = getAngle(knobCenter.x, knobCenter.y, e.clientX, e.clientY);
            const angleDelta = currentAngle - startAngle;
            
            // Calculate new rotation
            let newRotation = startRotation + angleDelta;
            
            // Update knob position and value
            currentRotation = updateKnobValue(newRotation);
        });
        
        document.addEventListener('mouseup', () => {
            if (isDragging) {
                isDragging = false;
                knob.style.cursor = 'grab';
                document.body.style.cursor = 'default';
                knob.classList.remove('knob-active');
                
                // Update start positions for next drag
                startRotation = currentRotation;
            }
        });
        
        // Click to increment/decrement
        knob.addEventListener('click', (e) => {
            if (e.target !== knob) return; // Make sure we clicked on the knob itself
            
            // Update knob center position
            knobRect = knob.getBoundingClientRect();
            knobCenter = {
                x: knobRect.left + knobRect.width / 2,
                y: knobRect.top + knobRect.height / 2
            };
            
            // Determine if click was on left or right half
            const isRightSide = e.clientX > knobCenter.x;
            
            // Get current value
            const currentValue = parseInt(knob.dataset.value || 0);
            
            // Calculate new value
            let newValue;
            if (isRightSide) {
                newValue = Math.min(currentValue + 1, options.length - 1);
            } else {
                newValue = Math.max(currentValue - 1, 0);
            }
            
            // Update knob
            const newRotation = (newValue * (270 / (options.length - 1))) - 135;
            knob.style.transform = `rotate(${newRotation}deg)`;
            knob.dataset.value = newValue;
            valueDisplay.textContent = options[newValue];
            
            // Update start rotation for next drag
            startRotation = newRotation;
        });
    }
    
    // Set up all knobs
    setupKnob(timeframeKnob, timeframeValue, timeframes);
    setupKnob(genreKnob, genreValue, genres);
    
    // Slider event listener
    if (recommendationSlider && sliderValue) {
        recommendationSlider.addEventListener('input', function() {
            sliderValue.textContent = this.value;
        });
    }
    
    // Enhanced search input event listener
    if (searchInput && searchResults) {
        searchInput.addEventListener('input', function() {
            clearTimeout(typingTimer);
            
            const query = searchInput.value.trim();
            
            if (query) {
                // Show the loading message in search results
                searchResults.innerHTML = '<div class="searchResultItem"><div class="searchResultItem-content"><p class="searching-message">Searching...</p></div></div>';
                searchResults.style.display = 'block';
                
                // Force high z-index and proper positioning
                searchResults.style.position = 'absolute';
                searchResults.style.zIndex = '9999';
                searchResults.style.top = '100%';
                searchResults.style.left = '0';
                searchResults.style.right = '0';
                
                typingTimer = setTimeout(() => {
                    // Make an actual API call
                    fetch('/api/search', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ query: query, limit: 20 }) // <-- Add limit here
                    })
                    .then(response => response.json())
                    .then(data => {
                        searchResults.innerHTML = '';
                        
                        // Maintain z-index after clearing content
                        searchResults.style.position = 'absolute';
                        searchResults.style.zIndex = '9999';
                        searchResults.style.top = '100%';
                        searchResults.style.left = '0';
                        searchResults.style.right = '0';
                        
                        // Check if the response contains results
                        if (data.results && data.results.length > 0) {
                            data.results.forEach(track => {
                                const div = document.createElement('div');
                                div.className = 'searchResultItem';
                                div.setAttribute('data-title', track.title);
                                div.setAttribute('data-artist', track.artist);
                                div.setAttribute('data-album-cover', track.album_cover);
                                
                                // Create enhanced search result with background and styling
                                const bg = document.createElement('div');
                                bg.className = 'searchResultItem-bg';
                                bg.style.backgroundImage = `url("${track.album_cover}")`;
                                
                                const content = document.createElement('div');
                                content.className = 'searchResultItem-content';
                                
                                const artwork = document.createElement('div');
                                artwork.className = 'searchResultItem-artwork';
                                
                                const img = document.createElement('img');
                                img.src = track.album_cover;
                                img.alt = `${track.title} album cover`;
                                artwork.appendChild(img);
                                
                                const info = document.createElement('div');
                                info.className = 'searchResultItem-info';
                                
                                const title = document.createElement('p');
                                title.className = 'searchResultItem-title';
                                title.textContent = track.title;
                                
                                const artist = document.createElement('p');
                                artist.className = 'searchResultItem-artist';
                                artist.textContent = track.artist;
                                
                                info.appendChild(title);
                                info.appendChild(artist);
                                content.appendChild(artwork);
                                content.appendChild(info);
                                
                                div.appendChild(bg);
                                div.appendChild(content);
                                searchResults.appendChild(div);
                            });
                        } else {
                            searchResults.innerHTML = '<div class="searchResultItem"><div class="searchResultItem-content"><p class="searching-message">No results found.</p></div></div>';
                        }
                    })
                    .catch(error => {
                        console.error('Error searching:', error);
                        searchResults.innerHTML = '<div class="searchResultItem"><div class="searchResultItem-content"><p>Error searching. Try again.</p></div></div>';
                    });
                }, typingDelay);
            } else {
                searchResults.innerHTML = '';
                searchResults.style.display = 'none';
            }
        });
        
        // Enhanced hide search results when clicking outside
        document.addEventListener('click', function(event) {
            if (!searchInput.contains(event.target) && !searchResults.contains(event.target)) {
                searchResults.style.display = 'none';
            }
        });
        
        // Show search results when focusing on input (if there's content)
        searchInput.addEventListener('focus', function() {
            if (searchResults.innerHTML.trim() !== '') {
                searchResults.style.display = 'block';
                // Re-apply z-index styling
                searchResults.style.position = 'absolute';
                searchResults.style.zIndex = '9999';
                searchResults.style.top = '100%';
                searchResults.style.left = '0';
                searchResults.style.right = '0';
            }
        });
        
        // Enhanced search result click handler
        searchResults.addEventListener('click', function(event) {
            const clicked = event.target.closest('.searchResultItem');
            if (!clicked) return;
            
            const title = clicked.getAttribute('data-title');
            const artist = clicked.getAttribute('data-artist');
            const albumCoverUrl = clicked.getAttribute('data-album-cover');
            
            if (title && artist) {
                // Update the record player with the selected song if elements exist
                if (albumCover) {
                    albumCover.innerHTML = `<img src="${albumCoverUrl}" alt="${title} by ${artist}">`;
                }
                searchInput.value = `${title} - ${artist}`;
                searchResults.style.display = 'none';

                // Start the record playing if record player exists
                if (record && !isPlaying) {
                    isPlaying = true;
                    record.classList.add('playing');
                    if (recordArm) recordArm.style.transform = 'rotate(-15deg)';
                }
                
                // Get current timeframe, genre and recommendations count
                const timeframe = timeframes[parseInt((timeframeKnob && timeframeKnob.dataset.value) || 0)];
                const genre = genres[parseInt((genreKnob && genreKnob.dataset.value) || 0)];
                const count = parseInt((recommendationSlider && recommendationSlider.value) || 5);
                
                // Show loading in recommendation box and fetch both artist fact and recommendations
                if (recommendationBox) {
                    updateRecommendationWithArtistFact(recommendationBox, title, artist, timeframe, genre, count);
                }
            }
        });
    }
});

// --- PICK OF THE WEEK FUNCTIONALITY ---
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Pick of the Week
    initializePickOfTheWeek();
});

// Configuration: Add new weeks here as they come
const PICK_HISTORY = [
    {
        id: "2025-07-28",
        searchQuery: "The Bends Radiohead",
        albumTitle: "The Bends",
        artistName: "Radiohead",
        weekOf: "July 28, 2025",
        description: "...",
        isCurrent: true
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
        searchQuery: "Tapestry Carol King",
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
        searchQuery: "Led Zeppelin IV Led Zeppelin",
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
        searchQuery: "Thriller Michael Jackson",
        albumTitle: "Thriller",
        artistName: "Michael Jackson",
        weekOf: "June 9, 2025",
        description: "The watershed moment in pop music history: an album that defined global pop culture with blockbuster hits like “Thriller,” “Billie Jean,” and “Beat It.” Blending pop, R&B, funk, and rock, it showcases cinematic production, groundbreaking dance tracks, and a universal appeal that continues to influence music today."
    },
    {
        id: "2025-06-02",
        searchQuery: "Appetite for Destruction Guns N Roses",
        albumTitle: "Appetite for Destruction",
        artistName: "Guns N Roses",
        weekOf: "June 2, 2025",
        description: "Raw, rebellious, and electrifying, this debut album ignited late‑’80s hard rock with fiery songs such as “Welcome to the Jungle,” “Sweet Child o’ Mine,” and “Paradise City.” Featuring gritty lyrics, searing guitar solos, and an authentic street‑wise attitude, it transformed rock with uncompromised energy and swagger."
    },
    {
        id: "2025-05-26",
        searchQuery: "The Dark Side of the Moon Pink Floyd",
        albumTitle: "The Dark Side of the Moon",
        artistName: "Pink Floyd",
        weekOf: "May 26, 2025",
        description: "A genre‑defining progressive/psychedelic rock concept album from March 1973 that explores time, money, mental health, death, consumerism, and societal alienation. It interweaves ambient soundscapes, tape loops, synthesizers, and interview snippets into a seamless emotional journey from “Speak to Me” to “Eclipse,” all bookended by a heartbeat motif. With iconic tracks like “Time,” “Money,” “Us and Them,” and “Brain Damage,” it became one of the best-selling and most influential albums ever, certified multi-platinum and sustaining legendary status for decades"
    },
];

// Store loaded song data to avoid re-fetching
let songCache = {};
let displayedPickId = null; // Track which pick is currently displayed at the top

function initializePickOfTheWeek() {
    const pickSection = document.querySelector('.pick-of-week-section');
    if (!pickSection) {
        console.error('Pick of the Week section not found');
        return;
    }
    
    // Show loading state
    pickSection.innerHTML = `
        <div class="pick-loading">
            <h2>Pick of the Week</h2>
            <p>Loading this week's pick...</p>
        </div>
    `;
    
    // Load the current pick (first item in history or the one marked as current)
    const currentPick = PICK_HISTORY.find(pick => pick.isCurrent) || PICK_HISTORY[0];
    displayedPickId = currentPick.id;
    
    // Load all picks
    loadAllPicks();
}

function loadAllPicks() {
    const pickSection = document.querySelector('.pick-of-week-section');
    
    // Create the main structure
    pickSection.innerHTML = `
        <div class="pick-of-week-container">
            <h2>Pick of the Week</h2>
            
            <!-- Main featured pick -->
            <div class="featured-pick-container">
                <div class="pick-loading-inline">
                    <p>Loading this week's pick...</p>
                </div>
            </div>
            
            <!-- Horizontal scroll list of past picks -->
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
    
    // Load songs for all picks
    const loadPromises = PICK_HISTORY.map(pick => loadSongData(pick));
    
    Promise.all(loadPromises).then(() => {
        renderFeaturedPick();
        renderPastPicks();
    }).catch(error => {
        console.error('Error loading picks:', error);
        showPickError('Failed to load picks');
    });
}

function loadSongData(pickConfig) {
    // Return cached data if available
    if (songCache[pickConfig.id]) {
        return Promise.resolve(songCache[pickConfig.id]);
    }
    
    return fetch('/api/search', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ query: pickConfig.searchQuery })
    })
    .then(response => response.json())
    .then(data => {
        if (data.results && data.results.length > 0) {
            // Try to find the best match for the album
            let bestMatch = data.results[0];
            if (pickConfig.albumTitle && pickConfig.artistName) {
                const exactMatch = data.results.find(result =>
                    result.title.toLowerCase().includes(pickConfig.albumTitle.toLowerCase()) &&
                    result.artist.toLowerCase().includes(pickConfig.artistName.toLowerCase())
                );
                if (exactMatch) bestMatch = exactMatch;
            }
            const albumData = {
                song: {
                    title: pickConfig.albumTitle || bestMatch.title,
                    artist: pickConfig.artistName || bestMatch.artist,
                    album_cover: bestMatch.album_cover
                },
                config: pickConfig
            };
            songCache[pickConfig.id] = albumData;
            return albumData;
        } else {
            throw new Error(`Album not found for ${pickConfig.weekOf}`);
        }
    });
}

function renderFeaturedPick() {
    const featuredContainer = document.querySelector('.featured-pick-container');
    const pickData = songCache[displayedPickId];
    
    if (!pickData) {
        featuredContainer.innerHTML = '<p class="pick-error">Failed to load featured album</p>';
        return;
    }
    
    const { song, config } = pickData;
    const isCurrentWeek = config.isCurrent;

    // Use album search links instead of song search
    const spotifyAlbumSearch = `https://open.spotify.com/search/${encodeURIComponent('album:"' + song.title + '" artist:"' + song.artist + '"')}`;
    const appleAlbumSearch = `https://music.apple.com/us/search?term=${encodeURIComponent(song.title + ' ' + song.artist)}&entity=album`;

    featuredContainer.innerHTML = `
        <div class="featured-pick-card">
            <div class="featured-pick-image">
                <img src="${song.album_cover}" alt="${song.title} by ${song.artist}" class="featured-cover-image">
                ${isCurrentWeek ? '<div class="current-pick-badge">This Week</div>' : '<div class="past-pick-badge">Past Pick</div>'}
            </div>
            
            <div class="featured-pick-info">
                <div class="featured-pick-details">
                    <p class="featured-pick-week">Week of ${config.weekOf}</p>
                    <h3 class="featured-pick-title">${song.title}</h3>
                    <p class="featured-pick-artist">by ${song.artist}</p>
                    ${config.description ? `<p class="featured-pick-description">${config.description}</p>` : ''}
                </div>
                
                <div class="featured-music-links">
                    <a href="${spotifyAlbumSearch}" 
                       target="_blank" rel="noopener noreferrer" class="music-link spotify">
                        <span class="link-icon">♪</span> Listen on Spotify
                    </a>
                    <a href="${appleAlbumSearch}" 
                       target="_blank" rel="noopener noreferrer" class="music-link apple">
                        <span class="link-icon">♪</span> Listen on Apple Music
                    </a>
                </div>
            </div>
        </div>
    `;
}

function renderPastPicks() {
    const pastPicksScroll = document.querySelector('.past-picks-scroll');
    
    // Get all picks except the currently displayed one
    const pastPicks = PICK_HISTORY.filter(pick => pick.id !== displayedPickId);
    
    if (pastPicks.length === 0) {
        pastPicksScroll.innerHTML = '<p class="no-past-picks">No past albums to show</p>';
        return;
    }
    
    let pastPicksHTML = '';
    
    pastPicks.forEach(pick => {
        const pickData = songCache[pick.id];
        if (pickData) {
            const { song, config } = pickData;
            pastPicksHTML += `
                <div class="past-pick-card" data-pick-id="${pick.id}">
                    <div class="past-pick-content">
                        <div class="past-pick-image">
                            <img src="${song.album_cover}" alt="${song.title} by ${song.artist}" class="past-cover-image">
                            ${config.isCurrent ? '<div class="current-indicator">Current</div>' : ''}
                        </div>
                        <div class="past-pick-info">
                            <p class="past-pick-week">${config.weekOf}</p>
                            <h4 class="past-pick-title">${song.title}</h4>
                            <p class="past-pick-artist">${song.artist}</p>
                        </div>
                    </div>
                </div>
            `;
        }
    });
    
    pastPicksScroll.innerHTML = pastPicksHTML;
    
    // Add click event listeners to past pick cards
    const pastPickCards = pastPicksScroll.querySelectorAll('.past-pick-card');
    pastPickCards.forEach(card => {
        card.addEventListener('click', function() {
            const pickId = this.dataset.pickId;
            if (pickId && pickId !== displayedPickId) {
                switchToPickWithAnimation(pickId);
            }
        });
        
        // Add hover effect
        card.style.cursor = 'pointer';
    });
}

function switchToPickWithAnimation(newPickId) {
    const featuredContainer = document.querySelector('.featured-pick-container');
    
    // Add fade-out animation
    featuredContainer.style.opacity = '0.5';
    featuredContainer.style.transform = 'scale(0.95)';
    
    setTimeout(() => {
        // Update the displayed pick
        displayedPickId = newPickId;
        
        // Re-render both sections
        renderFeaturedPick();
        renderPastPicks();
        
        // Add fade-in animation
        featuredContainer.style.opacity = '1';
        featuredContainer.style.transform = 'scale(1)';
    }, 200);
}

function showPickError(message) {
    const pickSection = document.querySelector('.pick-of-week-section');
    
    pickSection.innerHTML = `
        <div class="pick-error-container">
            <h2>Album of the Week</h2>
            <p class="error-message">${message}</p>
            <button onclick="initializePickOfTheWeek()" class="pick-retry-btn">Try Again</button>
        </div>
    `;
}

// Helper function to add a new album pick (for future weeks)
function addNewPick(searchQuery, weekOf, description, makeCurrent = true) {
    // Remove current flag from all picks if making this one current
    if (makeCurrent) {
        PICK_HISTORY.forEach(pick => pick.isCurrent = false);
    }
    
    // Create new pick object
    const newPick = {
        id: new Date(weekOf).toISOString().split('T')[0], // Convert date to YYYY-MM-DD format
        searchQuery: searchQuery,
        weekOf: weekOf,
        description: description,
        isCurrent: makeCurrent
    };
    
    // Add to beginning of array (most recent first)
    PICK_HISTORY.unshift(newPick);
    
    // Clear cache for the new pick
    delete songCache[newPick.id];
    
    // Reload the pick section if it exists
    const pickSection = document.querySelector('.pick-of-week-section');
    if (pickSection) {
        initializePickOfTheWeek();
    }
}

// Helper function to manually switch to a specific pick (useful for testing)
function switchToPick(pickId) {
    const pick = PICK_HISTORY.find(p => p.id === pickId);
    if (pick && songCache[pickId]) {
        switchToPickWithAnimation(pickId);
    } else {
        console.error(`Pick with ID ${pickId} not found or not loaded`);
    }
}

// --- SEARCH FUNCTIONALITY ENHANCEMENTS ---
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('songSearch');
    const clearBtn = document.getElementById('clearSearch');
    const searchResults = document.getElementById('searchResults');
    if (searchInput && clearBtn) {
        // Show/hide the clear button based on input value
        searchInput.addEventListener('input', function() {
            clearBtn.style.display = this.value ? 'block' : 'none';
        });

        // Clear the input and hide results when the button is clicked
        clearBtn.addEventListener('mousedown', function(e) {
            // Use mousedown instead of click to prevent input blur
            e.preventDefault();
            searchInput.value = '';
            clearBtn.style.display = 'none';
            searchInput.focus();
            if (searchResults) {
                searchResults.style.display = 'none';
                searchResults.innerHTML = '';
            }
            // Optionally, trigger input event if you have logic tied to it
            searchInput.dispatchEvent(new Event('input'));
        });
    }
});
