import { Avatar, AvatarFallback } from './ui/avatar'
import { Card, CardContent } from './ui/card'
import { cn } from '../lib/utils'
import ReactMarkdown from 'react-markdown'

function ChatMessage({ role, content }) {
  const isUser = role === 'user'

  return (
    <div className={cn('flex w-full', isUser ? 'justify-end' : 'justify-start')}>
      <div className={cn('flex items-start gap-3', isUser && 'flex-row-reverse')}>
        <Avatar className={cn('h-8 w-8', isUser ? 'bg-slate-300' : 'bg-slate-200')}>
          <AvatarFallback className={cn('text-[11px]', isUser ? 'bg-slate-300 text-slate-700' : 'bg-slate-200 text-slate-600')}>
            {isUser ? 'YOU' : 'AI'}
          </AvatarFallback>
        </Avatar>
        <Card
          className={cn(
            'max-w-[75%] rounded-2xl border-slate-200/70 shadow-sm',
            isUser ? 'bg-slate-200 text-slate-900' : 'bg-slate-50 text-slate-900',
          )}
        >
          <CardContent className="p-3 text-sm leading-relaxed break-words">
            <ReactMarkdown
              components={{
                p: (props) => <p className="mb-2 last:mb-0" {...props} />,
                strong: (props) => <strong className="font-semibold" {...props} />,
                em: (props) => <em className="italic" {...props} />,
                ul: (props) => <ul className="mb-2 list-disc pl-5" {...props} />,
                ol: (props) => <ol className="mb-2 list-decimal pl-5" {...props} />,
                li: (props) => <li className="mb-1 last:mb-0" {...props} />,
                code: (props) => (
                  <code className="rounded bg-slate-200 px-1 py-0.5 text-[0.85em]" {...props} />
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export { ChatMessage }
