import { z } from 'zod';

/**
 * Shared type definitions for PostOp AI system
 */

// Session data schema
export const SessionDataSchema = z.object({
  patientName: z.string().nullable(),
  patientLanguage: z.string().nullable(),
  workflowMode: z.enum(['setup', 'passive_listening', 'active_translation', 'verification']),
  isPassiveMode: z.boolean(),
  collectedInstructions: z.array(
    z.object({
      text: z.string(),
      category: z.string().optional(),
      timestamp: z.number(),
    })
  ),
  roomPeople: z.array(z.string()),
  sessionId: z.string(),
});

// Conversation message schema
export const ConversationMessageSchema = z.object({
  timestamp: z.number(),
  role: z.enum(['user', 'assistant', 'system']),
  message: z.string(),
});

// Instruction schema
export const InstructionSchema = z.object({
  text: z.string(),
  category: z.string().optional().default('general'),
  timestamp: z.number(),
  translated: z.boolean().optional().default(false),
  translatedText: z.string().optional(),
});

// Patient data schema
export const PatientDataSchema = z.object({
  name: z.string(),
  language: z.string().optional().default('en'),
  phoneNumber: z.string().optional(),
});

// Workflow state schema
export const WorkflowStateSchema = z.object({
  currentMode: z.enum(['setup', 'passive_listening', 'active_translation', 'verification']),
  isPassiveMode: z.boolean(),
  instructionsCollected: z.number(),
  translationRequired: z.boolean(),
  verificationComplete: z.boolean(),
});

export const WORKFLOW_MODES = {
  SETUP: 'setup',
  PASSIVE_LISTENING: 'passive_listening',
  ACTIVE_TRANSLATION: 'active_translation',
  VERIFICATION: 'verification',
};

export const MESSAGE_ROLES = {
  USER: 'user',
  ASSISTANT: 'assistant',
  SYSTEM: 'system',
};

export const INSTRUCTION_CATEGORIES = {
  MEDICATION: 'medication',
  ACTIVITY: 'activity',
  FOLLOWUP: 'followup',
  WARNING: 'warning',
  DIET: 'diet',
  WOUND_CARE: 'wound_care',
  GENERAL: 'general',
};
