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

export type ConversationMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
  formattedTime?: string;
};

export type ConversationDetails = {
  sessionId: string;
  timestamp: string;
  patientName?: string;
  patientLanguage?: string;
  messages: ConversationMessage[];
  collectedInstructions: unknown[];
  messageCount: number;
  instructionCount: number;
  createdAt: string;
  updatedAt: string;
};

export async function GET(
  request: Request,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    const { sessionId } = await params;
    const redis = await getRedisClient();

    // Get session data from Redis
    const sessionKey = `session:${sessionId}`;
    const sessionData = await redis.get(sessionKey);

    if (!sessionData) {
      return NextResponse.json({ error: 'Conversation not found' }, { status: 404 });
    }

    const session = JSON.parse(sessionData);
    const transcript = session.transcript || [];
    const collectedInstructions = session.collected_instructions || [];

    // Format messages with timestamps
    const messages: ConversationMessage[] = transcript.map((msg: {role: string, content: string, timestamp?: string}) => ({
      role: msg.role,
      content: msg.content,
      formattedTime: msg.timestamp ? new Date(msg.timestamp).toLocaleString() : undefined,
    }));

    const conversationDetails: ConversationDetails = {
      sessionId: session.session_id,
      timestamp: session.timestamp,
      patientName: session.patient_name,
      patientLanguage: session.patient_language,
      messages,
      collectedInstructions,
      messageCount: transcript.length || 0,
      instructionCount: collectedInstructions.length || 0,
      createdAt: session.created_at,
      updatedAt: session.updated_at,
    };

    return NextResponse.json(conversationDetails);
  } catch (error) {
    console.error('Failed to fetch conversation details:', error);
    return NextResponse.json({ error: 'Failed to fetch conversation details' }, { status: 500 });
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    const { sessionId } = await params;
    const redis = await getRedisClient();

    // Check if conversation exists and delete it
    const sessionKey = `session:${sessionId}`;
    const result = await redis.del(sessionKey);

    if (result === 0) {
      return NextResponse.json({ error: 'Conversation not found' }, { status: 404 });
    }

    return NextResponse.json({
      message: 'Conversation deleted successfully',
      sessionId: sessionId,
    });
  } catch (error) {
    console.error('Failed to delete conversation:', error);
    return NextResponse.json({ error: 'Failed to delete conversation' }, { status: 500 });
  }
}
