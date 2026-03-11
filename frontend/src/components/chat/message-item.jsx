import { Link2 } from 'lucide-react'

import { cn } from '../../lib/utils'
import { Badge } from '../ui/badge'
import { buttonVariants } from '../ui/button'
import { Card, CardContent } from '../ui/card'
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover'

export function MessageItem({ item, versionIndex, onPrev, onNext }) {
  const version = item.versions[versionIndex] ?? item.versions[0]
  const isUser = item.from === 'user'

  return (
    <article className={cn('flex flex-col gap-2', isUser ? 'items-end' : 'items-start')}>
      <Card
        className={cn(
          'w-full max-w-[760px] border shadow-sm',
          isUser ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-white',
        )}
      >
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            {item.model ? (
              <Badge className="bg-slate-100 text-slate-600">Model: {item.model}</Badge>
            ) : null}
            {item.sources?.length ? (
              <Popover>
                <PopoverTrigger
                  className={cn(
                    buttonVariants({ variant: 'outline', size: 'sm' }),
                    'h-7 px-2 text-xs text-slate-600',
                  )}
                  type="button"
                >
                  Sources ({item.sources.length})
                </PopoverTrigger>
                <PopoverContent className="w-80">
                  <div className="space-y-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Sources</p>
                    <ul className="space-y-2 text-sm text-slate-600">
                      {item.sources.map((source, index) => (
                        <li className="flex items-start gap-2" key={`${source.title}-${index}`}>
                          <Link2 size={14} className="mt-0.5 text-slate-400" />
                          {source.href ? (
                            <a
                              className="text-slate-700 underline-offset-2 hover:underline"
                              href={source.href}
                              rel="noreferrer"
                              target="_blank"
                            >
                              {source.title}
                            </a>
                          ) : (
                            <span>{source.title}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                </PopoverContent>
              </Popover>
            ) : null}
          </div>
          <p className="whitespace-pre-wrap text-sm text-slate-900">{version.content}</p>
        </CardContent>
      </Card>

      {item.versions.length > 1 ? (
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <button className={cn(buttonVariants({ variant: 'ghost', size: 'sm' }), 'h-7 px-2')} onClick={onPrev} type="button">
            Prev
          </button>
          <Badge className="bg-slate-100 text-slate-600">
            {versionIndex + 1}/{item.versions.length}
          </Badge>
          <button className={cn(buttonVariants({ variant: 'ghost', size: 'sm' }), 'h-7 px-2')} onClick={onNext} type="button">
            Next
          </button>
        </div>
      ) : null}
    </article>
  )
}
