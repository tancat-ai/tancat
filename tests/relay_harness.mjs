// Drive the real Worker from Python, with the store's answer stubbed.
//
// The contract test cannot be a string match on the Worker's source (t-1505): a
// renamed field only shows up when the two sides actually exchange a body. This
// harness imports the Worker as-is, replaces global fetch with a canned upstream,
// and prints the Worker's own response as JSON.
//
// Usage: node relay_harness.mjs <operation> <request-json> <upstream-status> <upstream-json> [env-json]
//
// The optional env JSON overrides the Worker's bindings, so a test can run it with
// the merchant secret missing.

import worker from '../services/licence-relay/src/index.js';

const [operation, requestJson, upstreamStatus, upstreamJson, envJson] = process.argv.slice(2);

globalThis.fetch = async () =>
  new Response(upstreamJson || '{}', {
    status: Number(upstreamStatus || 200),
    headers: { 'content-type': 'application/json' },
  });

const request = new Request(`https://relay.test/${operation}`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: requestJson,
});

const env = {
  API_KEY: 'harness-key',
  API_BASE: 'https://upstream.test',
  ALLOWED_ORIGIN: 'https://tancat.dev',
  ...(envJson ? JSON.parse(envJson) : {}),
};

const response = await worker.fetch(request, env);
const text = await response.text();
let body;
try {
  body = JSON.parse(text);
} catch {
  body = { raw: text };
}
process.stdout.write(JSON.stringify({ status: response.status, body }));
