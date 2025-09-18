import { NextResponse } from 'next/server';
import { createClient } from 'redis';

// Redis client setup
let redisClient: any = null;

async function getRedisClient() {
  if (!redisClient) {
    const redisUrl = process.env.REDIS_URL;
    if (!redisUrl) {
      throw new Error('REDIS_URL environment variable not set');
    }
    redisClient = createClient({ url: redisUrl });
    await redisClient.connect();
  }
  return redisClient;
}

export type ConversationSummary = {
  sessionId: string;
  messageCount: number;
  instructionCount: number;
  patientName?: string;
  patientLanguage?: string;
  firstMessage?: string;
  lastMessage?: string;
  createdAt: string;
  updatedAt: string;
};

export async function GET() {
  try {
    const redis = await getRedisClient();

    // Get all session keys
    const keys = await redis.keys('session:*');
    const conversations: ConversationSummary[] = [];

    // Get session data for each key
    for (const key of keys) {
      const sessionData = await redis.get(key);
      if (sessionData) {
        const session = JSON.parse(sessionData);
        const transcript = session.transcript || [];
        const instructions = session.collected_instructions || [];

        // Extract first and last messages from transcript
        let firstMessage = '';
        let lastMessage = '';

        if (transcript.length > 0) {
          const userMessages = transcript.filter((msg: {role: string, content?: string}) => msg.role === 'user');
          if (userMessages.length > 0) {
            firstMessage = userMessages[0]?.content?.substring(0, 100) || '';
            lastMessage = userMessages[userMessages.length - 1]?.content?.substring(0, 100) || '';
          }
        }

        conversations.push({
          sessionId: session.session_id,
          messageCount: transcript.length || 0,
          instructionCount: instructions.length || 0,
          patientName: session.patient_name,
          patientLanguage: session.patient_language,
          firstMessage,
          lastMessage,
          createdAt: session.created_at,
          updatedAt: session.updated_at,
        });
      }
    }

    // Sort by created_at (most recent first) and limit to 50
    conversations.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
    const limitedConversations = conversations.slice(0, 50);

    return NextResponse.json(limitedConversations);
  } catch (error) {
    console.error('Failed to fetch conversations:', error);
    return NextResponse.json({ error: 'Failed to fetch conversations' }, { status: 500 });
  }
}
