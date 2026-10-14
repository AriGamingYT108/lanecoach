import {NextRequest} from 'next/server';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function proxy(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  const {path} = await context.params;
  if (path.some(part => part === '.' || part === '..' || part.includes('/') || part.includes('\\')))
    return Response.json({detail: 'Unknown endpoint.'}, {status: 404});
  if (!['health', 'ready', 'visitor', 'champions', 'analytics', 'coverage', 'assets', 'sessions', 'coach'].includes(path[0]))
    return Response.json({detail: 'Unknown endpoint.'}, {status: 404});
  if ((request.method === 'POST') !== (path[0] === 'coach'))
    return Response.json({detail: 'Method not allowed.'}, {status: 405});
  const headers = new Headers({'Accept': 'application/json'});
  for (const name of ['content-type', 'origin', 'x-lanecoach-client', 'x-lanecoach-csrf']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const cookie = request.headers.get('cookie')?.split(';').map(c => c.trim()).find(c => c.startsWith('lanecoach_visitor='));
  if (cookie) headers.set('cookie', cookie);
  if (process.env.INTERNAL_PROXY_TOKEN) headers.set('x-lanecoach-proxy', process.env.INTERNAL_PROXY_TOKEN);
  let body: Uint8Array | undefined;
  if (request.method === 'POST') {
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let length = 0;
    if (reader) {
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        length += part.value.byteLength;
        if (length > 20000) {await reader.cancel(); return Response.json({detail: 'Request too large.'}, {status: 413});}
        chunks.push(part.value);
      }
    }
    body = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) {body.set(chunk, offset); offset += chunk.byteLength;}
  }
  try {
    const origin = process.env.API_ORIGIN || 'http://127.0.0.1:8000';
    const url = `${origin.replace(/\/$/, '')}/api/${path.map(encodeURIComponent).join('/')}${request.nextUrl.search}`;
    const upstream = await fetch(url, {method: request.method, headers, body: body as BodyInit | undefined,
      cache: 'no-store', redirect: 'manual', signal: AbortSignal.timeout(110000)});
    const outgoing = new Headers({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'});
    for (const name of ['content-type', 'retry-after']) {
      const value = upstream.headers.get(name); if (value) outgoing.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie()) outgoing.append('set-cookie', cookie);
    return new Response(upstream.body, {status: upstream.status, headers: outgoing});
  } catch {
    return Response.json({detail: 'The coaching service is temporarily unavailable. Please try again later.'}, {status: 503});
  }
}
export const GET = proxy;
export const POST = proxy;
