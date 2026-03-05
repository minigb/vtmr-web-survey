const express = require('express');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const app = express();
const PORT = process.env.PORT || 5555;
const VIDEOS_DIR = path.join(__dirname, 'videos');
const VIDEO_EXTENSIONS = new Set(['.mp4', '.webm', '.ogg']);
const RESULTS_READ_TOKEN = process.env.RESULTS_READ_TOKEN || '';
const ADMIN_API_TOKEN = process.env.ADMIN_API_TOKEN || '';

app.use(express.static('public'));
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
        file: `videos/${subdir}/${videoFile}`
      }));

    return {
      id: `survey_${subdir}`,
      name: subdir,
      videos
    };
  });
}

function generateAnonVideoToken() {
  return `v_${crypto.randomBytes(12).toString('hex')}`;
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
  const used = new Set();
  allVideoFiles.forEach((videoFile) => {
    let anonId = generateAnonVideoToken();
    while (used.has(anonId)) {
      anonId = generateAnonVideoToken();
    }
    used.add(anonId);
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
  if (!ADMIN_API_TOKEN) {
    return res.status(404).json({ error: 'Not found' });
  }
  if (req.query.token !== ADMIN_API_TOKEN) {
    return res.status(403).json({ error: 'Forbidden' });
  }
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
    const pair = sampledVideos.map((video) => ({ file: reverseMapping.get(video.file) }));

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
  const votesWithOriginalPaths = votes.map((vote) => {
    // Only trust anonymous token from client and resolve canonical server-side fields.
    const mapVideo = (video) => {
      if (!video || typeof video !== 'object') {
        return null;
      }
      const anonFile = String(video.file || '');
      const realFile = videoMapping.get(anonFile);
      if (!realFile) {
        return null;
      }
      const parsed = path.parse(realFile);
      const subdir = path.basename(path.dirname(realFile));
      const canonicalId = `${subdir}_${parsed.name}`;
      return {
        id: canonicalId,
        file: realFile
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

  // Reject malformed or tampered payloads that contain unknown video tokens.
  const hasInvalidVideoRef = votesWithOriginalPaths.some((vote) => {
    if (!Array.isArray(vote.pair) || vote.pair.length !== 2 || vote.pair.some((video) => !video)) {
      return true;
    }
    if (!vote.results || typeof vote.results !== 'object') {
      return true;
    }
    for (const result of Object.values(vote.results)) {
      if (!result || typeof result !== 'object') {
        return true;
      }
      if (result.tie === true) {
        continue;
      }
      if (!result.winner || !result.loser) {
        return true;
      }
    }
    return false;
  });
  if (hasInvalidVideoRef) {
    return res.status(400).json({ ok: false, error: 'Invalid vote payload' });
  }

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
  if (!RESULTS_READ_TOKEN) {
    return res.status(404).json({ error: 'Not found' });
  }
  if (req.query.token !== RESULTS_READ_TOKEN) {
    return res.status(403).json({ error: 'Forbidden' });
  }
  res.sendFile(resultsFile);
});

app.listen(PORT, '0.0.0.0', () => console.log(`Listening on ${PORT}`));
