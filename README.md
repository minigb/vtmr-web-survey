# VTMR Web Survey

This project is a web-based survey tool for Video-to-Music Retrieval (VTMR) research. It allows researchers to conduct pairwise comparison tests where users select their preferred video from a pair of pre-combined video/audio files.

## Features

- **Predefined Assignment Surveys**: Uses generated assignment files (`data/test_case_assignments_public.json`) for fixed per-user question sets.
- **Username-to-Slot Mapping**: Maps each entered username to a persistent internal user slot (`user_01` ... `user_30`).
- **Dynamic Frontend**: A single-page application that loads and presents each user's assigned pairs.
- **Detailed Data Collection**: Records user choices with timestamps, and full details of the video pair shown.

## How It Works

1.  **Username Registration**: The frontend sends a username to the backend.
2.  **Slot Mapping**: The backend maps that username to one fixed assignment slot (`user_01` ... `user_30`) and persists this mapping in `data/user_mappings.json`.
3.  **Predefined Assignment Delivery**: The backend returns the pre-generated question list for that slot from `data/test_case_assignments_public.json`.
4.  **Survey Interface**: The frontend shows those fixed pairs and collects responses.
5.  **Submission Storage**: The backend validates that submitted questions match the assigned slot, then stores responses in `data/results.json` under the mapped user ID.

## Usage

### 1. Add Your Media Files

-   Place your pre-combined video files (with audio) in the `videos/` directory.

### 2. Organize Directory Structure

Create one subdirectory per condition under `videos/`, and place candidate videos in each:

```text
videos/
  condition_a/
    video1.mp4
    video2.mp4
    video3.mp4
  condition_b/
    video1.mp4
    video2.mp4
```

Each directory must contain at least 2 compatible video files (`.mp4`, `.webm`, `.ogg`).

### 3. Run the Application

Use the provided deployment script to build and run the application in a Docker container:

```bash
./dev-deploy.sh
```

Optional security env vars:
- `RESULTS_READ_TOKEN`: enables `GET /results?token=...` (without it, `/results` is disabled).
- `ADMIN_API_TOKEN`: enables `POST /api/refresh-mappings?token=...` (without it, endpoint is disabled).

### 4. Access the Survey

Open your web browser and navigate to the application URL (e.g., `http://localhost:5555` or `http://your_server_ip:5555`).

## Development

This project uses a Docker-based development workflow. See `DEVELOPMENT.md` for detailed instructions on how to set up your environment, make changes, and deploy the application.

## Data Analysis

The survey results are stored in `data/results.json`. The file contains a single JSON object where each key is a participant's ID. Under each ID is a list of their final votes, submitted as a batch at the end of the survey.

Assignment generator outputs:
- `data/test_case_assignments_public.json` and `data/test_case_assignments_public.csv`: participant-safe (anonymous tokens only).
- `data/test_case_assignments_private_map.json`: sensitive mapping from anonymous tokens to real files/options (do not expose).
- `data/test_case_assignments.json` and `data/test_case_assignments.csv`: internal analysis versions with full labels.

```json
{
  "participant_01": [
    {
      "pair": [
        { "id": "video_01a", "file": "...", "description": "..." },
        { "id": "video_01b", "file": "...", "description": "..." }
      ],
      "choice": "A",
      "winner": { "id": "video_01a", "file": "...", "description": "..." },
      "loser": { "id": "video_01b", "file": "...", "description": "..." },
      "ts": "2023-10-27T12:00:00.000Z"
    },
    {
      "pair": [
        { "id": "video_02a", "file": "...", "description": "..." },
        { "id": "video_02c", "file": "...", "description": "..." }
      ],
      "choice": "B",
      "winner": { "id": "video_02c", "file": "...", "description": "..." },
      "loser": { "id": "video_02a", "file": "...", "description": "..." },
      "ts": "2023-10-27T12:05:10.000Z"
    }
  ]
}
```

Each vote object in the array contains:
-   **`pair`**: The pair of videos that were presented to the user.
-   **`choice`**: The option the user selected (`"A"` or `"B"`).
-   **`winner`**: The full object of the video the user chose.
-   **`loser`**: The full object of the video the user did not choose.
-   **`ts`**: The timestamp of when the vote was recorded on the client side.
