import { CalendarDays } from 'lucide-react'
import { format } from 'date-fns'
import { useState } from 'react'

import { Button } from './ui/button'
import { Calendar } from './ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover'

function CalendarPicker({ onSelectText }) {
  const [date, setDate] = useState()

  const handleSelect = (nextDate) => {
    setDate(nextDate)
    if (nextDate && onSelectText) {
      onSelectText(`Schedule meeting on ${format(nextDate, 'MMM d')}`)
    }
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="secondary"
          size="icon"
          className="h-10 w-10"
          aria-label="Open calendar"
        >
          <CalendarDays className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="end">
        <Calendar mode="single" selected={date} onSelect={handleSelect} initialFocus />
      </PopoverContent>
    </Popover>
  )
}

export { CalendarPicker }
