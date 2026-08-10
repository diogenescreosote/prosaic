// config.js — matter configuration loading shared by all connectors.
//
// A matter is configured by `matter.yaml` in the matter directory:
//
//   case:
//     name: Smith v. Smith
//     number: 24CV00000
//   connectors:
//     gmail:
//       addresses: [opposing@example.com, examplefirm.com]
//     mycase:
//       portal_url: https://firm-name.mycase.com
//       credential: prosaic.mycase
//
// For compatibility with pre-prosaic matters, top-level keys in
// `envelopes.yaml` (`gmail_addresses:`, `mycase:`) are read as
// a fallback when matter.yaml has no entry for a connector.

const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

function loadYaml(file) {
  return fs.existsSync(file) ? yaml.load(fs.readFileSync(file, 'utf-8')) : null;
}

// Returns the config object for one connector, or null if unconfigured.
function connectorConfig(matterDir, name) {
  const matter = loadYaml(path.join(matterDir, 'matter.yaml'));
  const fromMatter = matter?.connectors?.[name];
  if (fromMatter) return fromMatter;
  const legacy = loadYaml(path.join(matterDir, 'envelopes.yaml'));
  if (!legacy) return null;
  if (name === 'gmail' && legacy.gmail_addresses)
    return { addresses: legacy.gmail_addresses };
  if (legacy[name]) return legacy[name];
  return null;
}

// Per-connector persistent state lives in <matter>/.state/<name>.json.
function statePath(matterDir, name) {
  const dir = path.join(matterDir, '.state');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `${name}.json`);
}

function loadState(matterDir, name, fallback = {}) {
  const p = statePath(matterDir, name);
  return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf-8')) : fallback;
}

function saveState(matterDir, name, state) {
  fs.writeFileSync(statePath(matterDir, name), JSON.stringify(state, null, 2));
}

module.exports = { connectorConfig, statePath, loadState, saveState, loadYaml };
