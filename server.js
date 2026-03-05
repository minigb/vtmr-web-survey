const express = require('express');
const fs = require('fs');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 5555;
const VIDEOS_DIR = path.join(__dirname, 'videos');
const VIDEO_EXTENSIONS = new Set(['.mp4', '.webm', '.ogg']);

app.use(express.static('public'));
app.use('/videos', express.static('videos'));
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
const resultsFile = path.join(dataDir, 'results.json');
if (!fs.existsSync(resultsFile) || fs.readFileSync(resultsFile, 'utf8').trim() === '') fs.writeFileSync(resultsFile, '{}', 'utf8');

// Create anonymous video mapping to hide real file paths
const videoMapping = new Map();
const reverseMapping = new Map();
let videoCatalog = [];

function shuffleInPlace(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
}

function discoverVideoCatalog() {
  if (!fs.existsSync(VIDEOS_DIR)) {
    console.warn(`Video directory not found: ${VIDEOS_DIR}`);
    return [];
  }

  const subdirs = fs.readdirSync(VIDEOS_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

  return subdirs.map((subdir) => {
    const subdirPath = path.join(VIDEOS_DIR, subdir);
    const videos = fs.readdirSync(subdirPath, { withFileTypes: true })
      .filter((entry) => entry.isFile())
      .map((entry) => entry.name)
      .filter((filename) => VIDEO_EXTENSIONS.has(path.extname(filename).toLowerCase()))
      .sort()
      .map((videoFile) => ({
        id: `${subdir}_${path.parse(videoFile).name}`,
        file: `videos/${subdir}/${videoFile}`
      }));

    return {
      id: `survey_${subdir}`,
      name: subdir,
      videos
    };
  });
}

function createAnonymousMapping() {
  videoMapping.clear();
  reverseMapping.clear();
  videoCatalog = discoverVideoCatalog();

  // Collect all video files first
  const allVideoFiles = [];
  videoCatalog.forEach((survey) => {
    survey.videos.forEach((video) => {
      allVideoFiles.push(video.file);
    });
  });

  // Create shuffled anonymous IDs
  const anonymousIds = [];
  for (let i = 1; i <= allVideoFiles.length; i++) {
    anonymousIds.push(`anon_video_${i.toString().padStart(3, '0')}`);
  }

  // Shuffle the anonymous IDs using Fisher-Yates algorithm
  shuffleInPlace(anonymousIds);

  // Map shuffled anonymous IDs to video files
  allVideoFiles.forEach((videoFile, index) => {
    const anonId = anonymousIds[index];
    videoMapping.set(anonId, videoFile);
    reverseMapping.set(videoFile, anonId);
  });

  console.log(`🔀 Created ${allVideoFiles.length} shuffled anonymous video mappings from ${videoCatalog.length} directories`);
}

// Initialize mapping at startup
createAnonymousMapping();

// Refresh mappings when video files are updated
function refreshMappings() {
  try {
    createAnonymousMapping();
    console.log('📋 Video mappings refreshed');
  } catch (error) {
    console.error('Error refreshing mappings:', error);
  }
}

// API endpoint to refresh mappings
app.post('/api/refresh-mappings', (req, res) => {
  refreshMappings();
  res.json({ ok: true, message: 'Mappings refreshed' });
});

function sampleTwoVideos(videos) {
  const pickedIndices = new Set();
  while (pickedIndices.size < 2) {
    pickedIndices.add(Math.floor(Math.random() * videos.length));
  }
  return [...pickedIndices].map((index) => videos[index]);
}

// API to get fresh A/B pairs for a participant (2 random videos per directory)
app.get('/api/all-pairs', (req, res) => {
  let allPairs = [];

  videoCatalog.forEach((survey) => {
    if (survey.videos.length < 2) {
      return;
    }

    const sampledVideos = sampleTwoVideos(survey.videos);
    const pair = sampledVideos.map((video) => ({
      id: video.id,
      file: reverseMapping.get(video.file)
    }));

    if (!pair[0].file || !pair[1].file) {
      return;
    }

    if (Math.random() < 0.5) {
      [pair[0], pair[1]] = [pair[1], pair[0]];
    }

    allPairs.push(pair);
  });

  // Shuffle the pair order shown to each participant
  shuffleInPlace(allPairs);
  res.json(allPairs);
});

// API to serve anonymous videos
app.get('/api/video/:anonId', (req, res) => {
  const anonId = req.params.anonId;
  const realPath = videoMapping.get(anonId);
  
  if (!realPath) {
    return res.status(404).json({ error: 'Video not found' });
  }
  
  const videoPath = path.join(__dirname, realPath);
  if (!fs.existsSync(videoPath)) {
    return res.status(404).json({ error: 'Video file not found' });
  }
  
  res.sendFile(videoPath);
});

// API to check if a user ID already exists
app.get('/api/check-user/:id', (req, res) => {
  const userId = req.params.id;
  fs.readFile(resultsFile, 'utf8', (err, data) => {
    if (err) {
      // If file doesn't exist or is unreadable, the user doesn't exist
      return res.json({ exists: false });
    }
    const results = JSON.parse(data);
    res.json({ exists: results.hasOwnProperty(userId) });
  });
});

app.post('/api/submit', (req, res) => {
  const { userId, votes } = req.body;
  if (!userId || !votes || !Array.isArray(votes)) {
    return res.status(400).json({ ok: false, error: 'Missing required fields' });
  }

  // Map anonymous video IDs back to original file paths for research data
  const votesWithOriginalPaths = votes.map(vote => {
    // Helper to map a video object back to original path
    const mapVideo = (video) => {
      if (!video || typeof video !== 'object') {
        return null;
      }
      return {
        ...video,
        file: videoMapping.get(video.file) || video.file // Resolve anonymous ID to real path
      };
    };

    const mappedResults = {};
    // Map winners and losers for each metric
    if (vote.results) {
      for (const [metric, result] of Object.entries(vote.results)) {
        if (result && result.tie) {
          mappedResults[metric] = {
            tie: true,
            winner: null,
            loser: null
          };
        } else {
          mappedResults[metric] = {
            tie: false,
            winner: mapVideo(result?.winner),
            loser: mapVideo(result?.loser)
          };
        }
      }
    }

    return {
      ...vote,
      pair: vote.pair.map(mapVideo),
      results: mappedResults
    };
  });

  fs.readFile(resultsFile, 'utf8', (err, data) => {
    if (err) {
      console.error(err);
      return res.status(500).json({ ok: false, error: 'Could not read results file' });
    }
    const results = JSON.parse(data);

    // Save the votes with original file paths
    results[userId] = votesWithOriginalPaths;

    fs.writeFile(resultsFile, JSON.stringify(results, null, 2), 'utf8', (err) => {
      if (err) {
        console.error(err);
        return res.status(500).json({ ok: false, error: 'Could not save results' });
      }
      res.json({ ok: true });
    });
  });
});

app.get('/results', (req, res) => {
  res.sendFile(resultsFile);
});

app.listen(PORT, '0.0.0.0', () => console.log(`Listening on ${PORT}`));
