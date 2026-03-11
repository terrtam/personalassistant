import { Check, ChevronDown } from 'lucide-react'
import { useMemo, useState } from 'react'

import { cn } from '../../lib/utils'
import { buttonVariants } from '../ui/button'
import { Input } from '../ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover'

const providers = ['OpenAI', 'Anthropic', 'Google']

export function ModelSelector({ model, models, onChange }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')

  const selected = useMemo(() => models.find((entry) => entry.id === model), [model, models])
  const grouped = useMemo(() => {
    const query = search.toLowerCase().trim()
    const filtered = query
      ? models.filter((entry) => `${entry.name} ${entry.provider}`.toLowerCase().includes(query))
      : models
    return providers.map((provider) => ({
      provider,
      entries: filtered.filter((entry) => entry.provider === provider),
    }))
  }, [models, search])

  return (
    <Popover onOpenChange={setOpen} open={open}>
      <PopoverTrigger
        className={cn(
          buttonVariants({ variant: 'secondary' }),
          'h-9 gap-2 border border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
        )}
        type="button"
      >
        <span className="h-2 w-2 rounded-full bg-blue-500" />
        <span>{selected?.name ?? 'Select model'}</span>
        <ChevronDown size={14} className={cn('text-slate-400 transition', open ? 'rotate-180' : '')} />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 border-slate-200 bg-white p-3">
        <Input
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search models..."
          value={search}
        />
        <div className="mt-3 max-h-60 space-y-3 overflow-y-auto pr-1">
          {grouped.map((group) => (
            <div key={group.provider}>
              <p className="text-[0.7rem] font-semibold uppercase tracking-wide text-slate-500">{group.provider}</p>
              {group.entries.length ? (
                <div className="mt-2 space-y-1">
                  {group.entries.map((entry) => (
                    <button
                      className={cn(
                        'flex w-full items-center justify-between rounded-lg px-2 py-2 text-left text-sm transition',
                        entry.id === model ? 'bg-slate-100 text-slate-900' : 'text-slate-600 hover:bg-slate-50',
                      )}
                      key={entry.id}
                      onClick={() => {
                        onChange(entry.id)
                        setOpen(false)
                      }}
                      type="button"
                    >
                      <span>{entry.name}</span>
                      {entry.id === model ? (
                        <Check size={14} className="text-emerald-600" />
                      ) : (
                        <span className="text-xs text-slate-300">•</span>
                      )}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-xs text-slate-500">No models found.</p>
              )}
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
