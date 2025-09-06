'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

type ConversationMessage = {
  timestamp: number;
  role: 'user' | 'assistant';
  message: string;
  formattedTime?: string;
};

type ConversationDetails = {
  sessionId: string;
  messages: ConversationMessage[];
  messageCount: number;
  startTime: number;
  endTime: number;
  duration: number;
};

export default function ConversationDetailPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const [conversation, setConversation] = useState<ConversationDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchConversation() {
      try {
        const resolvedParams = await params;
        const sessionIdValue = resolvedParams.sessionId;
        const response = await fetch(`/api/conversations/${sessionIdValue}`);
        if (!response.ok) {
          if (response.status === 404) {
            throw new Error('Conversation not found');
          }
          throw new Error('Failed to fetch conversation');
        }
        const data = await response.json();
        setConversation(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setLoading(false);
      }
    }

    fetchConversation();
  }, [params]);

  const formatDuration = (duration: number) => {
    const minutes = Math.floor(duration / 60);
    const seconds = duration % 60;
    return `${minutes}m ${seconds}s`;
  };

  const formatTime = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleTimeString();
  };

  if (loading) {
    return (
      <main className="mx-auto flex min-h-svh w-full max-w-6xl flex-col px-6 py-10">
        <div className="flex items-center justify-center py-20">
          <div className="text-lg">Loading conversation...</div>
        </div>
      </main>
    );
  }

  if (error || !conversation) {
    return (
      <main className="mx-auto flex min-h-svh w-full max-w-6xl flex-col px-6 py-10">
        <div className="flex items-center justify-center py-20">
          <div className="text-center">
            <div className="mb-4 text-lg text-red-600">{error || 'Conversation not found'}</div>
            <Button asChild variant="outline">
              <Link href="/conversations">← Back to Conversations</Link>
            </Button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-6xl flex-col px-6 py-10">
      <header className="mb-8 flex items-start justify-between py-2">
        <div>
          <h1 className="font-mono text-3xl font-semibold tracking-tight">
            {conversation.sessionId}
          </h1>
          <div className="text-fg1 mt-2 flex items-center gap-6 text-sm">
            <span>
              <strong>Started:</strong> {new Date(conversation.startTime * 1000).toLocaleString()}
            </span>
            <span>
              <strong>Duration:</strong> {formatDuration(conversation.duration)}
            </span>
            <span>
              <strong>Messages:</strong> {conversation.messageCount}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Button asChild variant="outline" size="sm">
            <Link href="/conversations">← All Conversations</Link>
          </Button>
          <Button asChild variant="primary" size="sm" className="font-mono">
            <Link href="/app">Chat with Maya</Link>
          </Button>
        </div>
      </header>

      <div className="border-border bg-card overflow-hidden rounded-lg border">
        <div className="bg-accent/30 border-border border-b px-6 py-3">
          <h2 className="font-semibold">Conversation Transcript</h2>
        </div>

        <div className="divide-border max-h-[70vh] divide-y overflow-y-auto">
          {conversation.messages.map((message, index) => (
            <div
              key={index}
              className={`px-6 py-4 ${
                message.role === 'assistant' ? 'bg-primary/5' : 'bg-background'
              }`}
            >
              <div className="flex items-start gap-4">
                <div className="w-16 flex-shrink-0">
                  <div
                    className={`inline-flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold ${
                      message.role === 'assistant'
                        ? 'bg-primary text-white'
                        : 'bg-gray-500 text-white'
                    }`}
                  >
                    {message.role === 'assistant' ? 'M' : 'U'}
                  </div>
                </div>

                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex items-center gap-3">
                    <span className="font-medium">
                      {message.role === 'assistant' ? 'Maya' : 'User'}
                    </span>
                    <span className="text-fg1 text-xs">{formatTime(message.timestamp)}</span>
                  </div>
                  <div className="text-sm leading-relaxed whitespace-pre-wrap">
                    {message.message}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {conversation.messages.length === 0 && (
          <div className="text-fg1 px-6 py-12 text-center">No messages in this conversation</div>
        )}
      </div>

      <div className="mt-8 text-center">
        <Button asChild variant="outline">
          <Link href="/conversations">← Back to All Conversations</Link>
        </Button>
      </div>
    </main>
  );
}
