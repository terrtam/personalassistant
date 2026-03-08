export const models = [
  { id: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI' },
  { id: 'gpt-4o-mini', name: 'GPT-4o Mini', provider: 'OpenAI' },
  { id: 'claude-sonnet-4-20250514', name: 'Claude 4 Sonnet', provider: 'Anthropic' },
  { id: 'claude-opus-4-20250514', name: 'Claude 4 Opus', provider: 'Anthropic' },
  { id: 'gemini-2.0-flash-exp', name: 'Gemini 2.0 Flash', provider: 'Google' },
]

export const suggestions = [
  'What are the latest trends in AI?',
  'How does machine learning work?',
  'Explain quantum computing',
  'Best practices for React development',
  'How should I structure a backend API?',
]

export const initialMessages = [
  {
    key: 'seed-user-1',
    from: 'user',
    versions: [{ id: 'seed-user-1-v1', content: 'Can you explain React hooks best practices?' }],
  },
  {
    key: 'seed-assistant-1',
    from: 'assistant',
    sources: [{ href: 'https://react.dev/reference/react', title: 'React Docs' }],
    versions: [
      {
        id: 'seed-assistant-1-v1',
        content:
          'React hooks work best when they stay predictable: call hooks at top level, keep effects narrow, and only memoize when profiling shows real gains.',
      },
    ],
  },
]
