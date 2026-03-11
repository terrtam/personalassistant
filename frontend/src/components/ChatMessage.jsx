import { Avatar, AvatarFallback } from './ui/avatar'
import { Card, CardContent } from './ui/card'
import { cn } from '../lib/utils'

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
          <CardContent className="p-3 text-sm leading-relaxed whitespace-pre-wrap">
            {content}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export { ChatMessage }
