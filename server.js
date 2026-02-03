const express = require('express');
const fs = require('fs');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 5555;

app.use(express.static('public'));
app.use('/videos', express.static('videos'));
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
const resultsFile = path.join(dataDir, 'results.json');
if (!fs.existsSync(resultsFile) || fs.readFileSync(resultsFile, 'utf8').trim() === '') fs.writeFileSync(resultsFile, '{}', 'utf8');

const surveys = JSON.parse(fs.readFileSync(path.join(__dirname, 'config', 'surveys.json'), 'utf8'));

// Create anonymous video mapping to hide real file paths
const videoMapping = new Map();
const reverseMapping = new Map();
let videoCounter = 1;

function createAnonymousMapping() {
  videoMapping.clear();
  reverseMapping.clear();
  
  // Collect all video files first
  const allVideoFiles = [];
  surveys.forEach(survey => {
    survey.videos.forEach(video => {
      allVideoFiles.push(video.file);
    });
  });
  
  // Create shuffled anonymous IDs
  const anonymousIds = [];
  for (let i = 1; i <= allVideoFiles.length; i++) {
    anonymousIds.push(`anon_video_${i.toString().padStart(3, '0')}`);
  }
  
  // Shuffle the anonymous IDs using Fisher-Yates algorithm
  for (let i = anonymousIds.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [anonymousIds[i], anonymousIds[j]] = [anonymousIds[j], anonymousIds[i]];
  }
  
  // Map shuffled anonymous IDs to video files
  allVideoFiles.forEach((videoFile, index) => {
    const anonId = anonymousIds[index];
    videoMapping.set(anonId, videoFile);
    reverseMapping.set(videoFile, anonId);
  });
  
  console.log(`🔀 Created ${allVideoFiles.length} shuffled anonymous video mappings`);
}

// Initialize mapping (will be refreshed on startup via the Python script)
createAnonymousMapping();

// Refresh mappings when surveys.json is updated
function refreshMappings() {
  try {
    const updatedSurveys = JSON.parse(fs.readFileSync(path.join(__dirname, 'config', 'surveys.json'), 'utf8'));
    surveys.length = 0; // Clear existing array
    surveys.push(...updatedSurveys); // Add updated surveys
    createAnonymousMapping();
    console.log('📋 Video mappings refreshed');
  } catch (error) {
    console.error('Error refreshing mappings:', error);
  }
}

// API endpoint to refresh mappings (called by Python script)
app.post('/api/refresh-mappings', (req, res) => {
  refreshMappings();
  res.json({ ok: true, message: 'Mappings refreshed' });
});

const generatePairs = (survey) => {
  const pairs = [];
  const videos = survey.videos;
  for (let i = 0; i < videos.length; i++) {
    for (let j = i + 1; j < videos.length; j++) {
      // Create anonymized video objects
      const anonVideo1 = {
        id: videos[i].id,
        file: reverseMapping.get(videos[i].file) // Use anonymous ID
      };
      const anonVideo2 = {
        id: videos[j].id,
        file: reverseMapping.get(videos[j].file) // Use anonymous ID
      };
      pairs.push([anonVideo1, anonVideo2]);
    }
  }
  return pairs;
};

// API to get all pairs from all surveys, shuffled
app.get('/api/all-pairs', (req, res) => {
  let allPairs = [];
  surveys.forEach(survey => {
    allPairs = allPairs.concat(generatePairs(survey));
  });
  // Shuffle the pairs
  for (let i = allPairs.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [allPairs[i], allPairs[j]] = [allPairs[j], allPairs[i]];
  }
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
    const mapVideo = (video) => ({
      ...video,
      file: videoMapping.get(video.file) || video.file // Resolve anonymous ID to real path
    });

    const mappedResults = {};
    // Map winners and losers for each metric
    if (vote.results) {
      for (const [metric, result] of Object.entries(vote.results)) {
        mappedResults[metric] = {
          winner: mapVideo(result.winner),
          loser: mapVideo(result.loser)
        };
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
