#!/usr/bin/env node

import { config } from 'dotenv';
import { WorkerOptions, cli } from '@livekit/agents';
import { fileURLToPath } from 'node:url';

import { DischargeAgent } from './agents/discharge/DischargeAgent.js';

// Load environment variables from .env.local
config({ path: '.env.local' });

// Global cleanup tracking
const activeConnections = new Set();

// Graceful shutdown handling
process.on('SIGINT', async () => {
  console.log('\n🛑 Received SIGINT, cleaning up...');
  await cleanupAll();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.log('\n🛑 Received SIGTERM, cleaning up...');
  await cleanupAll();
  process.exit(0);
});

async function cleanupAll() {
  console.log('🧹 Cleaning up all active connections...');
  for (const cleanup of activeConnections) {
    try {
      await cleanup();
    } catch (error) {
      console.error('Error during cleanup:', error);
    }
  }
  activeConnections.clear();
}

// Create discharge agent instance
const dischargeAgent = new DischargeAgent();
const agent = dischargeAgent.createAgent();

// Export the agent for the worker
export default agent;

// If this script is run directly, start the worker
if (import.meta.url === `file://${fileURLToPath(import.meta.url)}` || import.meta.url === `file://${process.argv[1]}`) {
  console.log('🎯 Starting PostOp AI Discharge Workflow (JavaScript Version)');
  console.log('Environment check:');
  console.log(`- LIVEKIT_URL: ${process.env.LIVEKIT_URL ? '✓ Set' : '✗ Missing'}`);
  console.log(`- LIVEKIT_API_KEY: ${process.env.LIVEKIT_API_KEY ? '✓ Set' : '✗ Missing'}`);
  console.log(`- LIVEKIT_API_SECRET: ${process.env.LIVEKIT_API_SECRET ? '✓ Set' : '✗ Missing'}`);
  console.log(`- OPENAI_API_KEY: ${process.env.OPENAI_API_KEY ? '✓ Set' : '✗ Missing'}`);
  console.log(`- DEEPGRAM_API_KEY: ${process.env.DEEPGRAM_API_KEY ? '✓ Set' : '✗ Missing'}`);
  console.log(`- REDIS_URL: ${process.env.REDIS_URL || 'redis://localhost:6379 (default)'}`);
  
  if (!process.env.LIVEKIT_URL || !process.env.LIVEKIT_API_KEY || !process.env.LIVEKIT_API_SECRET) {
    console.error('❌ Missing required LiveKit environment variables');
    process.exit(1);
  }
  
  if (!process.env.OPENAI_API_KEY) {
    console.error('❌ Missing OPENAI_API_KEY environment variable');
    process.exit(1);
  }

  if (!process.env.DEEPGRAM_API_KEY) {
    console.error('❌ Missing DEEPGRAM_API_KEY environment variable');
    process.exit(1);
  }
  
  console.log('✓ All environment variables set, starting Maya discharge agent...');
  
  const entryPath = fileURLToPath(import.meta.url);
  console.log(`Using entry module: ${entryPath}`);
  
  // Use the CLI to start the worker
  cli.runApp(new WorkerOptions({ 
    agent: entryPath
  }));
}