const express = require('express');
const fs = require('fs');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 5555;

app.use(express.static('public'));
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
const resultsFile = path.join(dataDir, 'results.json');
if (!fs.existsSync(resultsFile)) fs.writeFileSync(resultsFile, '[]', 'utf8');

const surveys = JSON.parse(fs.readFileSync(path.join(__dirname, 'config', 'surveys.json'), 'utf8'));

const generatePairs = (survey) => {
  const pairs = [];
  const videos = survey.videos;
  for (let i = 0; i < videos.length; i++) {
    for (let j = i + 1; j < videos.length; j++) {
      pairs.push([videos[i], videos[j]]);
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

app.post('/api/vote', (req, res) => {
  const { pair, choice } = req.body;
  if (!pair || !choice) {
    return res.status(400).json({ ok: false, error: 'Missing required fields' });
  }

  const vote = {
    pair,
    choice,
    winner: choice === 'A' ? pair[0] : pair[1],
    loser: choice === 'A' ? pair[1] : pair[0],
    ts: new Date().toISOString(),
    ip: req.ip
  };

  fs.readFile(resultsFile, 'utf8', (err, data) => {
    if (err) {
      console.error(err);
      return res.status(500).json({ ok: false, error: 'Could not read results file' });
    }
    const results = JSON.parse(data);
    results.push(vote);
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
