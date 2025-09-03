'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

type ConversationSummary = {
  sessionId: string;
  messageCount: number;
  firstMessage?: string;
  lastMessage?: string;
  startTime?: number;
  endTime?: number;
};

export default function ConversationsPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchConversations() {
      try {
        const response = await fetch('/api/conversations');
        if (!response.ok) {
          throw new Error('Failed to fetch conversations');
        }
        const data = await response.json();
        setConversations(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setLoading(false);
      }
    }

    fetchConversations();
  }, []);

  const formatDate = (timestamp?: number) => {
    if (!timestamp) return 'Unknown';
    return new Date(timestamp * 1000).toLocaleString();
  };

  const formatDuration = (start?: number, end?: number) => {
    if (!start || !end) return 'Unknown';
    const duration = end - start;
    const minutes = Math.floor(duration / 60);
    const seconds = duration % 60;
    return `${minutes}m ${seconds}s`;
  };

  if (loading) {
    return (
      <main className="mx-auto flex min-h-svh w-full max-w-6xl flex-col px-6 py-10">
        <div className="flex items-center justify-center py-20">
          <div className="text-lg">Loading conversations...</div>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="mx-auto flex min-h-svh w-full max-w-6xl flex-col px-6 py-10">
        <div className="flex items-center justify-center py-20">
          <div className="text-lg text-red-600">Error: {error}</div>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-6xl flex-col px-6 py-10">
      <header className="flex items-center justify-between py-2 mb-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Conversations</h1>
          <p className="text-fg1 mt-2">View all Maya conversations from discharge calls</p>
        </div>
        <div className="flex items-center gap-4">
          <Button asChild variant="outline" size="sm">
            <Link href="/">← Back to Home</Link>
          </Button>
          <Button asChild variant="primary" size="sm" className="font-mono">
            <Link href="/app">Chat with Maya</Link>
          </Button>
        </div>
      </header>

      {conversations.length === 0 ? (
        <div className="border-border bg-card rounded-lg border p-8 text-center">
          <h2 className="text-xl font-semibold mb-2">No conversations found</h2>
          <p className="text-fg1 mb-4">
            No conversation data is available yet. Conversations will appear here after discharge calls with Maya.
          </p>
          <Button asChild variant="primary">
            <Link href="/app">Start a Conversation</Link>
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="text-sm text-fg1 mb-4">
            Found {conversations.length} conversation{conversations.length !== 1 ? 's' : ''}
          </div>
          
          {conversations.map((conversation) => (
            <div
              key={conversation.sessionId}
              className="border-border bg-card hover:bg-accent/50 rounded-lg border p-6 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold font-mono">
                      {conversation.sessionId}
                    </h3>
                    <span className="bg-primary/10 text-primary px-2 py-1 rounded-full text-xs font-medium">
                      {conversation.messageCount} messages
                    </span>
                  </div>
                  
                  <div className="text-sm text-fg1 space-y-1">
                    <div>
                      <strong>Started:</strong> {formatDate(conversation.startTime)}
                    </div>
                    <div>
                      <strong>Duration:</strong> {formatDuration(conversation.startTime, conversation.endTime)}
                    </div>
                    {conversation.firstMessage && (
                      <div>
                        <strong>Preview:</strong> {conversation.firstMessage}
                        {conversation.firstMessage.length >= 100 && '...'}
                      </div>
                    )}
                  </div>
                </div>
                
                <div className="flex items-center gap-2">
                  <Button asChild size="sm" variant="outline">
                    <Link href={`/conversations/${conversation.sessionId}`}>
                      View Full Conversation
                    </Link>
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}