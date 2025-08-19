import { pipeline } from '@livekit/agents';
import { RedisMemory } from '../../lib/redis/RedisMemory.js';
import { SessionData } from '../../lib/utils/SessionData.js';

/**
 * Base agent class with common functionality
 */
export class BaseAgent {
  constructor(memory, sessionData) {
    this.memory = memory || new RedisMemory();
    this.sessionData = sessionData || new SessionData();
    this.activeConnections = new Set();
  }

  /**
   * Enhanced voice pipeline agent with conversation logging
   */
  createLoggingVoicePipelineAgent(vad, stt, llm, tts, options) {
    const memory = this.memory;
    const sessionData = this.sessionData;
    
    class LoggingVoicePipelineAgent extends pipeline.VoicePipelineAgent {
      constructor(...args) {
        super(...args);
        this._memory = memory;
        this._sessionData = sessionData;
        this._isPassiveMode = false;
      }
      
      async _logMessage(role, message) {
        await this._memory.logConversationMessage(this._sessionData.sessionId, role, message);
        console.log(`[CONVERSATION LOG] Session: ${this._sessionData.sessionId} | ${role.toUpperCase()}: '${message}'`);
      }
      
      async say(message, allowInterruptions = true) {
        await this._logMessage('assistant', message);
        return super.say(message, allowInterruptions);
      }
      
      async cleanup() {
        console.log('🧹 Cleaning up agent resources...');
        try {
          // Clean up Redis connection
          if (this._memory) {
            await this._memory.disconnect();
          }
          
          // Call parent cleanup if available
          if (super.cleanup) {
            await super.cleanup();
          }
        } catch (error) {
          console.error('Error during cleanup:', error);
        }
      }
    }

    return new LoggingVoicePipelineAgent(vad, stt, llm, tts, options);
  }

  /**
   * Register cleanup function for graceful shutdown
   */
  registerCleanup(cleanupFn) {
    this.activeConnections.add(cleanupFn);
  }

  /**
   * Remove cleanup function
   */
  unregisterCleanup(cleanupFn) {
    this.activeConnections.delete(cleanupFn);
  }

  /**
   * Clean up all registered connections
   */
  async cleanupAll() {
    console.log('🧹 Cleaning up all active connections...');
    for (const cleanup of this.activeConnections) {
      try {
        await cleanup();
      } catch (error) {
        console.error('Error during cleanup:', error);
      }
    }
    this.activeConnections.clear();
  }
}