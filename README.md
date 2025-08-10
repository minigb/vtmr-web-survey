# VTMR Web Survey

This project is a web-based survey tool for Video-to-Music Retrieval (VTMR) research. It allows researchers to conduct pairwise comparison tests where users select their preferred video from a pair of pre-combined video/audio files.

## Features

- **Multiple Surveys**: Configure multiple, independent surveys, each with its own set of videos.
- **Pairwise Comparisons**: Automatically generates all possible pairs of videos for each survey (`nC2`).
- **Dynamic Frontend**: A single-page application that dynamically loads and presents all video pairs in a random order.
- **Flexible Configuration**: Easily add or modify surveys by editing a JSON configuration file.
- **Detailed Data Collection**: Records user choices with timestamps, and full details of the video pair shown.

## How It Works

1.  **Configuration**: Surveys are defined in `config/surveys.json`. Each survey consists of `n` pre-combined video files.
2.  **Backend API**: The Node.js/Express backend reads the configuration, generates all possible video pairs, shuffles them, and serves them to the frontend. It also handles vote submissions.
3.  **Frontend Interface**: The frontend fetches the shuffled list of all video pairs and presents them to the user one by one for voting.
4.  **Data Storage**: All responses are stored in `data/results.json`.

## Usage

### 1. Add Your Media Files

-   Place your pre-combined video files (with audio) in the `public/videos/` directory.

### 2. Configure Your Surveys

Edit the `config/surveys.json` file to define your surveys. Each survey object has the following structure:

```json
{
  "id": "unique_survey_id",
  "name": "Survey Name",
  "videos": [
    { "id": "unique_video_id_1", "file": "videos/your_video_1.mp4", "description": "Internal description of video 1" },
    { "id": "unique_video_id_2", "file": "videos/your_video_2.mp4", "description": "Internal description of video 2" },
    { "id": "unique_video_id_3", "file": "videos/your_video_3.mp4", "description": "Internal description of video 3" }
  ]
}
```

-   **`id`**: A unique identifier for the survey (e.g., `"survey_01"`).
-   **`name`**: The display name of the survey.
-   **`videos`**: An array of pre-combined video objects.
    -   **`id`**: A unique identifier for the video.
    -   **`file`**: The path to the video file.
    -   **`description`**: An internal note for you to identify the video (not shown to users).

### 3. Run the Application

Use the provided deployment script to build and run the application in a Docker container:

```bash
./dev-deploy.sh
```

### 4. Access the Survey

Open your web browser and navigate to the application URL (e.g., `http://localhost:5555` or `http://your_server_ip:5555`).

## Development

This project uses a Docker-based development workflow. See `DEVELOPMENT.md` for detailed instructions on how to set up your environment, make changes, and deploy the application.

## Data Analysis

The survey results are stored in `data/results.json`. Each entry in the JSON array represents a single vote and contains the following information:

```json
{
  "userId": "participant_01",
  "pair": [
    { "id": "video_01a", "file": "...", "description": "..." },
    { "id": "video_01b", "file": "...", "description": "..." }
  ],
  "choice": "A",
  "winner": { "id": "video_01a", "file": "...", "description": "..." },
  "loser": { "id": "video_01b", "file": "...", "description": "..." },
  "ts": "2023-10-27T12:00:00.000Z",
  "ip": "::1"
}
```

-   **`userId`**: The ID of the participant who submitted the vote.
-   **`pair`**: The pair of videos that were presented to the user.
-   **`choice`**: The option the user selected (`"A"` or `"B"`).
-   **`winner`**: The full object of the video the user chose.
-   **`loser`**: The full object of the video the user did not choose.
-   **`ts`**: The timestamp of the vote.
-   **`ip`**: The IP address of the user.
