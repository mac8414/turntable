// --- RANDOMIZER LOGIC ---
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

// --- SEARCH BAR LOGIC + RECOMMENDATION FETCH ---
document.addEventListener('DOMContentLoaded', function () {
    const input = document.getElementById('songSearch');
    const results = document.getElementById('searchResults');
    const recommendationBox = document.querySelector('.recommendationBox');

    if (!input) return;

    input.addEventListener('input', function () {
        const query = input.value.trim();
        if (query.length < 2) {
            results.innerHTML = '';
            return;
        }

        fetch(`/spotify-search?q=${encodeURIComponent(query)}`)
            .then(res => res.json())
            .then(data => {
                results.innerHTML = '';

                if (!data.length) {
                    results.innerHTML = `<p style="color: white;">No results found.</p>`;
                    return;
                }

                data.forEach(song => {
                    const div = document.createElement('div');
                    div.innerHTML = `
                        <div style="display: flex; align-items: center; padding: 10px; cursor: pointer; border-bottom: 1px solid #ccc;">
                            <img src="${song.image}" style="width: 50px; height: 50px; border-radius: 4px; margin-right: 10px;">
                            <div style="color: white;">
                                <strong>${song.name}</strong><br>
                                <small>${song.artist}</small>
                            </div>
                        </div>
                    `;
                    div.addEventListener('click', () => {
                        input.value = `${song.name} - ${song.artist}`;
                        results.innerHTML = '';

                        // Send song to backend
                        fetch('/submit-song', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ track: song.name, artist: song.artist })
                        })
                        .then(res => res.json())
                        .then(data => {
                            recommendationBox.innerHTML = `<h3 style="color:white;">Top Recommendations for "${song.name}"</h3>`;

                            if (!data || !data.length) {
                                recommendationBox.innerHTML += `<p style="color:white;">No recommendations found.</p>`;
                                return;
                            }

                            data.forEach(rec => {
                                recommendationBox.innerHTML += `
                                    <div style="margin-bottom: 15px;">
                                        <p style="color:white;"><strong>${rec.title}</strong> by ${rec.artist}</p>
                                        ${rec.spotify_url ? `<a href="${rec.spotify_url}" target="_blank" style="color:#1DB954;">Listen on Spotify</a>` : ''}
                                        <p style="color:white; font-size: 0.9em;">Sentiment: ${rec.sentiment.label} (${(rec.sentiment.score * 100).toFixed(2)}%)</p>
                                    </div>
                                `;
                            });
                        });
                    });
                    results.appendChild(div);
                });
            });
    });
});