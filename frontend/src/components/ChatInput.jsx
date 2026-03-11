import { Mic, SendHorizontal } from 'lucide-react'

import { CalendarPicker } from './CalendarPicker'
import { Button } from './ui/button'
import { Input } from './ui/input'

function ChatInput({ value, onChange, onSend, isLoading }) {
  const handleSubmit = (event) => {
    event.preventDefault()
    onSend(value)
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          className="h-11 min-w-[200px] flex-1"
          placeholder="Ask about your schedule, meetings, or notes..."
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        <CalendarPicker onSelectText={(text) => onChange(text)} />
        <Button type="button" variant="secondary" size="icon" className="h-11 w-11" aria-label="Voice input">
          <Mic className="h-4 w-4" />
        </Button>
        <Button type="submit" className="h-11 px-4" disabled={isLoading || !value.trim()}>
          <SendHorizontal className="h-4 w-4" />
          Send
        </Button>
      </div>
      <p className="text-xs text-slate-500">
        Tip: Pick a date to prefill a scheduling request.
      </p>
    </form>
  )
}

export { ChatInput }
