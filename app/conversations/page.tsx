'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { TrashIcon } from '@phosphor-icons/react/dist/ssr';
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
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());

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

  const handleDeleteConversation = async (sessionId: string) => {
    const confirmed = window.confirm(
      `Are you sure you want to delete conversation ${sessionId}? This action cannot be undone.`
    );

    if (!confirmed) return;

    setDeletingIds((prev) => new Set(prev).add(sessionId));

    try {
      const response = await fetch(`/api/conversations/${sessionId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || 'Failed to delete conversation');
      }

      // Remove from local state optimistically
      setConversations((prev) => prev.filter((conv) => conv.sessionId !== sessionId));
      toast.success(`Conversation ${sessionId} deleted successfully`);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to delete conversation';
      toast.error(errorMessage);
      console.error('Delete error:', err);
    } finally {
      setDeletingIds((prev) => {
        const newSet = new Set(prev);
        newSet.delete(sessionId);
        return newSet;
      });
    }
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
      <header className="mb-8 flex items-center justify-between py-2">
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
          <h2 className="mb-2 text-xl font-semibold">No conversations found</h2>
          <p className="text-fg1 mb-4">
            No conversation data is available yet. Conversations will appear here after discharge
            calls with Maya.
          </p>
          <Button asChild variant="primary">
            <Link href="/app">Start a Conversation</Link>
          </Button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="text-fg1 mb-4 text-sm">
            Found {conversations.length} conversation{conversations.length !== 1 ? 's' : ''}
          </div>

          {conversations.map((conversation) => (
            <div
              key={conversation.sessionId}
              className="border-border bg-card hover:bg-accent/50 rounded-lg border p-6 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="mb-2 flex items-center gap-3">
                    <h3 className="font-mono text-lg font-semibold">{conversation.sessionId}</h3>
                    <span className="bg-primary/10 text-primary rounded-full px-2 py-1 text-xs font-medium">
                      {conversation.messageCount} messages
                    </span>
                  </div>

                  <div className="text-fg1 space-y-1 text-sm">
                    <div>
                      <strong>Started:</strong> {formatDate(conversation.startTime)}
                    </div>
                    <div>
                      <strong>Duration:</strong>{' '}
                      {formatDuration(conversation.startTime, conversation.endTime)}
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
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => handleDeleteConversation(conversation.sessionId)}
                    disabled={deletingIds.has(conversation.sessionId)}
                    className="px-2"
                  >
                    {deletingIds.has(conversation.sessionId) ? (
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    ) : (
                      <TrashIcon size={16} />
                    )}
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
