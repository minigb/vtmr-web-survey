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
const resultFile = path.join(dataDir, 'results.json');
if (!fs.existsSync(resultFile)) fs.writeFileSync(resultFile, '[]');

app.post('/vote', (req, res) => {
  const choice = req.body.choice || req.body.selection;
  if (!choice) return res.status(400).json({ ok: false, error: 'no choice' });
  const vote = { choice, ts: new Date().toISOString(), ip: req.ip };
  const arr = JSON.parse(fs.readFileSync(resultFile, 'utf8'));
  arr.push(vote);
  fs.writeFileSync(resultFile, JSON.stringify(arr, null, 2));
  res.json({ ok: true });
});

app.get('/results', (req, res) => {
  res.sendFile(resultFile);
});

app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, '0.0.0.0', () => console.log(`Listening on ${PORT}`));
