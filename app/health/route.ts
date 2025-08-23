import { createClient } from 'redis';

export async function GET() {
  const redisUrl = process.env.REDIS_URL || 'redis://localhost:6379';
  const client = createClient({ url: redisUrl });

  try {
    await client.connect();
    const pong = await client.ping();

    return new Response(
      JSON.stringify({
        status: 'ok',
        service: 'postop-ai-web',
        redis: pong === 'PONG' ? 'connected' : 'unknown',
        timestamp: Date.now(),
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } }
    );
  } catch (error: unknown) {
    return new Response(
      JSON.stringify({
        status: 'degraded',
        service: 'postop-ai-web',
        redis: 'error',
        error: (error as Error)?.message || String(error),
        timestamp: Date.now(),
      }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  } finally {
    try {
      await client.disconnect();
    } catch {}
  }
}
