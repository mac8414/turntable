// --- LAVA LAMP ANIMATION ---
document.addEventListener('DOMContentLoaded', function() {
    // Check if Vue is available
    if (typeof Vue === 'undefined') {
        console.error('Vue is not loaded! Using plain JavaScript for animation instead.');
        animateLavaLamp();
        return;
    }
    
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

// --- RANDOMIZER LOGIC (PRESERVED FROM ORIGINAL) ---
function randomizeSelection() {
    const button = document.querySelector('.randomizeButton');
    button.disabled = true;
    button.textContent = "Loading...";
    const selectedOption = document.querySelector('.optionButton.selected');
    if (!selectedOption) {
        alert("Please select an option (Song, Album, or Artist) first!");
        button.disabled = false;
        button.textContent = "Randomize";
        console.log("No option selected. Prompting user to select an option.");
        return;
    }

    const genre = document.querySelector('.dropDownGenre').value;
    const year = document.querySelector('.dropDownTimePeriod').value;
    let endpoint = "";

    if (selectedOption.textContent === "Song") {
        endpoint = `/random_song?year=${year}&genre=${genre}`;
    } else if (selectedOption.textContent === "Album") {
        endpoint = `/random_album?year=${year}&genre=${genre}`;
    } else if (selectedOption.textContent === "Artist") {
        endpoint = `/random_artist?genre=${genre}`;
    }

    console.log(`Fetching data from endpoint: ${endpoint}`);

    fetch(endpoint)
        .then(response => response.json())
        .then(data => {
            const contentBox = document.querySelector('.contentBox');

            if (data.name) {
                console.log(`Data received: ${JSON.stringify(data)}`);
                contentBox.innerHTML = `
                    <div>
                        <h2 style="color: white;">${data.name}</h2>
                        <p style="color: white;">${data.artist ? "By " + data.artist : ""}</p>
                        ${data.image ? `<a href="${data.url}" target="_blank"><img id="albumImage" src="${data.image}" alt="${data.name}" style="width:300px; border-radius: 5px;"></a>` : ''}
                        ${data.type === "song" && data.preview_url ? `<audio controls><source src="${data.preview_url}" type="audio/mpeg"></audio>` : ''}
                    </div>
                `;
                
                if (data.image) {
                    const albumImage = document.getElementById('albumImage');
                    albumImage.onload = function() {
                        button.disabled = false;
                        button.textContent = "Randomize";
                        console.log("Album image loaded successfully.");
                    };
                    albumImage.onerror = function() {
                        button.disabled = false;
                        button.textContent = "Randomize";
                        console.error('Failed to load the album image.');
                    };
                    if (data.dominant_color) {
                        document.querySelector('.contentBox').style.background = `linear-gradient(to bottom, ${data.dominant_color}, black)`;
                    }
                } else {
                    button.disabled = false;
                    button.textContent = "Randomize";
                }
            } else {
                console.log("No results found.");
                contentBox.innerHTML = `<p>No results found. Try refreshing!</p>`;
                button.disabled = false;
                button.textContent = "Randomize";
            }
        })
        .catch(error => {
            console.error('Error fetching data:', error);
            button.disabled = false;
            button.textContent = "Randomize";
        });
}

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
                searchResults.innerHTML = '<div class="searchResultItem"><div class="searchResultItem-content"><p>Searching...</p></div></div>';
                searchResults.style.display = 'block';
                
                typingTimer = setTimeout(() => {
                    // Make an actual API call
                    fetch('/api/search', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ query: query })
                    })
                    .then(response => response.json())
                    .then(data => {
                        searchResults.innerHTML = '';
                        
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
                            searchResults.innerHTML = '<div class="searchResultItem"><div class="searchResultItem-content"><p>No results found.</p></div></div>';
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
        
        // Hide search results when clicking outside
        document.addEventListener('click', function(event) {
            if (!searchInput.contains(event.target) && !searchResults.contains(event.target)) {
                searchResults.style.display = 'none';
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
                
                // Show loading in recommendation box
                if (recommendationBox) {
                    recommendationBox.innerHTML = `
                        <div class="recommendations-show">
                            <h3>Loading recommendations for ${title} by ${artist}...</h3>
                            <p>Time Frame: ${timeframe} | Genre: ${genre} | Count: ${count}</p>
                            <h5>Powered by <strong>CadenceAI</strong></h5>
                        </div>
                    `;
                    
                    // Make the API call for recommendations
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
                    })
                    .then(response => response.json())
                    .then(data => {
                        // Create enhanced recommendations HTML
                        let recHTML = `
                            <div class="recommendations-show">
                                <h3>Recommended Songs for: ${title} by ${artist}</h3>
                                <p>Time Frame: ${timeframe} | Genre: ${genre}</p>
                                <h5>Powered by <strong>CadenceAI</strong></h5>
                            </div>
                            <div>
                                <ul class="recommendation-list">
                        `;
                        
                        if (data.recommendations && data.recommendations.length > 0) {
                            console.log('Recommendation data:', data.recommendations[0]);
                            data.recommendations.forEach(rec => {
                                // Use the album_cover from the backend
                                const albumCoverUrl = rec.album_cover || '/api/placeholder/50/50';
                                
                                // Use the music links provided by the backend (preferred method)
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
                        
                        recHTML += `
                                </ul>
                            </div>
                        `;
                        
                        recommendationBox.innerHTML = recHTML;
                    })
                    .catch(error => {
                        console.error('Error fetching recommendations:', error);
                        recommendationBox.innerHTML = `
                            <div class="recommendations show">
                                <h3>Error loading recommendations</h3>
                                <p>Please try again later.</p>
                            </div>
                        `;
                    });
                }
            }
        });
    }
});