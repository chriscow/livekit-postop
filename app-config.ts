import type { AppConfig } from './lib/types';

export const APP_CONFIG_DEFAULTS: AppConfig = {
  companyName: 'PostOp AI',
  pageTitle: 'PostOp AI Voice Agent',
  pageDescription: 'A voice agent for post-operative patient care',

  supportsChatInput: true,
  supportsVideoInput: false,
  supportsScreenShare: false,
  isPreConnectBufferEnabled: true,

  logo: '/postop-logo.svg',
  accent: '#002cf2',
  logoDark: '/postop-logo-dark.svg',
  accentDark: '#1fd5f9',
  startButtonText: 'Start call',
};
