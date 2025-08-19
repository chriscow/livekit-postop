import { z } from 'zod';

/**
 * Discharge-specific function tools for the Maya agent
 */
export const createDischargeTools = (memory, sessionData) => {
  return {
    start_passive_listening: {
      description: 'Enter passive listening mode for instruction collection',
      parameters: z.object({}),
      execute: async (_, context) => {
        console.log('[FUNCTION] Entering passive listening mode');
        
        // Store state in agent context if available
        if (context?.agent) {
          context.agent._isPassiveMode = true;
        }
        
        // Store in session data
        sessionData.isPassiveMode = true;
        sessionData.workflowMode = 'passive_listening';
        
        // Persist to Redis
        await memory?.storeSessionData(sessionData.sessionId, 'workflow_mode', 'passive_listening');
        await memory?.storeSessionData(sessionData.sessionId, 'is_passive_mode', true);
        
        return "Got it, I'll listen quietly while you go through the instructions.";
      },
    },
    
    exit_passive_listening: {
      description: `Call this function when:
      1. Addressed directly by name ("Maya", "Hey Maya", "Maya, are you listening?")
      2. Asked for translation ("Can you translate this?", "What did they say?")
      3. Doctor indicates they're finished ("That's all", "Any questions?", "We're done", "We're all set", "Maya, did you get all that?")
      4. Someone asks if you captured everything or needs clarification
      
      After exiting, you can return to passive listening if the consultation continues and no further translation is needed.`,
      parameters: z.object({}),
      execute: async (_, context) => {
        console.log('[FUNCTION] Exiting passive listening mode');
        
        // Update state in agent context if available
        if (context?.agent) {
          context.agent._isPassiveMode = false;
        }
        
        // Update session data
        sessionData.isPassiveMode = false;
        sessionData.workflowMode = 'active';
        
        // Persist to Redis
        await memory?.storeSessionData(sessionData.sessionId, 'workflow_mode', 'active');
        await memory?.storeSessionData(sessionData.sessionId, 'is_passive_mode', false);
        
        return "I'm back. How can I help?";
      },
    },
    
    store_patient_name: {
      description: "Captures and stores patient's full name",
      parameters: z.object({
        name: z.string().describe("The patient's full name"),
      }),
      execute: async ({ name }) => {
        console.log(`[FUNCTION] Storing patient name: ${name}`);
        sessionData.patientName = name;
        await memory?.storeSessionData(sessionData.sessionId, 'patient_name', name);
        return `Patient name "${name}" has been recorded.`;
      },
    },
    
    store_patient_language: {
      description: 'Records preferred language for care instructions',
      parameters: z.object({
        language: z.string().describe("The patient's preferred language"),
      }),
      execute: async ({ language }) => {
        console.log(`[FUNCTION] Storing patient language: ${language}`);
        sessionData.patientLanguage = language;
        await memory?.storeSessionData(sessionData.sessionId, 'patient_language', language);
        return `Patient language preference "${language}" has been recorded.`;
      },
    },
    
    collect_instruction: {
      description: 'Captures discharge instructions being read aloud',
      parameters: z.object({
        instruction: z.string().describe('The discharge instruction'),
        category: z.string().optional().describe('Category: medication, activity, followup, warning, etc.'),
      }),
      execute: async ({ instruction, category }) => {
        console.log(`[FUNCTION] Collecting instruction [${category || 'general'}]: ${instruction}`);
        
        const instructionData = {
          text: instruction,
          category: category || 'general',
          timestamp: Date.now()
        };
        
        sessionData.collectedInstructions.push(instructionData);
        await memory?.storeSessionData(sessionData.sessionId, 'collected_instructions', sessionData.collectedInstructions);
        
        return `Instruction recorded: ${instruction}`;
      },
    },
    
    translate_instruction: {
      description: 'Real-time English to patient language translation',
      parameters: z.object({
        instruction: z.string().describe('The instruction to translate'),
        targetLanguage: z.string().describe('Target language for translation'),
      }),
      execute: async ({ instruction, targetLanguage }) => {
        console.log(`[FUNCTION] Translating to ${targetLanguage}: ${instruction}`);
        // In a real implementation, you'd use a translation service
        // For now, this is a placeholder that would integrate with translation APIs
        return `[Translation to ${targetLanguage}]: ${instruction}`;
      },
    },
  };
};