function randomizeSelection() {
    const selectedOption = document.querySelector('.optionButton.selected');
    if (!selectedOption) {
        alert("Please select an option (Song, Album, or Artist) first!");
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

    fetch(endpoint)
        .then(response => response.json())
        .then(data => {
            const contentBox = document.querySelector('.contentBox');

            if (data.name) {
                contentBox.innerHTML = `
                    <div>
                         <h2>${data.name}</h2>
                        <p>${data.artist ? "By " + data.artist : ""}</p>
                        ${data.image ? `<a href="${data.url}" target="_blank"><img src="${data.image}" alt="${data.name}" style="width:300px;"></a>` : ''}
                        ${data.type === "song" && data.preview_url ? `<audio controls><source src="${data.preview_url}" type="audio/mpeg"></audio>` : ''}
                    </div>
                `;
            } else {
                contentBox.innerHTML = `<p>No results found. Try refreshing!</p>`;
            }
        })
        .catch(error => {
            console.error('Error fetching data:', error);
        });
}


function toggleSelection(button) {
    document.querySelectorAll('.optionButton').forEach(btn => btn.classList.remove('selected'));
    button.classList.add('selected');
}

