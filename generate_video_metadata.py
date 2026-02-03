import os
import json

# Define the path to the videos directory
VIDEOS_DIR = 'videos'

# Define the output JSON file (surveys configuration)
OUTPUT_FILE = 'config/surveys.json'

# Function to generate video metadata

def generate_video_metadata():
    surveys = []

    # Get sorted list of subdirectories to ensure consistent ordering
    subdirs = sorted([d for d in os.listdir(VIDEOS_DIR) 
                     if os.path.isdir(os.path.join(VIDEOS_DIR, d))])

    # Traverse the videos directory
    for i, subdir in enumerate(subdirs, 1):
        subdir_path = os.path.join(VIDEOS_DIR, subdir)
        videos = []
        
        # Get sorted list of video files to ensure consistent ordering
        video_files = sorted([f for f in os.listdir(subdir_path) 
                             if f.endswith(('.mp4', '.webm', '.ogg'))])
        
        for video_file in video_files:
            video_id = os.path.splitext(video_file)[0]
            videos.append({
                "id": video_id,
                "file": f"videos/{subdir}/{video_file}"
            })
        
        surveys.append({
            "id": f"survey_{int(subdir):02d}" if subdir.isdigit() else f"survey_{subdir}",
            "name": subdir,
            "videos": videos
        })

    # Create config directory if it doesn't exist
    os.makedirs('config', exist_ok=True)
    
    # Write the surveys configuration to the JSON file
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(surveys, f, indent=2)

    print(f"Surveys configuration has been generated and written to {OUTPUT_FILE}")
    print(f"Found {len(surveys)} survey directories with videos:")
    for survey in surveys:
        print(f"  - {survey['name']}: {len(survey['videos'])} videos")

# Run the function
generate_video_metadata()
