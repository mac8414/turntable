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

    // --- Search bar logic ---
    document.addEventListener('DOMContentLoaded', function () {

        // Get references to important DOM elements
        const searchInput = document.getElementById('songSearch');
        const searchResults = document.getElementById('searchResults');
        const recommendationBox = document.querySelector('.recommendationBox');

        let typingTimer; 
        const typingDelay = 200;

        // Event listener for user input in the search field
        searchInput.addEventListener('input', function () {
            clearTimeout(typingTimer); // cancel previous timer
        
            const query = searchInput.value.trim();
        
            if (query) {
                // Set a timer to wait briefly after typing stops before making API call
                typingTimer = setTimeout(() => {
                    fetch('/api/search', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ query: query })
                    })
                    .then(response => response.json())
                    .then(data => {
                        // Double-check that input is still not empty (user could have cleared it)
                        if (searchInput.value.trim() === '') {
                            searchResults.innerHTML = ''; // Nothing should show if input is empty
                            return;
                        }

                        // Clear previous search results
                        searchResults.innerHTML = '';
                        
                        // Check if the response contains results
                        if (data.results && data.results.length > 0) {
                            data.results.forEach(track => {
                                const div = document.createElement('div');
                                div.className = 'searchResultItem';
                                div.setAttribute('data-title', track.title);
                                div.setAttribute('data-artist', track.artist);
                                div.setAttribute('data-album-cover', track.album_cover);
                                div.innerHTML = `
                                    <div style="display: flex; align-items: center; gap: 10px;">
                                        <img src="${track.album_cover}" alt="Album Cover" style="width: 50px; height: 50px; object-fit: cover; border-radius: 5px;">
                                        <p><strong>${track.title}</strong> by ${track.artist}</p>
                                    </div>
                                `;
                                searchResults.appendChild(div);
                            });
                        } else {
                            searchResults.innerHTML = '<p>No results found.</p>';
                        }
                    })
                    .catch(error => {
                        console.error('Error searching:', error);
                    });
                }, typingDelay);
            } else {
                searchResults.innerHTML = '';
            }
        });
    
        

    // --- CLICK a search result to send to /api/recommend ---
    searchResults.addEventListener('click', function (event) {

        // Check if the clicked element is a search result item
        const clicked = event.target.closest('.searchResultItem');
        if (!clicked) return;

        // Get the title and artist from the clicked item
        const title = clicked.getAttribute('data-title');
        const artist = clicked.getAttribute('data-artist');

        console.log(`Clicked song: ${title} by ${artist}`); // DEBUG LINE
        

        clearTimeout(typingTimer);

        // Clear the search input and results
        searchInput.value = '';
        searchResults.innerHTML = '';


        if (title && artist) {
            // Show loading message while recommendations are being fetched
            recommendationBox.innerHTML = `<p>Loading recommendations for: <strong>${title}</strong> by <strong>${artist}</strong>...</p>`;

            // Request recommendations from the backend API
            fetch('/api/recommend', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ track_name: title, artist_name: artist })
            })
            .then(response => response.json())
            .then(data => {
                 // Update recommendation box header with selected song info
                recommendationBox.innerHTML = `<h3>Recommended Songs for: <em>${title}</em> by <em>${artist}</em></h3>`;

                 // Display recommendations
                if (data.recommendations && data.recommendations.length > 0) {
                    const ul = document.createElement('ul');

                    // Create list items for each recommendation
                    data.recommendations.forEach(rec => {
                        const li = document.createElement('li');
                        li.textContent = `${rec.title} by ${rec.artist} (${rec.similarity_score}% match)`;
                        ul.appendChild(li);
                    });

                    // Add the recommendation list to the page
                    recommendationBox.appendChild(ul);
                } else {
                     // Display a message if no recommendations were found
                    recommendationBox.innerHTML += '<p>No recommendations found.</p>';
                }
            })
            .catch(error => {
                // Handle any errors during the recommendation fetch
                console.error('Error fetching recommendations:', error);
                recommendationBox.innerHTML = '<p>Error loading recommendations.</p>';
            });
        }
    });
});
