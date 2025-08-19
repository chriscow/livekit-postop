/**
 * Shared utility functions for PostOp AI system
 */

/**
 * Generate a session ID with timestamp
 */
export function generateSessionId() {
  return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Format timestamp for logging
 */
export function formatTimestamp(timestamp = Date.now()) {
  return new Date(timestamp).toISOString();
}

/**
 * Check if text contains exit triggers for passive mode
 */
export function containsPassiveModeExitTrigger(text) {
  const exitTriggers = [
    /maya/i,
    /translate/i,
    /that's all/i,
    /any questions/i,
    /we're done/i,
    /did you get/i,
    /capture/i,
    /we're all set/i,
    /maya.*listening/i
  ];
  
  return exitTriggers.some(trigger => trigger.test(text));
}

/**
 * Sanitize text for logging (remove sensitive information)
 */
export function sanitizeForLogging(text) {
  // Remove potential sensitive patterns
  return text
    .replace(/\b\d{3}-\d{2}-\d{4}\b/g, '[SSN]') // SSN
    .replace(/\b\d{16}\b/g, '[CARD]') // Credit card
    .replace(/\b\d{3}-\d{3}-\d{4}\b/g, '[PHONE]'); // Phone number
}

/**
 * Extract patient name from text
 */
export function extractPatientName(text) {
  // Simple pattern matching for common name introductions
  const patterns = [
    /(?:patient|mr|mrs|ms)\s+([a-zA-Z\s]+)/i,
    /this is ([a-zA-Z\s]+)/i,
    /([a-zA-Z\s]+)'s discharge/i
  ];
  
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && match[1]) {
      return match[1].trim();
    }
  }
  
  return null;
}

/**
 * Detect language from text (basic implementation)
 */
export function detectLanguage(text) {
  // Basic language detection patterns
  const languagePatterns = {
    spanish: [/\b(hola|gracias|por favor|sí|no|cómo|está|doctor)\b/i],
    portuguese: [/\b(olá|obrigado|por favor|sim|não|como|está|doutor)\b/i],
    french: [/\b(bonjour|merci|s'il vous plaît|oui|non|comment|docteur)\b/i]
  };
  
  for (const [language, patterns] of Object.entries(languagePatterns)) {
    if (patterns.some(pattern => pattern.test(text))) {
      return language;
    }
  }
  
  return 'english'; // Default
}

/**
 * Validate environment variables
 */
export function validateEnvironment() {
  const required = [
    'LIVEKIT_URL',
    'LIVEKIT_API_KEY', 
    'LIVEKIT_API_SECRET',
    'OPENAI_API_KEY',
    'DEEPGRAM_API_KEY'
  ];
  
  const missing = required.filter(key => !process.env[key]);
  
  if (missing.length > 0) {
    throw new Error(`Missing required environment variables: ${missing.join(', ')}`);
  }
  
  return true;
}