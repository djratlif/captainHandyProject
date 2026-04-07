document.addEventListener('DOMContentLoaded', () => {

    // Elements
    const screens = {
        intro: document.getElementById('intro-screen'),
        loading: document.getElementById('loading-screen'),
        reader: document.getElementById('reader-screen')
    };

    const ideaInput = document.getElementById('comic-idea');
    const generateBtn = document.getElementById('generate-btn');

    const loadingHeader = document.getElementById('loading-header');
    const loadingText = document.getElementById('loading-text');
    const progressContainer = document.getElementById('progress-container');

    const panelImg = document.getElementById('current-panel-img');
    const panelCaption = document.getElementById('current-panel-caption');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const restartBtn = document.getElementById('restart-btn');

    // State
    let currentComicId = null;
    let panelsData = [];
    let currentPanelIdx = 0;

    function switchScreen(screenKey) {
        Object.values(screens).forEach(el => el.classList.remove('active'));
        screens[screenKey].classList.add('active');
    }

    async function startGeneration() {
        const idea = ideaInput.value.trim();

        switchScreen('loading');
        loadingHeader.textContent = "Writing Script...";
        loadingText.textContent = "Consulting the AI storywriters.";
        progressContainer.innerHTML = '';

        try {
            // 1. Brainstorm API
            const res = await fetch('/api/brainstorm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ idea })
            });
            const data = await res.json();

            if (data.error) throw new Error(data.error);

            currentComicId = data.comic_id;
            panelsData = data.panels;

            // 2. Generate each panel sequentially
            loadingHeader.textContent = "Drawing Panels...";
            loadingText.textContent = `Pinging Replicate Custom AI Model...`;

            for (let i = 0; i < panelsData.length; i++) {
                const progressEl = document.createElement('p');
                progressEl.textContent = `Panel ${i + 1}/${panelsData.length}: Starting...`;
                progressContainer.appendChild(progressEl);

                try {
                    let attempts = 0;
                    let panelData = null;

                    while (attempts < 4) {
                        const panelRes = await fetch(`/api/generate_panel/${currentComicId}/${i}`, {
                            method: 'POST'
                        });
                        panelData = await panelRes.json();

                        if (!panelData.error) break; // Success!

                        // If it's an error, assume it's a rate limit and wait 15 seconds before retrying
                        console.log(`Panel ${i + 1} failed: ${panelData.error}. Retrying...`);
                        progressEl.textContent = `Panel ${i + 1}/${panelsData.length}: Rate limited. Waiting 15s to retry...`;
                        progressEl.style.color = '#f5b041'; // Warning color
                        await new Promise(r => setTimeout(r, 15000));
                        progressEl.textContent = `Panel ${i + 1}/${panelsData.length}: Retrying...`;
                        progressEl.style.color = '#ffffff';
                        attempts++;
                    }

                    if (panelData.error) throw new Error(panelData.error);

                    panelsData[i].image_url = panelData.image_url;
                    progressEl.textContent = `Panel ${i + 1}/${panelsData.length}: Complete! ✨`;
                    progressEl.style.color = '#00f2fe';

                    // Respect Replicate API rate limits (6 requests / min burst limit)
                    if (i < panelsData.length - 1) {
                        const waitEl = document.createElement('p');
                        waitEl.textContent = "⏳ Cooling down API (6s)...";
                        waitEl.style.color = "#a0a5b5";
                        progressContainer.appendChild(waitEl);
                        await new Promise(r => setTimeout(r, 6000));
                        waitEl.remove();
                    }

                } catch (err) {
                    progressEl.textContent = `Panel ${i + 1}/${panelsData.length}: Skipped (Error)`;
                    progressEl.style.color = '#ff4b4b';
                    console.error(err);
                }
            }

            // 3. Complete! Show Reader
            loadingHeader.textContent = "Complete!";
            setTimeout(() => initializeReader(), 1000);

        } catch (error) {
            alert("Error: " + error.message);
            switchScreen('intro');
        }
    }

    function initializeReader() {
        currentPanelIdx = 0;
        updateReaderUI();
        switchScreen('reader');
    }

    function updateReaderUI() {
        if (!panelsData[currentPanelIdx] || !panelsData[currentPanelIdx].image_url) {
            panelImg.src = "";
            panelCaption.textContent = "Panel generation failed.";
        } else {
            panelImg.src = panelsData[currentPanelIdx].image_url;
            panelCaption.textContent = panelsData[currentPanelIdx].caption;
        }

        // Nav Btns
        if (currentPanelIdx === 0) {
            prevBtn.classList.add('hidden');
        } else {
            prevBtn.classList.remove('hidden');
        }

        if (currentPanelIdx === panelsData.length - 1) {
            nextBtn.classList.add('hidden');
        } else {
            nextBtn.classList.remove('hidden');
        }
    }

    // Binding events
    generateBtn.addEventListener('click', startGeneration);
    ideaInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') startGeneration();
    });

    prevBtn.addEventListener('click', () => {
        if (currentPanelIdx > 0) {
            currentPanelIdx--;
            updateReaderUI();
        }
    });

    nextBtn.addEventListener('click', () => {
        if (currentPanelIdx < panelsData.length - 1) {
            currentPanelIdx++;
            updateReaderUI();
        }
    });

    restartBtn.addEventListener('click', () => {
        ideaInput.value = '';
        currentComicId = null;
        panelsData = [];
        progressContainer.innerHTML = '';
        switchScreen('intro');
    });
});
