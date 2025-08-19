import { defineAgent, llm, AutoSubscribe } from '@livekit/agents';
import * as deepgram from '@livekit/agents-plugin-deepgram';
import * as livekit from '@livekit/agents-plugin-livekit';
import * as openai from '@livekit/agents-plugin-openai';
import * as silero from '@livekit/agents-plugin-silero';

import { BaseAgent } from '../base/BaseAgent.js';
import { RedisMemory } from '../../lib/redis/RedisMemory.js';
import { SessionData } from '../../lib/utils/SessionData.js';
import { DISCHARGE_INSTRUCTIONS } from '../../lib/prompts/discharge.js';
import { createDischargeTools } from '../../tools/DischargeTools.js';

/**
 * Maya - AI Medical Translation and Discharge Support Specialist
 */
export class DischargeAgent extends BaseAgent {
  constructor() {
    super();
    this.memory = new RedisMemory();
    this.sessionData = new SessionData();
  }

  /**
   * Create the agent definition
   */
  createAgent() {
    return defineAgent({
      prewarm: async (proc) => {
        console.log('🎯 Prewarming PostOp AI Discharge Agent...');
        proc.userData.vad = await silero.VAD.load();
        proc.userData.memory = this.memory;
        proc.userData.sessionData = this.sessionData;
        console.log('✓ VAD and Redis Memory loaded successfully');
      },
      
      entry: async (ctx) => {
        const vad = ctx.proc.userData.vad;
        const memory = ctx.proc.userData.memory;
        const sessionData = ctx.proc.userData.sessionData;
        
        console.log(`🚀 Starting Discharge Agent with session: ${sessionData.sessionId}`);
        
        // Create initial chat context with discharge instructions
        const initialContext = new llm.ChatContext().append({
          role: llm.ChatRole.SYSTEM,
          text: DISCHARGE_INSTRUCTIONS,
        });

        await ctx.connect(undefined, AutoSubscribe.AUDIO_ONLY);
        console.log('✓ Agent connected, waiting for participant...');
        
        // Wait for a participant to join
        const participant = await ctx.waitForParticipant();
        console.log(`✓ Starting discharge assistant for ${participant.identity}`);
        
        // Create function context with discharge tools
        const fncCtx = createDischargeTools(memory, sessionData);
        
        // Create the enhanced voice pipeline agent
        const voiceAgent = this.createLoggingVoicePipelineAgent(
          vad,
          new deepgram.STT({ model: "nova-3", language: "multi" }),
          new openai.LLM({ model: 'gpt-4.1' }),
          new openai.TTS({ voice: 'shimmer'}),
          { 
            chatCtx: initialContext, 
            fncCtx,
            turnDetector: new livekit.turnDetector.EOUModel()
          },
        );
        
        // Register cleanup function globally
        const cleanupFn = async () => {
          await voiceAgent.cleanup();
        };
        this.registerCleanup(cleanupFn);
        
        // Set up cleanup on disconnect
        ctx.room.on('disconnected', async () => {
          console.log('🔌 Room disconnected, cleaning up...');
          await cleanupFn();
          this.unregisterCleanup(cleanupFn);
        });
        
        // Start the voice pipeline
        voiceAgent.start(ctx.room, participant);

        // Send initial Maya greeting
        await voiceAgent.say("Hi all! I'm Maya, thanks for dialing me in today. So Dr. Shah, who do we have in the room today?", true);
        
        console.log('✓ PostOp Discharge Agent started successfully');
        
        // Return the agent instance
        return voiceAgent;
      },
    });
  }
}