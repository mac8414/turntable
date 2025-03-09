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

