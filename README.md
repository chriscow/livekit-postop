# PostOp AI - Organized Project Structure

This project has been reorganized from the LiveKit Agent Starter template into a monorepo structure for better maintainability and scalability. It features Maya, an AI medical translation and discharge support specialist.

## 🎯 Maya Agent Features

- **Medical Translation**: Real-time English to patient language translation
- **Passive Listening**: Silent instruction collection mode  
- **Session Management**: Redis-backed conversation persistence
- **Function Tools**: Comprehensive discharge workflow tools
- **Multi-language Support**: Spanish, Portuguese, French, and more

## 📁 Project Structure

```
postop-ai/
├── packages/
│   ├── web/                    # Next.js web interface
│   │   ├── app/               # Next.js app router
│   │   ├── components/        # React components  
│   │   ├── hooks/             # Custom React hooks
│   │   └── lib/               # Web utilities
│   ├── agent/                 # LiveKit AI Agent
│   │   ├── src/
│   │   │   ├── agents/        # Agent implementations
│   │   │   │   ├── base/      # Base agent classes
│   │   │   │   └── discharge/ # Maya discharge agent
│   │   │   ├── lib/           # Agent utilities
│   │   │   │   ├── redis/     # Redis memory management
│   │   │   │   ├── prompts/   # System instructions
│   │   │   │   └── utils/     # Utility functions
│   │   │   ├── tools/         # Function tools
│   │   │   └── workflows/     # Complex workflows
│   │   └── package.json
│   └── shared/                # Shared utilities
│       ├── src/
│       │   ├── types.js       # Shared type definitions
│       │   └── utils.js       # Common utilities
│       └── package.json
├── package.json               # Workspace configuration
└── pnpm-workspace.yaml        # pnpm workspace config
```

## 🚀 Available Scripts

### Root Level Commands
- `pnpm dev:all` - Start both web and agent in development mode
- `pnpm dev:web` - Start only the web interface
- `pnpm dev:agent` - Start only the agent  
- `pnpm agent` - Start agent in production mode
- `pnpm build` - Build all packages
- `pnpm lint` - Lint all packages

### Package-Specific Commands
- `pnpm --filter web <command>` - Run command in web package
- `pnpm --filter agent <command>` - Run command in agent package  
- `pnpm --filter shared <command>` - Run command in shared package

## 🛠️ Development

1. **Install dependencies:**
   ```bash
   pnpm install
   ```

2. **Start development:**
   ```bash
   # Start both web and agent
   pnpm dev:all
   
   # Or start individually
   pnpm dev:web    # Web interface on http://localhost:3000
   pnpm dev:agent  # Agent connects to LiveKit
   ```

3. **Production:**
   ```bash
   pnpm start:agent  # Start Maya discharge agent
   pnpm start:web    # Start web interface
   ```

## 🔧 Environment Setup

Create `.env.local` in the root and each package directory:
```bash
LIVEKIT_URL=wss://your-livekit-server.com
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
OPENAI_API_KEY=your-openai-key
DEEPGRAM_API_KEY=your-deepgram-key
REDIS_URL=redis://your-redis-server:6379
```

## 📦 Benefits of This Structure

- **Modularity**: Clean separation of web interface and agent logic
- **Scalability**: Easy to add new agent types or web features
- **Maintainability**: Well-organized code with clear dependencies
- **Development**: Can work on web/agent independently
- **Deployment**: Flexible deployment options (together or separate)
- **Shared Code**: Common utilities without duplication

## 🏗️ Future Expansion

This structure is designed to easily accommodate:
- Multiple agent types (followup, callback, etc.)
- Additional web features  
- Shared libraries and utilities
- Independent scaling of components
- Different deployment strategies
