/**
 * TanCat licence relay - the only piece of ours in the purchase path.
 *
 * The product never holds a merchant API key, so it cannot talk to the store
 * directly. It talks to this Worker instead; this Worker holds the key as a secret
 * and forwards three operations:
 *
 *   POST /activate    { key, instance_name }          -> { activation: {...} }
 *   POST /validate    { key, instance_id }            -> { status, expires_at }
 *   POST /deactivate  { key, instance_id }            -> { released: true }
 *
 * Failures answer with OUR error codes, never the store's status machine:
 *
 *   activation_limit   the key is on its maximum number of machines   (403)
 *   not_recognised     the key is not one of ours                     (404)
 *   already_released   this machine was already released               (409)
 *   revoked_or_expired the key is disabled or past its expiry         (410)
 *   not_found          the key/instance pair is unknown on validate    (404)
 *   upstream_error     anything else - the caller treats it as unreachable
 *
 * The product maps those codes to sentences. No provider name appears in any
 * response body: these strings can reach a buyer's screen.
 */

const UPSTREAM_STATUS = {
  403: 'activation_limit',
  404: 'not_recognised',
  409: 'already_released',
  410: 'revoked_or_expired',
};

/** Path allowed to reach the browser. The product is not a browser, so this is
 *  only for the docs site's "activate" helper; everything else gets no CORS. */
const DEFAULT_ALLOWED_ORIGIN = 'https://tancat.dev';

function corsHeaders(request, env) {
  const allowed = (env.ALLOWED_ORIGIN || DEFAULT_ALLOWED_ORIGIN).trim();
  const origin = request.headers.get('Origin') || '';
  if (!origin || origin !== allowed) return {};
  return {
    'Access-Control-Allow-Origin': allowed,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '600',
    Vary: 'Origin',
  };
}

function json(body, status, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...extraHeaders },
  });
}

/** The upstream call. The key never leaves this Worker's memory. */
async function upstream(env, path, payload) {
  const base = (env.API_BASE || '').replace(/\/$/, '');
  if (!base || !env.API_KEY) {
    return { status: 503, body: {} };
  }
  const response = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'x-api-key': env.API_KEY,
    },
    body: JSON.stringify(payload),
  });
  let body = {};
  try {
    body = await response.json();
  } catch {
    body = {};
  }
  return { status: response.status, body };
}

/** Our codes. The product maps these to sentences; none of them is the store's. */
const OUR_CODES = ['activation_limit', 'not_recognised', 'already_released', 'revoked_or_expired', 'not_found'];

/**
 * The store's message, lowercased, as one string. Its 400 bodies carry the useful
 * text in `message` (and sometimes repeat it in `error`).
 */
function messageOf(body) {
  const parts = [body?.message, body?.error, body?.detail]
    .filter((value) => typeof value === 'string')
    .map((value) => value.toLowerCase());
  return parts.join(' | ');
}

/**
 * Classify an upstream failure into one of OUR codes.
 *
 * **Both** the status and the message are read, because the live store does not use
 * the codes its reference page implies (observed 2026-11-26, test API):
 *
 *   - activation limit reached  -> 400 {"error":"Bad Request","message":"Activation limit reached"}
 *   - already deactivated       -> 400 {"message":"License key instnace is already deactivated"}
 *   - not found                 -> 404
 *   - revoked / expired         -> 410
 *
 * A status-only mapping told the buyer "could not reach the licence service" when
 * the truth was "this key is already in use" (t-1508). The message wins when it
 * names a cause the status does not.
 */
