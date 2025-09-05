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

export type ConversationMessage = {
  timestamp: number;
  role: 'user' | 'assistant';
  message: string;
  formattedTime?: string;
};

export type ConversationDetails = {
  sessionId: string;
  messages: ConversationMessage[];
  messageCount: number;
  startTime: number;
  endTime: number;
  duration: number; // in seconds
};

export async function GET(
  request: Request,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    const { sessionId } = await params;
    const redis = await getRedisClient();
    
    // Get all messages for this conversation
    const conversationKey = `postop:conversations:${sessionId}`;
    const messages = await redis.lRange(conversationKey, 0, -1);
    
    if (messages.length === 0) {
      return NextResponse.json(
        { error: 'Conversation not found' },
        { status: 404 }
      );
    }
    
    // Parse and sort messages by timestamp
    const parsedMessages: ConversationMessage[] = messages
      .map((msg: string) => {
        try {
          const parsed = JSON.parse(msg);
          return {
            timestamp: parsed.timestamp,
            role: parsed.role,
            message: parsed.message,
            formattedTime: new Date(parsed.timestamp * 1000).toLocaleString(),
          } as ConversationMessage;
        } catch {
          return null;
        }
      })
      .filter((msg: ConversationMessage | null): msg is ConversationMessage => msg !== null)
      .sort((a: ConversationMessage, b: ConversationMessage) => a.timestamp - b.timestamp);
    
    if (parsedMessages.length === 0) {
      return NextResponse.json(
        { error: 'No valid messages found' },
        { status: 404 }
      );
    }
    
    const startTime = parsedMessages[0].timestamp;
    const endTime = parsedMessages[parsedMessages.length - 1].timestamp;
    const duration = endTime - startTime;
    
    const conversationDetails: ConversationDetails = {
      sessionId,
      messages: parsedMessages,
      messageCount: parsedMessages.length,
      startTime,
      endTime,
      duration,
    };
    
    return NextResponse.json(conversationDetails);
    
  } catch (error) {
    console.error('Failed to fetch conversation details:', error);
    return NextResponse.json(
      { error: 'Failed to fetch conversation details' },
      { status: 500 }
    );
  }
}