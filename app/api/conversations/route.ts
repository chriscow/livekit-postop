import { NextResponse } from 'next/server';
import { createClient } from 'redis';

// Redis client setup
let redisClient: any = null;

async function getRedisClient() {
  if (!redisClient) {
    const redisUrl = process.env.REDIS_URL || 'redis://localhost:6379';
    redisClient = createClient({ url: redisUrl });
    await redisClient.connect();
  }
  return redisClient;
}

export type ConversationSummary = {
  sessionId: string;
  messageCount: number;
  firstMessage?: string;
  lastMessage?: string;
  startTime?: number;
  endTime?: number;
};

export async function GET() {
  try {
    const redis = await getRedisClient();
    
    // Get all session IDs
    const sessionIds = await redis.sMembers('postop:conversations:sessions');
    
    // Get summary data for each session
    const conversations: ConversationSummary[] = [];
    
    for (const sessionId of sessionIds) {
      const conversationKey = `postop:conversations:${sessionId}`;
      const messages = await redis.lRange(conversationKey, 0, -1);
      
      if (messages.length === 0) continue;
      
      // Parse messages to get timestamps and content
      const parsedMessages = messages.map((msg: string) => {
        try {
          return JSON.parse(msg);
        } catch {
          return null;
        }
      }).filter(Boolean);
      
      if (parsedMessages.length === 0) continue;
      
      // Sort by timestamp (Redis lpush stores in reverse order)
      parsedMessages.sort((a, b) => a.timestamp - b.timestamp);
      
      const firstMsg = parsedMessages[0];
      const lastMsg = parsedMessages[parsedMessages.length - 1];
      
      conversations.push({
        sessionId,
        messageCount: parsedMessages.length,
        firstMessage: firstMsg?.message?.substring(0, 100) || '',
        lastMessage: lastMsg?.message?.substring(0, 100) || '',
        startTime: firstMsg?.timestamp,
        endTime: lastMsg?.timestamp,
      });
    }
    
    // Sort conversations by start time (most recent first)
    conversations.sort((a, b) => (b.startTime || 0) - (a.startTime || 0));
    
    return NextResponse.json(conversations);
    
  } catch (error) {
    console.error('Failed to fetch conversations:', error);
    return NextResponse.json(
      { error: 'Failed to fetch conversations' },
      { status: 500 }
    );
  }
}