function codeFor(status, operation, body) {
  const explicit = String(body?.error || body?.code || '').trim();
  if (OUR_CODES.includes(explicit)) {
    return explicit;
  }

  const message = messageOf(body);
  // The store's own spelling of "instance" is misspelt in this message; match the
  // words either side of it so a correction on their side cannot unmatch us.
  if (message.includes('already deactivated') || message.includes('already released')) {
    return 'already_released';
  }
  if (message.includes('activation limit')) {
    return 'activation_limit';
  }
  if (message.includes('disabled') || message.includes('revoked') || message.includes('expired')) {
    return 'revoked_or_expired';
  }
  if (message.includes('not found') || message.includes('does not exist') || message.includes('unknown key')) {
    return operation === 'validate' ? 'not_found' : 'not_recognised';
  }
  if (message.includes('invalid') || message.includes('not recognised') || message.includes('not recognized')) {
    return operation === 'validate' ? 'not_found' : 'not_recognised';
  }

  if (status === 403) return 'activation_limit';
  if (status === 404) return operation === 'validate' ? 'not_found' : 'not_recognised';
  if (status === 409) return 'already_released';
  if (status === 410) return 'revoked_or_expired';
  return 'upstream_error';
}

/**
 * The store answers an activation with the licence object, sometimes wrapped in a
 * `license` key (the shape read from its API on 2026-11-26). Unwrap once, here, so a
 * wrapper cannot silently empty the created_at date the 12-month window runs from.
 */
function licenceObject(body) {
  const inner = body?.license ?? body?.licence ?? body;
  return inner && typeof inner === 'object' ? inner : {};
}

/** The shape the product caches. Field names are part of the contract. */
function activationFrom(body, key, instanceName) {
  const licence = licenceObject(body);
  const instance = licence?.instance || {};
  return {
    key: licence?.key || key,
    status: licence?.status || 'active',
    created_at: licence?.created_at || new Date().toISOString(),
    expires_at: licence?.expires_at || '',
    activation_limit: typeof licence?.activation_limit === 'number' ? licence.activation_limit : null,
    instance: {
      id: instance.id || '',
      name: instance.name || instanceName,
      status: instance.status || 'active',
    },
  };
}

async function readBody(request) {
  try {
    const data = await request.json();
    return data && typeof data === 'object' ? data : {};
  } catch {
    return {};
  }
}

function requiredText(value) {
  return typeof value === 'string' ? value.trim() : '';
}

async function handle(request, env) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, '') || '/';
  const operation = path.replace(/^\//, '');

  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders(request, env) });
  }
  if (request.method !== 'POST') {
    return json({ error: 'method_not_allowed' }, 405);
  }
  if (!['activate', 'validate', 'deactivate'].includes(operation)) {
    return json({ error: 'not_found' }, 404);
  }

  const body = await readBody(request);
  const key = requiredText(body.key);
  if (!key) {
    return json({ error: 'not_recognised' }, 400);
  }

  if (operation === 'activate') {
    const instanceName = requiredText(body.instance_name) || 'this machine';
    const { status, body: upstreamBody } = await upstream(env, '/v1/licenses/activate', {
      key,
      instance_name: instanceName,
    });
    if (status === 200) {
      return json({ activation: activationFrom(upstreamBody, key, instanceName) }, 200);
    }
    return json({ error: codeFor(status, 'activate', upstreamBody) }, status || 502);
  }

  const instanceId = requiredText(body.instance_id);
  if (!instanceId) {
    return json({ error: 'not_found' }, 400);
  }

  if (operation === 'validate') {
    const { status, body: upstreamBody } = await upstream(env, '/v1/licenses/validate', {
      key,
      instance_id: instanceId,
    });
    if (status === 200) {
      const licence = licenceObject(upstreamBody);
      return json({ status: licence?.status || '', expires_at: licence?.expires_at || '' }, 200);
    }
    return json({ error: codeFor(status, 'validate', upstreamBody) }, status || 502);
  }

  const { status, body: upstreamBody } = await upstream(env, '/v1/licenses/deactivate', {
    key,
    instance_id: instanceId,
  });
  if (status === 200) {
    return json({ released: true }, 200);
  }
  return json({ error: codeFor(status, 'deactivate', upstreamBody) }, status || 502);
}

export default {
  async fetch(request, env) {
    const headers = corsHeaders(request, env);
    try {
      const response = await handle(request, env);
      for (const [name, value] of Object.entries(headers)) {
        response.headers.set(name, value);
      }
      return response;
    } catch {
      // Never leak an upstream error message: it can carry a provider's wording.
      return json({ error: 'upstream_error' }, 502, headers);
    }
  },
};
