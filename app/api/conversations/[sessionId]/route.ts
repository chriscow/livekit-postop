import { NextResponse } from 'next/server';
import { Pool } from 'pg';

// PostgreSQL client setup
let pgPool: Pool | null = null;

async function getPgPool() {
  if (!pgPool) {
    const databaseUrl = process.env.DATABASE_URL;
    if (!databaseUrl) {
      throw new Error('DATABASE_URL environment variable not set');
    }
    pgPool = new Pool({ connectionString: databaseUrl });
  }
  return pgPool;
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
    const pool = await getPgPool();

    // Get session data from PostgreSQL
    const query = `
      SELECT
        session_id,
        timestamp,
        patient_name,
        patient_language,
        transcript,
        collected_instructions,
        jsonb_array_length(transcript) as message_count,
        jsonb_array_length(collected_instructions) as instruction_count,
        created_at,
        updated_at
      FROM sessions
      WHERE session_id = $1
    `;

    const result = await pool.query(query, [sessionId]);

    if (result.rows.length === 0) {
      return NextResponse.json({ error: 'Conversation not found' }, { status: 404 });
    }

    const row = result.rows[0];
    const transcript = row.transcript || [];
    const collectedInstructions = row.collected_instructions || [];

    // Format messages with timestamps
    const messages: ConversationMessage[] = transcript.map((msg: {role: string, content: string, timestamp?: string}) => ({
      role: msg.role,
      content: msg.content,
      formattedTime: msg.timestamp ? new Date(msg.timestamp).toLocaleString() : undefined,
    }));

    const conversationDetails: ConversationDetails = {
      sessionId: row.session_id,
      timestamp: row.timestamp,
      patientName: row.patient_name,
      patientLanguage: row.patient_language,
      messages,
      collectedInstructions,
      messageCount: row.message_count || 0,
      instructionCount: row.instruction_count || 0,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
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
    const pool = await getPgPool();

    // Check if conversation exists and delete it
    const deleteQuery = `
      DELETE FROM sessions
      WHERE session_id = $1
      RETURNING session_id
    `;

    const result = await pool.query(deleteQuery, [sessionId]);

    if (result.rows.length === 0) {
      return NextResponse.json({ error: 'Conversation not found' }, { status: 404 });
    }

    return NextResponse.json({
      message: 'Conversation deleted successfully',
      sessionId: result.rows[0].session_id,
    });
  } catch (error) {
    console.error('Failed to delete conversation:', error);
    return NextResponse.json({ error: 'Failed to delete conversation' }, { status: 500 });
  }
}
