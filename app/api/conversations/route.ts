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
    const pool = await getPgPool();

    // Query sessions with computed message and instruction counts
    const query = `
      SELECT
        session_id,
        timestamp,
        patient_name,
        patient_language,
        jsonb_array_length(transcript) as message_count,
        jsonb_array_length(collected_instructions) as instruction_count,
        created_at,
        updated_at,
        transcript
      FROM sessions
      ORDER BY created_at DESC
      LIMIT 50
    `;

    const result = await pool.query(query);
    const conversations: ConversationSummary[] = [];

    for (const row of result.rows) {
      const transcript = row.transcript || [];

      // Extract first and last messages from transcript
      let firstMessage = '';
      let lastMessage = '';

      if (transcript.length > 0) {
        const userMessages = transcript.filter((msg: any) => msg.role === 'user');
        if (userMessages.length > 0) {
          firstMessage = userMessages[0]?.content?.substring(0, 100) || '';
          lastMessage = userMessages[userMessages.length - 1]?.content?.substring(0, 100) || '';
        }
      }

      conversations.push({
        sessionId: row.session_id,
        messageCount: row.message_count || 0,
        instructionCount: row.instruction_count || 0,
        patientName: row.patient_name,
        patientLanguage: row.patient_language,
        firstMessage,
        lastMessage,
        createdAt: row.created_at,
        updatedAt: row.updated_at,
      });
    }

    return NextResponse.json(conversations);
  } catch (error) {
    console.error('Failed to fetch conversations:', error);
    return NextResponse.json({ error: 'Failed to fetch conversations' }, { status: 500 });
  }
}
